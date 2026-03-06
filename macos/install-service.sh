#!/bin/bash
# Install AgentStack as a macOS launchd service (auto-start on login)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTSTACK_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_SRC="$SCRIPT_DIR/com.agentstack.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.agentstack.plist"
LOG_DIR="$HOME/Library/Logs/agentstack"

if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "This script is for macOS only."
    exit 1
fi

# Unload if already installed
launchctl unload "$PLIST_DST" 2>/dev/null || true

# Create log directory
mkdir -p "$LOG_DIR"

# Generate plist with actual paths
sed -e "s|AGENTSTACK_DIR|$AGENTSTACK_DIR|g" \
    -e "s|HOME_DIR|$HOME|g" \
    "$PLIST_SRC" > "$PLIST_DST"

# Load
launchctl load "$PLIST_DST"

echo "AgentStack service installed."
echo "  Plist: $PLIST_DST"
echo "  Logs:  $LOG_DIR/"
echo ""
echo "Commands:"
echo "  Stop:    launchctl unload $PLIST_DST"
echo "  Start:   launchctl load $PLIST_DST"
echo "  Logs:    tail -f $LOG_DIR/*.log"
