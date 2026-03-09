#!/bin/bash
# AgentStack — one-command installer
#
# Usage:
#   curl -sL https://raw.githubusercontent.com/aidgoc/agentstack/main/install.sh | bash
#
# That's it. Installs everything, walks you through Telegram setup, and starts.

set -e

REPO="https://github.com/aidgoc/agentstack.git"
INSTALL_DIR="$HOME/.agentstack"

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║         AgentStack               ║"
echo "  ║   Your terminal, from Telegram   ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# ── Helper: open links (browser or Telegram deep link) ──
open_link() {
    if [ "$PLATFORM" = "mac" ]; then
        open "$1" 2>/dev/null || true
    else
        xdg-open "$1" 2>/dev/null || true
    fi
}

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
elif [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "linux-musl"* ]]; then
    PLATFORM="linux"
    ARCH=$(uname -m)  # x86_64, aarch64, armv7l
    # Detect package manager
    if command -v apt-get &>/dev/null; then
        PKG_MGR="apt"
    elif command -v dnf &>/dev/null; then
        PKG_MGR="dnf"
    elif command -v yum &>/dev/null; then
        PKG_MGR="yum"
    elif command -v pacman &>/dev/null; then
        PKG_MGR="pacman"
    else
        PKG_MGR="unknown"
    fi
else
    echo "Unsupported platform: $OSTYPE"
    echo "AgentStack supports macOS and Linux."
    exit 1
fi

echo "  Platform: $PLATFORM ($ARCH)"
echo ""

# ── Install dependencies ────────────────────────────
echo "[1/6] Installing dependencies..."

if [ "$PLATFORM" = "mac" ]; then
    command -v git &>/dev/null         || brew install git
    command -v python3 &>/dev/null     || brew install python
    command -v node &>/dev/null        || brew install node
    command -v tmux &>/dev/null        || brew install tmux
    command -v cloudflared &>/dev/null || brew install cloudflare/cloudflare/cloudflared
