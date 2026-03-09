.PHONY: start stop sentinel setup install uninstall upgrade logs health status generate-configs

start:
	bash start.sh

stop:
	@kill $$(cat /tmp/agentstack/sentinel.pid 2>/dev/null) 2>/dev/null || true
	@pkill -f "web/server.py" 2>/dev/null || true
	@pkill -f "bot\.py" 2>/dev/null || true
	@pkill -f "cloudflared tunnel.*8765" 2>/dev/null || true
	@echo "Stopped."

sentinel:
	bash sentinel.sh

setup:
	bash setup.sh

install:
	bash install.sh

uninstall:
	@echo "Stopping services..."
	@$(MAKE) stop 2>/dev/null || true
	@echo "Removing agentstack command..."
	@rm -f $$HOME/.local/bin/agentstack
	@echo "Uninstalled. Project files remain in $(shell pwd)."
	@echo "To fully remove: rm -rf $(shell pwd)"

upgrade:
	git pull origin main
	pip install -q -r requirements.txt
	bash generate-configs.sh "$(shell pwd)"
	@echo "Upgraded. Run: make start"

generate-configs:
	bash generate-configs.sh "$(shell pwd)"

logs:
	tail -f /tmp/agentstack/*.log

health:
	@curl -s http://localhost:8765/health | python3 -m json.tool

status:
	@echo "=== Processes ==="
	@ps aux | grep -E "server\.py|bot\.py|cloudflared|sentinel" | grep -v grep || echo "  Nothing running"
	@echo ""
	@echo "=== Health ==="
	@curl -sf http://localhost:8765/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "  Web server not responding"
	@echo ""
	@echo "=== Sentinel ==="
	@tail -3 /tmp/agentstack/sentinel.log 2>/dev/null || echo "  Not running"
