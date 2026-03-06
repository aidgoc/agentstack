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
        command -v claude &>/dev/null     || npm install -g @anthropic-ai/claude-code
    else
        # Linux
        if ! command -v cloudflared &>/dev/null; then
            curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
                -o /tmp/cloudflared && chmod +x /tmp/cloudflared && sudo mv /tmp/cloudflared /usr/local/bin/
        fi
        command -v claude &>/dev/null || npm install -g @anthropic-ai/claude-code 2>/dev/null || true
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

# ── Run ───────────────────────────────────────────────
install_deps
configure

echo ""
echo "Starting AgentStack..."
echo ""

exec bash start.sh
