#!/bin/bash
# AgentStack Sentinel — monitors, heals, and alerts
#
# Usage:
#   bash sentinel.sh          # run in foreground
#   bash sentinel.sh &        # run in background
#   nohup bash sentinel.sh &  # survive terminal close
#
# Monitors: web server, telegram bot, cloudflare tunnel, tmux, disk, memory
# Auto-fixes: restarts crashed services, clears stale locks, fixes port conflicts
# Alerts: sends Telegram messages on issues and recoveries

set -u
cd "$(dirname "$0")"

# ── Config ────────────────────────────────────────────
source .env 2>/dev/null || true
[ -f .venv/bin/activate ] && source .venv/bin/activate

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${OWNER_ID:-}"
PORT="${AGENTSTACK_PORT:-8765}"
CHECK_INTERVAL=30          # seconds between checks
HEALTH_TIMEOUT=5           # seconds for health check
MAX_RESTART_ATTEMPTS=3     # per service per hour
LOG_DIR="/tmp/agentstack"
SENTINEL_LOG="$LOG_DIR/sentinel.log"
STATE_FILE="$LOG_DIR/sentinel.state"

mkdir -p "$LOG_DIR"

# Track restart attempts (reset hourly)
declare -A restart_count
declare -A last_restart_hour
declare -A downtime_start

# ── Logging ───────────────────────────────────────────
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" | tee -a "$SENTINEL_LOG"
}

# ── Telegram Alert ────────────────────────────────────
alert() {
    local level="$1"  # INFO, WARN, CRIT, OK
    local msg="$2"
    local icon
    case "$level" in
        CRIT) icon="🔴" ;;
        WARN) icon="🟡" ;;
        OK)   icon="🟢" ;;
        *)    icon="🔵" ;;
    esac

    local text="${icon} *AgentStack Sentinel*
${msg}
_$(date '+%H:%M:%S')_"

    if [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ]; then
        curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
            -d chat_id="$CHAT_ID" \
            -d text="$text" \
            -d parse_mode="Markdown" \
            > /dev/null 2>&1
    fi
    log "[$level] $msg"
}

# ── Service Checks ────────────────────────────────────

check_web_server() {
    # Check 1: Health endpoint responds (most reliable check)
    local health
    health=$(curl -sf --max-time "$HEALTH_TIMEOUT" "http://localhost:$PORT/health" 2>/dev/null)
    if [ $? -ne 0 ]; then
        # Check if process exists at all
        if pgrep -f "web/server.py" > /dev/null 2>&1; then
            echo "unhealthy"
        else
            echo "dead"
        fi
        return
    fi

    echo "ok"
}

check_bot() {
    if ! pgrep -f "bot.py" > /dev/null 2>&1; then
        echo "dead"
        return
    fi

    # Check for 409 conflict — only in log lines from the last 60 seconds
    if [ -f "$LOG_DIR/bot.log" ]; then
        local log_age
        log_age=$(stat -c%Y "$LOG_DIR/bot.log" 2>/dev/null || stat -f%m "$LOG_DIR/bot.log" 2>/dev/null || echo 0)
        local now
        now=$(date +%s)
        # Only check if log was modified in the last 60 seconds
        if [ $((now - log_age)) -lt 60 ]; then
            local last3
            last3=$(tail -3 "$LOG_DIR/bot.log" 2>/dev/null)
            if echo "$last3" | grep -qi "409\|conflict\|terminated by other" 2>/dev/null; then
                echo "conflict"
                return
            fi
        fi
    fi

    echo "ok"
}

