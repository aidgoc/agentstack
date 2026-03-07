#!/bin/bash
# AgentStack — one-command installer
#
# Usage:
#   curl -sL https://raw.githubusercontent.com/aidgoc/agentstack/main/install.sh | bash
#
# That's it. Installs everything, asks for your Telegram bot token, and starts.

set -e

REPO="https://github.com/aidgoc/agentstack.git"
INSTALL_DIR="$HOME/.agentstack"

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║         AgentStack               ║"
echo "  ║   Your terminal, from Telegram   ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# ── Detect platform & architecture ───────────────────
if [[ "$OSTYPE" == "darwin"* ]]; then
    PLATFORM="mac"
    ARCH=$(uname -m)  # arm64 or x86_64
    if ! command -v brew &>/dev/null; then
        echo "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # Add brew to PATH for Apple Silicon
        if [ -f /opt/homebrew/bin/brew ]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PLATFORM="linux"
    ARCH=$(uname -m)  # x86_64, aarch64, armv7l
else
    echo "Unsupported platform: $OSTYPE"
    echo "AgentStack supports macOS and Linux."
    exit 1
fi

echo "  Platform: $PLATFORM ($ARCH)"
echo ""

# ── Install dependencies ────────────────────────────
echo "[1/5] Installing dependencies..."

if [ "$PLATFORM" = "mac" ]; then
    command -v git &>/dev/null         || brew install git
    command -v python3 &>/dev/null     || brew install python
    command -v node &>/dev/null        || brew install node
    command -v tmux &>/dev/null        || brew install tmux
    command -v cloudflared &>/dev/null || brew install cloudflare/cloudflare/cloudflared
else
    # Linux — install system packages
    NEED_APT=false
    PKGS=""
    command -v git &>/dev/null      || { NEED_APT=true; PKGS="$PKGS git"; }
    command -v python3 &>/dev/null  || { NEED_APT=true; PKGS="$PKGS python3 python3-venv"; }
    command -v tmux &>/dev/null     || { NEED_APT=true; PKGS="$PKGS tmux"; }
    command -v curl &>/dev/null     || { NEED_APT=true; PKGS="$PKGS curl"; }

    if [ "$NEED_APT" = true ]; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq $PKGS >/dev/null 2>&1
    fi

    # Node.js
    if ! command -v node &>/dev/null; then
        curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - >/dev/null 2>&1
        sudo apt-get install -y -qq nodejs >/dev/null 2>&1
    fi

    # cloudflared — detect architecture
    if ! command -v cloudflared &>/dev/null; then
        echo "  Installing cloudflared..."
        case "$ARCH" in
            x86_64|amd64)   CF_ARCH="amd64" ;;
            aarch64|arm64)  CF_ARCH="arm64" ;;
            armv7l|armhf)   CF_ARCH="arm" ;;
            *)              CF_ARCH="amd64" ;;
        esac
        curl -sL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}" \
            -o /tmp/cloudflared && chmod +x /tmp/cloudflared && sudo mv /tmp/cloudflared /usr/local/bin/
    fi
fi

echo "  OK"

# ── Install Claude Code ─────────────────────────────
echo "[2/5] Claude Code..."
if command -v claude &>/dev/null; then
    echo "  Already installed"
else
    echo "  Installing..."
    if [ "$PLATFORM" = "linux" ]; then
        # Try without sudo first, fall back to sudo
        npm install -g @anthropic-ai/claude-code 2>/dev/null || \
        sudo npm install -g @anthropic-ai/claude-code 2>/dev/null || \
        { echo "  WARN: Could not install Claude Code globally. Trying npx fallback..."; }
    else
        npm install -g @anthropic-ai/claude-code 2>/dev/null
    fi

    if command -v claude &>/dev/null; then
        echo "  OK"
    else
        echo "  WARN: 'claude' not in PATH. You can run: npx @anthropic-ai/claude-code"
        echo "        Or fix with: sudo npm install -g @anthropic-ai/claude-code"
    fi
fi

# ── Clone / update repo ─────────────────────────────
echo "[3/5] AgentStack..."
if [ -d "$INSTALL_DIR" ]; then
    echo "  Updating..."
    cd "$INSTALL_DIR"
    git pull --quiet origin main 2>/dev/null || true
else
    echo "  Cloning..."
    git clone --quiet "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Python venv
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
echo "  OK"

# ── Configure ────────────────────────────────────────
echo "[4/5] Configuration..."
if [ -f .env ] && grep -q "TELEGRAM_BOT_TOKEN=." .env 2>/dev/null && grep -q "OWNER_ID=." .env 2>/dev/null; then
    echo "  Config found"