else
    # Linux — install system packages
    if [ "$PKG_MGR" = "apt" ]; then
        PKGS=""
        command -v git &>/dev/null      || PKGS="$PKGS git"
        command -v python3 &>/dev/null  || PKGS="$PKGS python3 python3-venv"
        command -v tmux &>/dev/null     || PKGS="$PKGS tmux"
        command -v curl &>/dev/null     || PKGS="$PKGS curl"
        if [ -n "$PKGS" ]; then
            sudo apt-get update -qq
            sudo apt-get install -y -qq $PKGS >/dev/null 2>&1
        fi
        # Node.js via NodeSource if not present
        if ! command -v node &>/dev/null; then
            curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - >/dev/null 2>&1
            sudo apt-get install -y -qq nodejs >/dev/null 2>&1
        fi
    elif [ "$PKG_MGR" = "dnf" ] || [ "$PKG_MGR" = "yum" ]; then
        $PKG_MGR install -y -q git python3 tmux curl >/dev/null 2>&1 || true
        command -v node &>/dev/null || { curl -fsSL https://rpm.nodesource.com/setup_lts.x | sudo bash - >/dev/null 2>&1; $PKG_MGR install -y nodejs >/dev/null 2>&1; } || true
    elif [ "$PKG_MGR" = "pacman" ]; then
        sudo pacman -Sy --noconfirm git python tmux curl nodejs npm >/dev/null 2>&1 || true
    else
        echo "  WARN: Unknown package manager. Ensure git, python3 (3.10+), tmux, curl, node are installed."
    fi

    # cloudflared — binary install (works on all distros)
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

# ── Python version check (3.10+ required) ───────────
PY_VER=$(python3 -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>/dev/null || echo "0.0")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo ""
    echo "  ERROR: Python 3.10+ required (found $PY_VER)"
    if [ "$PLATFORM" = "linux" ] && [ "$PKG_MGR" = "apt" ]; then
        echo "  Installing Python 3.12 from deadsnakes PPA..."
        sudo apt-get install -y -qq software-properties-common >/dev/null 2>&1
        sudo add-apt-repository -y ppa:deadsnakes/ppa >/dev/null 2>&1
        sudo apt-get install -y -qq python3.12 python3.12-venv >/dev/null 2>&1
        sudo update-alternatives --install /usr/local/bin/python3 python3 /usr/bin/python3.12 10 >/dev/null 2>&1
        echo "  Python 3.12 installed"
    else
        echo "  Please install Python 3.10+ and re-run this script."
        echo "  macOS: brew install python"
        echo "  Ubuntu 20.04: sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.12"
        exit 1
    fi
fi

echo "  ✓ Python $PY_VER"

# ── Install Claude Code ─────────────────────────────
echo "[2/6] Claude Code..."
if command -v claude &>/dev/null; then
    echo "  ✓ Already installed"
else
    echo "  Installing..."
    if [ "$PLATFORM" = "linux" ]; then
        npm install -g @anthropic-ai/claude-code 2>/dev/null || \
        sudo npm install -g @anthropic-ai/claude-code 2>/dev/null || \
        { echo "  WARN: Could not install Claude Code globally. Trying npx fallback..."; }
    else
        npm install -g @anthropic-ai/claude-code 2>/dev/null
    fi

    if command -v claude &>/dev/null; then
        echo "  ✓ Installed"
    else
        echo "  WARN: 'claude' not in PATH. You can run: npx @anthropic-ai/claude-code"
        echo "        Or fix with: sudo npm install -g @anthropic-ai/claude-code"
    fi
fi

# ── Clone / update repo ─────────────────────────────
echo "[3/6] AgentStack..."
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
echo "  ✓ Ready"

# ── Telegram Bot Setup (with deep links) ─────────────
echo ""
echo "[4/6] Telegram Setup..."
if [ -f .env ] && grep -q "TELEGRAM_BOT_TOKEN=." .env 2>/dev/null && grep -q "OWNER_ID=." .env 2>/dev/null; then
    echo "  ✓ Config found"
else
    echo ""
    echo "  ─── Step 1: Create a bot with @BotFather ───"
    echo ""
    echo "    Opening Telegram..."
    open_link "https://t.me/BotFather"
    echo "    1. Send /newbot to @BotFather"
    echo "    2. Choose a name and username for your bot"
    echo "    3. Copy the token it gives you"
    echo ""
    read -p "  Paste your bot token: " BOT_TOKEN

    # Validate token
    if [ -z "$BOT_TOKEN" ]; then
        echo "  ✗ No token provided. Run this again when ready."
        exit 1
    fi
    GETME=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getMe")
    if echo "$GETME" | grep -q '"ok":true'; then
        BOT_NAME=$(echo "$GETME" | grep -o '"username":"[^"]*"' | cut -d'"' -f4)
        echo "  ✓ Token valid! Bot: @${BOT_NAME}"
    else
        echo "  ✗ Invalid token. Check and try again."
        exit 1
    fi

    echo ""
    echo "  ─── Step 2: Get your Telegram user ID ───"
    echo ""
    echo "    Opening @userinfobot..."
    open_link "https://t.me/userinfobot"
    echo "    Send any message — it will reply with your ID."
    echo ""
    read -p "  Your Telegram user ID: " OWNER_ID
    if ! [[ "$OWNER_ID" =~ ^[0-9]+$ ]]; then
        echo "  ✗ User ID must be a number. Try again."
        exit 1
    fi
    echo "  ✓ User ID saved"

    cat > .env <<EOL
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
OWNER_ID=$OWNER_ID
EOL
    echo "  ✓ Config saved"
fi

# ── Claude Code authentication ──────────────────────
echo ""
echo "[5/6] Claude Code authentication..."
CLAUDE_AUTHED=false
# Check common credential locations
for cred_path in "$HOME/.claude/.credentials.json" "$HOME/.claude/auth.json" "$HOME/.config/claude/credentials.json"; do
    if [ -f "$cred_path" ]; then
        CLAUDE_AUTHED=true
        break
    fi
done
# Also check if ANTHROPIC_API_KEY is already in .env
if grep -q "ANTHROPIC_API_KEY=." .env 2>/dev/null; then
    CLAUDE_AUTHED=true
fi

if [ "$CLAUDE_AUTHED" = true ]; then
    echo "  ✓ Already authenticated"
else
    echo ""
    echo "  Agents need Claude Code authenticated. Two options:"
    echo ""
    echo "  Option A — API key (works on any server, no browser needed)"
    echo "    Get one at: https://console.anthropic.com/settings/keys"
    echo ""
    read -p "  Paste Anthropic API key (or press Enter to skip): " ANTHROPIC_API_KEY_INPUT
    if [ -n "$ANTHROPIC_API_KEY_INPUT" ]; then
        # Remove existing key if present, then append
        grep -v "^ANTHROPIC_API_KEY=" .env > /tmp/.env_tmp 2>/dev/null && mv /tmp/.env_tmp .env || true
        echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY_INPUT" >> .env
        echo "  ✓ Saved to .env"
    else
        echo ""
        echo "  Skipped. After install, run this to authenticate:"
        echo "    ssh into this machine and run: claude"
        echo "  Important: do NOT try to authenticate from inside the Telegram terminal."
        echo "  The OAuth callback goes to localhost — it must be done locally."
        echo ""
    fi
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
        echo "  ✓ Browser links will be forwarded to Telegram"
    fi
fi

# ── Generate agent configs ──────────────────────────
echo ""
echo "[6/6] Generating agent configurations..."
bash generate-configs.sh "$(pwd)"

# ── Add to PATH ─────────────────────────────────────
echo ""
echo "Setting up command..."

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
    update)  git pull origin main && pip install -q -r requirements.txt && bash generate-configs.sh "\$(pwd)" && echo "Updated. Run: agentstack start" ;;
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

echo "  ✓ Command installed"

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
echo "  ║         ✓ Ready!                 ║"
echo "  ╚══════════════════════════════════╝"
echo ""
echo "  Start now:     agentstack"
echo "  Stop:          agentstack stop"
echo "  View logs:     agentstack logs"
echo "  Health check:  agentstack health"
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