check_tunnel() {
    # Check if cloudflared process exists
    if ! pgrep -f "cloudflared tunnel.*$PORT" > /dev/null 2>&1; then
        echo "dead"
        return
    fi

    # Check if tunnel URL is accessible (via the current URL in .env)
    local webapp_url
    webapp_url=$(grep "AGENTSTACK_WEBAPP_URL" .env 2>/dev/null | cut -d= -f2-)
    if [ -n "$webapp_url" ]; then
        local tunnel_base
        tunnel_base=$(echo "$webapp_url" | sed 's|/static/.*||')
        local http_code
        http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${tunnel_base}/health" 2>/dev/null)
        if [ "$http_code" = "000" ] || [ "$http_code" = "502" ] || [ "$http_code" = "503" ] || [ "$http_code" = "530" ]; then
            # Process alive but URL dead — kill and restart
            echo "url_dead"
            return
        fi
    fi

    # Also verify the tunnel log URL matches .env (catches stale URL after process restart)
    local log_url
    log_url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG_DIR/tunnel.log" 2>/dev/null | tail -1)
    if [ -n "$log_url" ] && [ -n "$webapp_url" ]; then
        local env_base
        env_base=$(echo "$webapp_url" | sed 's|/static/.*||')
        if [ "$log_url" != "$env_base" ]; then
            # Tunnel URL changed but .env wasn't updated
            log "Tunnel URL mismatch: env=$env_base log=$log_url — syncing"
            local new_webapp="${log_url}/static/terminal.html"
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|AGENTSTACK_WEBAPP_URL=.*|AGENTSTACK_WEBAPP_URL=$new_webapp|" .env
            else
                sed -i "s|AGENTSTACK_WEBAPP_URL=.*|AGENTSTACK_WEBAPP_URL=$new_webapp|" .env
            fi
            # Update Telegram menu button
            if [ -n "$BOT_TOKEN" ]; then
                curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setChatMenuButton" \
                    -H "Content-Type: application/json" \
                    -d "{\"menu_button\":{\"type\":\"web_app\",\"text\":\"Terminal\",\"web_app\":{\"url\":\"${new_webapp}\"}}}" \
                    > /dev/null 2>&1
            fi
            alert "INFO" "Tunnel URL synced: $log_url"
        fi
    fi

    echo "ok"
}

check_tmux() {
    if ! command -v tmux &>/dev/null; then
        echo "missing"
        return
    fi

    # Check if tmux server is responsive
    if ! tmux list-sessions > /dev/null 2>&1; then
        echo "no_sessions"
        return
    fi

    echo "ok"
}

check_disk() {
    local usage
    usage=$(df -h / | awk 'NR==2 {gsub(/%/,""); print $5}')
    if [ "$usage" -gt 95 ]; then
        echo "critical:${usage}%"
    elif [ "$usage" -gt 90 ]; then
        echo "warning:${usage}%"
    else
        echo "ok:${usage}%"
    fi
}

check_memory() {
    local available
    available=$(free -m 2>/dev/null | awk '/^Mem:/ {print $7}')
    if [ -z "$available" ]; then
        # macOS
        available=$(vm_stat 2>/dev/null | awk '/Pages free/ {gsub(/\./,""); print int($3*4096/1024/1024)}')
    fi

    if [ -n "$available" ] && [ "$available" -lt 200 ]; then
        echo "critical:${available}MB"
    elif [ -n "$available" ] && [ "$available" -lt 500 ]; then
        echo "warning:${available}MB"
    else
        echo "ok:${available:-?}MB"
    fi
}

# ── Fix Actions ───────────────────────────────────────

can_restart() {
    local service="$1"
    local hour
    hour=$(date +%H)

    if [ "${last_restart_hour[$service]:-}" != "$hour" ]; then
        restart_count[$service]=0
        last_restart_hour[$service]="$hour"
    fi

    if [ "${restart_count[$service]:-0}" -ge "$MAX_RESTART_ATTEMPTS" ]; then
        return 1
    fi
    return 0
}

track_restart() {
    local service="$1"
    restart_count[$service]=$(( ${restart_count[$service]:-0} + 1 ))
    log "Restart #${restart_count[$service]} for $service this hour"
}

fix_web_server() {
    local status="$1"

    if ! can_restart "web"; then
        alert "CRIT" "Web server ($status) — max restarts exceeded this hour. Manual intervention needed."
        return 1
    fi

    case "$status" in
        dead)
            alert "WARN" "Web server is dead. Restarting..."
            ;;
        unhealthy)
            alert "WARN" "Web server not responding to health checks. Restarting..."
            pkill -f "web/server.py" 2>/dev/null
            sleep 2
            ;;
        port_dead)
            alert "WARN" "Port $PORT not listening. Clearing and restarting..."
            pkill -f "web/server.py" 2>/dev/null
            fuser -k "${PORT}/tcp" 2>/dev/null || true
            sleep 2
            ;;
    esac

    python3 -u web/server.py > "$LOG_DIR/web.log" 2>&1 &
    track_restart "web"
    sleep 3

    if check_web_server | grep -q "ok"; then
        alert "OK" "Web server recovered."
        unset downtime_start[web]
        return 0
    else
        alert "CRIT" "Web server restart failed."
        return 1
    fi
}

