#!/bin/bash
# AgentStack launcher
# Starts: web server -> cloudflared tunnel -> auto-configures bot -> launches bot
# Tunnel URL is detected automatically on every restart. Zero manual steps.
# Works on Linux and macOS.

set -e
cd "$(dirname "$0")"

PORT=${AGENTSTACK_PORT:-8765}
LOG_DIR="/tmp/agentstack"
mkdir -p "$LOG_DIR" shared

cleanup() {
    echo ""
    echo "Shutting down..."
    [ -n "$BOT_PID" ]  && kill $BOT_PID 2>/dev/null
    [ -n "$CF_PID" ]   && kill $CF_PID 2>/dev/null
    [ -n "$WEB_PID" ]  && kill $WEB_PID 2>/dev/null
    wait 2>/dev/null
    echo "Done."
}
trap cleanup EXIT INT TERM

echo "=================================="
echo "  AgentStack"
echo "=================================="

# ── Check deps ────────────────────────────────────────
missing=""
for cmd in claude tmux cloudflared python3; do
    if ! command -v $cmd &>/dev/null; then
        missing="$missing $cmd"
    fi
done
if [ -n "$missing" ]; then
    echo ""
    echo "Missing:$missing"
    echo ""
    echo "Install:"
    echo "  claude:      npm install -g @anthropic-ai/claude-code"
    echo "  tmux:        brew install tmux          (Mac)"
    echo "               sudo apt install tmux      (Linux)"
    echo "  cloudflared: brew install cloudflared    (Mac)"
    echo "               see README.md              (Linux)"
    exit 1
fi

# ── Check .env ────────────────────────────────────────
if [ ! -f .env ]; then
    echo ""
    echo "No .env file found. Copy from example:"
    echo "  cp .env.example .env"
    echo "Then fill in TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USERS."
    exit 1
fi

# ── Kill previous instances ──────────────────────────
pkill -9 -f "agentstack/web/server.py" 2>/dev/null || true
pkill -9 -f "agentstack/bot.py" 2>/dev/null || true
pkill -9 -f "cloudflared tunnel.*$PORT" 2>/dev/null || true
# Kill anything on the port (cross-platform)
if command -v fuser &>/dev/null; then
    fuser -k ${PORT}/tcp 2>/dev/null || true
elif command -v lsof &>/dev/null; then
    lsof -ti :${PORT} | xargs kill -9 2>/dev/null || true
fi

# Clear stale Telegram polling
BOT_TOKEN=$(grep TELEGRAM_BOT_TOKEN .env 2>/dev/null | cut -d= -f2)
if [ -n "$BOT_TOKEN" ]; then
    curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates?offset=-1&timeout=0" > /dev/null 2>&1
fi
sleep 2

# ── 1. Web server ────────────────────────────────────
echo ""
echo "[1/3] Web server on :$PORT"
python3 -u web/server.py > "$LOG_DIR/web.log" 2>&1 &
WEB_PID=$!
sleep 2

if ! kill -0 $WEB_PID 2>/dev/null; then
    echo "  FAILED — check $LOG_DIR/web.log"
    cat "$LOG_DIR/web.log"
    exit 1
fi
echo "  OK (pid $WEB_PID)"

# ── 2. Cloudflare tunnel ─────────────────────────────
echo "[2/3] Cloudflare tunnel"
cloudflared tunnel --url http://localhost:$PORT > "$LOG_DIR/tunnel.log" 2>&1 &
CF_PID=$!

# Wait for URL (up to 20 seconds)
TUNNEL_URL=""
for i in $(seq 1 40); do
    # Cross-platform grep (no -P on Mac)
    TUNNEL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG_DIR/tunnel.log" 2>/dev/null | head -1)
    [ -n "$TUNNEL_URL" ] && break
    sleep 0.5
done

if [ -z "$TUNNEL_URL" ]; then
    echo "  FAILED — check $LOG_DIR/tunnel.log"
    cat "$LOG_DIR/tunnel.log"
    exit 1
fi

WEBAPP_URL="${TUNNEL_URL}/static/terminal.html"
echo "  $TUNNEL_URL"

# ── 3. Configure bot with new URL ────────────────────
# Update .env (cross-platform sed)
if grep -q "AGENTSTACK_WEBAPP_URL" .env 2>/dev/null; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|AGENTSTACK_WEBAPP_URL=.*|AGENTSTACK_WEBAPP_URL=$WEBAPP_URL|" .env
    else
        sed -i "s|AGENTSTACK_WEBAPP_URL=.*|AGENTSTACK_WEBAPP_URL=$WEBAPP_URL|" .env
    fi
else
    echo "AGENTSTACK_WEBAPP_URL=$WEBAPP_URL" >> .env
fi

# Set Telegram menu button
if [ -n "$BOT_TOKEN" ]; then
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setChatMenuButton" \
        -H "Content-Type: application/json" \
        -d "{\"menu_button\":{\"type\":\"web_app\",\"text\":\"Terminal\",\"web_app\":{\"url\":\"${WEBAPP_URL}\"}}}" \
        > /dev/null 2>&1
    echo "  Menu button updated"
fi

# ── 4. Telegram bot ──────────────────────────────────
echo "[3/3] Telegram bot"
export AGENTSTACK_WEBAPP_URL="$WEBAPP_URL"
python3 -u bot.py > "$LOG_DIR/bot.log" 2>&1 &
BOT_PID=$!
sleep 2

if ! kill -0 $BOT_PID 2>/dev/null; then
    echo "  FAILED — check $LOG_DIR/bot.log"
    cat "$LOG_DIR/bot.log"
    exit 1
fi
echo "  OK (pid $BOT_PID)"

# ── Done ─────────────────────────────────────────────
echo ""
echo "=================================="
echo "  All systems go"
echo "=================================="
echo "  Web:      http://localhost:$PORT"
echo "  Tunnel:   $TUNNEL_URL"
echo "  Terminal: $WEBAPP_URL"
echo "  Logs:     $LOG_DIR/"
echo ""
echo "  Ctrl+C to stop"
echo "=================================="
echo ""

# Tail logs
tail -f "$LOG_DIR/bot.log" "$LOG_DIR/web.log" 2>/dev/null &
TAIL_PID=$!

wait $BOT_PID 2>/dev/null
echo "Bot exited."
