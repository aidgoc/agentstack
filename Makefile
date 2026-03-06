.PHONY: start stop setup logs health status

start:
	bash start.sh

stop:
	pkill -f "agentstack/web/server.py" || true
	pkill -f "agentstack/bot.py" || true
	pkill -f "cloudflared tunnel.*8765" || true
	@echo "Stopped."

setup:
	bash setup.sh

logs:
	tail -f /tmp/agentstack/*.log

health:
	@curl -s http://localhost:8765/health | python3 -m json.tool

status:
	@echo "=== Processes ==="
	@ps aux | grep -E "agentstack|cloudflared" | grep -v grep || echo "  Nothing running"
	@echo ""
	@echo "=== Health ==="
	@curl -sf http://localhost:8765/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "  Web server not responding"