fix_bot() {
    local status="$1"

    if ! can_restart "bot"; then
        alert "CRIT" "Bot ($status) — max restarts exceeded this hour."
        return 1
    fi

    case "$status" in
        dead)
            alert "WARN" "Telegram bot is dead. Restarting..."
            ;;
        conflict)
            alert "WARN" "Bot 409 conflict — killing all instances and clearing polling..."
            pkill -f "bot\.py" 2>/dev/null
            sleep 2
            # Clear stale polling
            if [ -n "$BOT_TOKEN" ]; then
                curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates?offset=-1&timeout=0" > /dev/null 2>&1
            fi
            sleep 3
            ;;
        errors)
            alert "WARN" "Bot has recent errors. Restarting..."
            pkill -f "bot\.py" 2>/dev/null
            sleep 2
            ;;
    esac

    export AGENTSTACK_WEBAPP_URL=$(grep "AGENTSTACK_WEBAPP_URL" .env 2>/dev/null | cut -d= -f2-)
    python3 -u bot.py > "$LOG_DIR/bot.log" 2>&1 &
    track_restart "bot"
    sleep 3

    if check_bot | grep -q "ok"; then
        alert "OK" "Telegram bot recovered."
        unset downtime_start[bot]
        return 0
    else
        alert "CRIT" "Bot restart failed."
        return 1
    fi
}

