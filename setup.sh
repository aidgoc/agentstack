#!/bin/bash
# AgentStack — one-command setup + run
# Usage: curl -sL <raw-url> | bash
# Or:    git clone ... && bash setup.sh

set -e
cd "$(dirname "$0")"

# ── Install missing deps ─────────────────────────────
install_deps() {
    echo "Installing dependencies..."

    if [[ "$OSTYPE" == "darwin"* ]]; then
        # Mac
        command -v brew &>/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
        command -v tmux &>/dev/null       || brew install tmux
        command -v cloudflared &>/dev/null || brew install cloudflared
        command -v python3 &>/dev/null    || brew install python
        command -v node &>/dev/null       || brew install node
        command -v claude &>/dev/null     || npm install -g @anthropic-ai/claude-code
    else
        # Linux
        command -v tmux &>/dev/null || sudo apt-get install -y tmux
        if ! command -v cloudflared &>/dev/null; then
            curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
                -o /tmp/cloudflared && chmod +x /tmp/cloudflared && sudo mv /tmp/cloudflared /usr/local/bin/
        fi
        command -v claude &>/dev/null || npm install -g @anthropic-ai/claude-code 2>/dev/null || true
    fi

    pip3 install -q -r requirements.txt 2>/dev/null || pip install -q -r requirements.txt
}

# ── Configure ─────────────────────────────────────────
configure() {
    if [ -f .env ] && grep -q "TELEGRAM_BOT_TOKEN=." .env 2>/dev/null; then
        echo "Config found."
        return
    fi

    echo ""
    echo "First-time setup. You need a Telegram bot token."
    echo "Get one: open @BotFather on Telegram -> /newbot"
    echo ""
    read -p "Paste bot token: " BOT_TOKEN

    if [ -z "$BOT_TOKEN" ]; then
        echo "No token. Exiting."
        exit 1
    fi

    echo ""
    read -p "Your Telegram user ID (for admin access, or press Enter to skip): " ADMIN_ID

    cat > .env <<EOL
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ADMIN_USERS=$ADMIN_ID
MAX_SESSIONS_PER_USER=10
EOL

    echo "Config saved to .env"
}

# ── Run ───────────────────────────────────────────────
echo "=================================="
echo "  AgentStack Setup"
echo "=================================="

install_deps
configure

echo ""
echo "Starting AgentStack..."
echo ""

exec bash start.sh
