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

# ── Pre-flight ───────────────────────────────────────
if [[ "$OSTYPE" == "darwin"* ]]; then
    PLATFORM="mac"
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
else
    echo "Unsupported platform: $OSTYPE"
    echo "AgentStack supports macOS and Linux."
    exit 1
fi

# ── Install dependencies ────────────────────────────
echo "[1/5] Installing dependencies..."

if [ "$PLATFORM" = "mac" ]; then
    command -v git &>/dev/null         || brew install git
    command -v python3 &>/dev/null     || brew install python
    command -v node &>/dev/null        || brew install node
    command -v cloudflared &>/dev/null || brew install cloudflare/cloudflare/cloudflared
else
    # Linux
    if ! command -v git &>/dev/null || ! command -v python3 &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq git python3 python3-venv curl >/dev/null 2>&1
    fi
    if ! command -v node &>/dev/null; then
        curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - >/dev/null 2>&1
        sudo apt-get install -y -qq nodejs >/dev/null 2>&1
    fi
    if ! command -v cloudflared &>/dev/null; then
        echo "  Installing cloudflared..."
        curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
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
    npm install -g @anthropic-ai/claude-code 2>/dev/null
    echo "  OK"
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
    stop)    pkill -f "agentstack/web/server.py" 2>/dev/null; pkill -f "agentstack/bot.py" 2>/dev/null; pkill -f "cloudflared tunnel.*8765" 2>/dev/null; echo "Stopped." ;;
    logs)    tail -f /tmp/agentstack/*.log ;;
    health)  curl -s http://localhost:8765/health | python3 -m json.tool ;;
    update)  git pull origin main && pip install -q -r requirements.txt && echo "Updated. Run: agentstack start" ;;
    *)       echo "Usage: agentstack [start|stop|logs|health|update]" ;;
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

read -p "  Start AgentStack now? [Y/n] " START_NOW
if [[ "${START_NOW:-Y}" =~ ^[Yy]$ ]]; then
    exec bash start.sh
fi
