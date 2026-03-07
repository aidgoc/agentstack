#!/bin/bash
# ============================================================================
# AgentStack Sentinel — status monitor with Telegram alerts (read-only)
# ============================================================================
#
# Usage:
#   bash sentinel.sh            # one-shot status check + alert
#   bash sentinel.sh --watch    # continuous monitoring (every 5 min)
#
# Does NOT restart or fix anything — just reports status to Telegram.
# ============================================================================

cd "$(dirname "$0")"
source .env 2>/dev/null || true

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${OWNER_ID:-}"
PORT="${AGENTSTACK_PORT:-8765}"
LOG_DIR="/tmp/agentstack"
WATCH_MODE=false

[ "${1:-}" = "--watch" ] && WATCH_MODE=true

# ── Telegram Alert ────────────────────────────────────
alert() {
    local msg="$1"
    if [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ]; then
        curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
            -d chat_id="$CHAT_ID" \
            -d text="$msg" \
            -d parse_mode="Markdown" \
            > /dev/null 2>&1
    fi
    echo "$msg"
}

# ── Status Check ──────────────────────────────────────
check_status() {
    local issues=""
    local ok_count=0

    # Web server
    if curl -sf --max-time 5 "http://localhost:$PORT/health" > /dev/null 2>&1; then
        ok_count=$((ok_count + 1))
        web="ok"
    else
        web="DOWN"
        issues="${issues}\n- Web server not responding"
    fi

    # Bot
    if pgrep -f "bot\.py" > /dev/null 2>&1; then
        ok_count=$((ok_count + 1))
        bot="ok"
    else
        bot="DOWN"
        issues="${issues}\n- Telegram bot not running"
    fi

    # Tunnel
    if pgrep -f "cloudflared" > /dev/null 2>&1; then
        ok_count=$((ok_count + 1))
        tunnel="ok"
    else
        tunnel="DOWN"
        issues="${issues}\n- Cloudflare tunnel not running"
    fi

    # Uptime
    local uptime="?"
    local sessions="?"
    local health
    health=$(curl -sf --max-time 3 "http://localhost:$PORT/health" 2>/dev/null)
    if [ -n "$health" ]; then
        uptime=$(echo "$health" | python3 -c "import sys,json; d=json.load(sys.stdin); h=d['uptime']//3600; m=(d['uptime']%3600)//60; print(f'{h}h {m}m')" 2>/dev/null || echo "?")
        sessions=$(echo "$health" | python3 -c "import sys,json; print(json.load(sys.stdin)['sessions'])" 2>/dev/null || echo "?")
    fi

    # Disk
    local disk
    disk=$(df -h / | awk 'NR==2 {print $5}')

    # Memory
    local mem
    mem=$(free -m 2>/dev/null | awk '/^Mem:/ {printf "%dMB free", $7}' || echo "?")

    # Build message
    if [ -n "$issues" ]; then
        alert "$(printf "🔴 *AgentStack Status*\n\nWeb: %s | Bot: %s | Tunnel: %s\n\nIssues:%b\n\n_$(date '+%H:%M:%S')_" "$web" "$bot" "$tunnel" "$issues")"
    else
        alert "$(printf "🟢 *AgentStack Status*\n\nWeb: %s | Bot: %s | Tunnel: %s\nSessions: %s | Uptime: %s\nDisk: %s | %s\n\n_$(date '+%H:%M:%S')_" "$web" "$bot" "$tunnel" "$sessions" "$uptime" "$disk" "$mem")"
    fi
}

# ── Run ───────────────────────────────────────────────
if [ "$WATCH_MODE" = true ]; then
    echo "Sentinel watching (every 1 hour). Ctrl+C to stop."
    while true; do
        check_status
        sleep 3600
    done
else
    check_status
fi
