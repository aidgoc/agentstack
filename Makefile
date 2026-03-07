.PHONY: start stop sentinel setup logs health status

# Start all services (web server + tunnel + bot)
start:
	bash start.sh

# Stop everything including sentinel
stop:
	@kill $$(cat /tmp/agentstack/sentinel.pid 2>/dev/null) 2>/dev/null || true
	@pkill -f "web/server.py" 2>/dev/null || true
	@pkill -f "bot\.py" 2>/dev/null || true
	@pkill -f "cloudflared tunnel.*8765" 2>/dev/null || true
	@echo "Stopped."

# Start sentinel watchdog (monitors + auto-heals + alerts)
sentinel:
	bash sentinel.sh

# First-time setup (install deps + configure)
setup:
	bash setup.sh

# Tail all logs
logs:
	tail -f /tmp/agentstack/*.log

# Health check
health:
	@curl -s http://localhost:8765/health | python3 -m json.tool

# Full status overview
status:
	@echo "=== Processes ==="
	@ps aux | grep -E "server\.py|bot\.py|cloudflared|sentinel" | grep -v grep || echo "  Nothing running"
	@echo ""
	@echo "=== Health ==="
	@curl -sf http://localhost:8765/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "  Web server not responding"
	@echo ""
	@echo "=== Sentinel ==="
	@tail -3 /tmp/agentstack/sentinel.log 2>/dev/null || echo "  Not running"