fix_tunnel() {
    local status="$1"

    if ! can_restart "tunnel"; then
        alert "CRIT" "Tunnel ($status) — max restarts exceeded this hour."
        return 1
    fi

    alert "WARN" "Cloudflare tunnel $status. Restarting tunnel..."

    pkill -f "cloudflared tunnel.*$PORT" 2>/dev/null
    sleep 2

    cloudflared tunnel --url "http://localhost:$PORT" > "$LOG_DIR/tunnel.log" 2>&1 &
    track_restart "tunnel"

    # Wait for new tunnel URL
    local new_url=""
    for i in $(seq 1 40); do
        new_url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG_DIR/tunnel.log" 2>/dev/null | head -1)
        [ -n "$new_url" ] && break
        sleep 0.5
    done

    if [ -z "$new_url" ]; then
        alert "CRIT" "Tunnel failed to establish. Check logs."
        return 1
    fi

    local webapp_url="${new_url}/static/terminal.html"

    # Update .env
    if grep -q "AGENTSTACK_WEBAPP_URL" .env 2>/dev/null; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|AGENTSTACK_WEBAPP_URL=.*|AGENTSTACK_WEBAPP_URL=$webapp_url|" .env
        else
            sed -i "s|AGENTSTACK_WEBAPP_URL=.*|AGENTSTACK_WEBAPP_URL=$webapp_url|" .env
        fi
    else
        echo "AGENTSTACK_WEBAPP_URL=$webapp_url" >> .env
    fi

    # Update Telegram menu button
    if [ -n "$BOT_TOKEN" ]; then
        curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setChatMenuButton" \
            -H "Content-Type: application/json" \
            -d "{\"menu_button\":{\"type\":\"web_app\",\"text\":\"Terminal\",\"web_app\":{\"url\":\"${webapp_url}\"}}}" \
            > /dev/null 2>&1
    fi

    alert "OK" "Tunnel recovered: $new_url"
    unset downtime_start[tunnel]
    return 0
}

cleanup_logs() {
    # Rotate logs if they get too big (>50MB)
    for logfile in "$LOG_DIR"/*.log; do
        if [ -f "$logfile" ]; then
            local size
            size=$(stat -f%z "$logfile" 2>/dev/null || stat -c%s "$logfile" 2>/dev/null || echo 0)
            if [ "$size" -gt 52428800 ]; then
                tail -10000 "$logfile" > "${logfile}.tmp"
                mv "${logfile}.tmp" "$logfile"
                log "Rotated $logfile (was ${size} bytes)"
            fi
        fi
    done
}

cleanup_tmux() {
    # Kill zombie tmux sessions (older than 24 hours with no activity)
    if command -v tmux &>/dev/null; then
        local count
        count=$(tmux list-sessions 2>/dev/null | grep -c "^as_" || echo 0)
        if [ "$count" -gt 20 ]; then
            log "Too many tmux sessions ($count). Consider cleaning up."
            alert "WARN" "Found $count tmux sessions. Run: tmux kill-server to clean up."
        fi
    fi
}

# ── Main Loop ─────────────────────────────────────────

log "Sentinel started (PID $$)"
alert "INFO" "Sentinel started. Monitoring web, bot, tunnel, system."

# Save PID for management
echo $$ > "$LOG_DIR/sentinel.pid"

iteration=0

trap 'log "Sentinel stopped"; alert "INFO" "Sentinel stopped."; rm -f "$LOG_DIR/sentinel.pid"; exit 0' INT TERM

while true; do
    iteration=$((iteration + 1))

    # ── Web Server ──────────────────
    web_status=$(check_web_server)
    if [ "$web_status" != "ok" ]; then
        if [ -z "${downtime_start[web]:-}" ]; then
            downtime_start[web]=$(date +%s)
        fi
        fix_web_server "$web_status"
    fi

    # ── Telegram Bot ────────────────
    bot_status=$(check_bot)
    if [ "$bot_status" != "ok" ]; then
        if [ -z "${downtime_start[bot]:-}" ]; then
            downtime_start[bot]=$(date +%s)
        fi
        fix_bot "$bot_status"
    fi

    # ── Cloudflare Tunnel ───────────
    tunnel_status=$(check_tunnel)
    if [ "$tunnel_status" != "ok" ]; then
        if [ -z "${downtime_start[tunnel]:-}" ]; then
            downtime_start[tunnel]=$(date +%s)
        fi
        fix_tunnel "$tunnel_status"
    fi

    # ── System Checks (every 5 min) ─
    if [ $((iteration % 10)) -eq 0 ]; then
        disk_status=$(check_disk)
        case "$disk_status" in
            critical:*) alert "CRIT" "Disk usage ${disk_status#*:} — server may crash" ;;
            warning:*)  alert "WARN" "Disk usage ${disk_status#*:}" ;;
        esac

        mem_status=$(check_memory)
        case "$mem_status" in
            critical:*) alert "CRIT" "Low memory: ${mem_status#*:} available" ;;
            warning:*)  alert "WARN" "Memory getting low: ${mem_status#*:} available" ;;
        esac

        cleanup_logs
        cleanup_tmux
    fi

    # ── Heartbeat (every 30 min) ────
    if [ $((iteration % 60)) -eq 0 ]; then
        local_sessions=$(curl -sf "http://localhost:$PORT/health" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d[\"sessions\"]} sessions, uptime {d[\"uptime\"]//3600}h')" 2>/dev/null || echo "unknown")
        log "Heartbeat: web=$web_status bot=$bot_status tunnel=$tunnel_status | $local_sessions"
    fi

    sleep "$CHECK_INTERVAL"
done