else
    echo ""
    echo "  You need two things from Telegram:"
    echo "  1. Bot token  → open @BotFather, send /newbot"
    echo "  2. Your user ID → open @userinfobot, send /start"
    echo ""
    read -p "  Bot token: " BOT_TOKEN
    if [ -z "$BOT_TOKEN" ]; then
        echo "  No token provided. Run this again when ready."
        exit 1
    fi
    read -p "  Your Telegram user ID: " OWNER_ID
    if [ -z "$OWNER_ID" ]; then
        echo "  No user ID provided. Run this again when ready."
        exit 1
    fi

    cat > .env <<EOL
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
OWNER_ID=$OWNER_ID
EOL
    echo "  Saved"
fi

# ── xdg-open interceptor (Linux only) ───────────────
# Intercepts browser URL opens from the terminal and sends them to Telegram.
# Required for OAuth flows (Claude auth, Figma MCP, etc.) to work remotely.
if [ "$PLATFORM" = "linux" ]; then
    if ! grep -q "AgentStack" /usr/local/bin/xdg-open 2>/dev/null; then
        echo "Installing xdg-open interceptor..."
        _BOT=$(grep TELEGRAM_BOT_TOKEN .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')
        _OWN=$(grep OWNER_ID .env 2>/dev/null | cut -d= -f2 | tr -d '[:space:]')
        sudo tee /usr/local/bin/xdg-open > /dev/null << XDGEOF
#!/bin/bash
# AgentStack xdg-open interceptor — sends URLs to Telegram instead of a browser.
BOT_TOKEN="${_BOT}"
CHAT_ID="${_OWN}"
URL="\$1"
if [[ "\$URL" =~ ^https?:// ]]; then
    if [[ "\$URL" =~ redirect_uri=http ]]; then
        MSG="Open this auth link. NOTE: redirect_uri points to localhost on this server — complete auth while the local callback server is still running.\n\n\$URL"
    else
        MSG="Open this link:\n\n\$URL"
    fi
    curl -s -X POST "https://api.telegram.org/bot\${BOT_TOKEN}/sendMessage" \
        -d "chat_id=\${CHAT_ID}" --data-urlencode "text=\${MSG}" \
        -d "disable_web_page_preview=false" > /dev/null 2>&1
    echo "Link sent to Telegram." >&2
    exit 0
fi
REAL="/usr/bin/xdg-open"
[ -x "\$REAL" ] && exec "\$REAL" "\$@"
echo "xdg-open: no browser available" >&2
exit 1
XDGEOF
        sudo chmod +x /usr/local/bin/xdg-open
        echo "  OK (browser links will be forwarded to Telegram)"
    fi
fi

# ── Add to PATH ─────────────────────────────────────
echo "[5/5] Setting up command..."

# Create agentstack command
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/agentstack" <<SCRIPT
#!/bin/bash
cd "$INSTALL_DIR"
[ -f .venv/bin/activate ] && source .venv/bin/activate
case "\${1:-start}" in
    start)   exec bash start.sh ;;
    stop)    kill \$(cat /tmp/agentstack/sentinel.pid 2>/dev/null) 2>/dev/null; pkill -f "web/server.py" 2>/dev/null; pkill -f "bot\.py" 2>/dev/null; pkill -f "cloudflared tunnel.*8765" 2>/dev/null; echo "Stopped." ;;
    sentinel) bash sentinel.sh ;;
    watch)    exec bash sentinel.sh --watch ;;
    logs)    tail -f /tmp/agentstack/*.log ;;
    health)  curl -s http://localhost:8765/health | python3 -m json.tool ;;
    update)  git pull origin main && pip install -q -r requirements.txt && echo "Updated. Run: agentstack start" ;;
    *)       echo "Usage: agentstack [start|stop|sentinel|watch|logs|health|update]" ;;
esac
SCRIPT
chmod +x "$BIN_DIR/agentstack"

# Add to PATH if needed
SHELL_RC=""
if [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
fi

if [ -n "$SHELL_RC" ] && ! grep -q '.local/bin' "$SHELL_RC" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
fi
export PATH="$BIN_DIR:$PATH"

echo "  OK"

# ── macOS auto-start ────────────────────────────────
if [ "$PLATFORM" = "mac" ]; then
    echo ""
    read -p "  Start AgentStack on login? [Y/n] " AUTOSTART
    if [[ "${AUTOSTART:-Y}" =~ ^[Yy]$ ]]; then
        bash macos/install-service.sh
    fi
fi

# ── Done ─────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║         Ready!                   ║"
echo "  ╚══════════════════════════════════╝"
echo ""
echo "  Start now:     agentstack"
echo "  Stop:          agentstack stop"
echo "  View logs:     agentstack logs"
echo "  Update:        agentstack update"
echo ""
echo "  Installed to:  $INSTALL_DIR"
echo ""
echo "  Note: If you haven't logged into Claude Code yet,"
echo "  open a terminal and run: claude"
echo "  It will open your browser to sign in with your Anthropic account."
echo ""

read -p "  Start AgentStack now? [Y/n] " START_NOW
if [[ "${START_NOW:-Y}" =~ ^[Yy]$ ]]; then
    exec bash start.sh
fi
