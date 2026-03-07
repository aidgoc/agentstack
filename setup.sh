#!/bin/bash
# AgentStack — one-command setup + run
# Usage: git clone ... && bash setup.sh

set -e
cd "$(dirname "$0")"

echo "=================================="
echo "  AgentStack Setup"
echo "=================================="

# ── Install missing deps ─────────────────────────────
install_deps() {
    echo ""
    echo "Checking dependencies..."

    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        command -v brew &>/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
        command -v cloudflared &>/dev/null || brew install cloudflare/cloudflare/cloudflared
        command -v python3 &>/dev/null    || brew install python
        command -v node &>/dev/null       || brew install node
        command -v tmux &>/dev/null       || brew install tmux
        command -v claude &>/dev/null     || npm install -g @anthropic-ai/claude-code
    else
        # Linux
        PKGS=""
        command -v tmux &>/dev/null || PKGS="$PKGS tmux"
        command -v curl &>/dev/null || PKGS="$PKGS curl"
        if [ -n "$PKGS" ]; then
            sudo apt-get update -qq && sudo apt-get install -y -qq $PKGS >/dev/null 2>&1
        fi
        if ! command -v cloudflared &>/dev/null; then
            ARCH=$(uname -m)
            case "$ARCH" in
                x86_64|amd64)   CF_ARCH="amd64" ;;
                aarch64|arm64)  CF_ARCH="arm64" ;;
                armv7l|armhf)   CF_ARCH="arm" ;;
                *)              CF_ARCH="amd64" ;;
            esac
            curl -sL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}" \
                -o /tmp/cloudflared && chmod +x /tmp/cloudflared && sudo mv /tmp/cloudflared /usr/local/bin/
        fi
        command -v claude &>/dev/null || npm install -g @anthropic-ai/claude-code 2>/dev/null || \
            sudo npm install -g @anthropic-ai/claude-code 2>/dev/null || true
    fi

    # Python venv
    if [ ! -d ".venv" ]; then
        echo "Creating Python virtual environment..."
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install -q -r requirements.txt

    echo "  All dependencies OK"
}

# ── Configure ─────────────────────────────────────────
configure() {
    if [ -f .env ] && grep -q "TELEGRAM_BOT_TOKEN=." .env 2>/dev/null && grep -q "OWNER_ID=." .env 2>/dev/null; then
        echo "Config found."
        return
    fi

    echo ""
    echo "First-time setup. You need:"
    echo "  1. A Telegram bot token (from @BotFather → /newbot)"
    echo "  2. Your Telegram user ID (from @userinfobot)"
    echo ""
    read -p "Paste bot token: " BOT_TOKEN
    if [ -z "$BOT_TOKEN" ]; then
        echo "No token. Exiting."
        exit 1
    fi

    read -p "Your Telegram user ID: " OWNER_ID
    if [ -z "$OWNER_ID" ]; then
        echo "No owner ID. Exiting."
        exit 1
    fi

    cat > .env <<EOL
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
OWNER_ID=$OWNER_ID
EOL

    echo "Config saved to .env"
}

# ── xdg-open interceptor ─────────────────────────────
install_xdg_interceptor() {
    if [[ "$OSTYPE" == "darwin"* ]]; then return; fi  # macOS not needed
    if grep -q "AgentStack" /usr/local/bin/xdg-open 2>/dev/null; then return; fi
    echo "Installing xdg-open interceptor (forwards browser URLs to Telegram)..."
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
    echo "  OK"
}

# ── Run ───────────────────────────────────────────────
install_deps
configure
install_xdg_interceptor

echo ""
echo "Starting AgentStack..."
echo ""

exec bash start.sh
