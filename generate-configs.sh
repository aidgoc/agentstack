#!/bin/bash
# generate-configs.sh — Generate agents.json and mcp-configs/ from templates
#
# Usage: bash generate-configs.sh [/path/to/agentstack]
# Defaults to current directory if no argument given.

set -e

AGENTSTACK_HOME="${1:-$(pwd)}"

# Validate
if [ ! -f "$AGENTSTACK_HOME/config-templates/agents.template.json" ]; then
    echo "Error: config-templates/agents.template.json not found in $AGENTSTACK_HOME"
    exit 1
fi

echo "Generating configs for: $AGENTSTACK_HOME"

# Generate agents.json
sed "s|{{AGENTSTACK_HOME}}|${AGENTSTACK_HOME}|g" \
    "$AGENTSTACK_HOME/config-templates/agents.template.json" > "$AGENTSTACK_HOME/agents.json"
echo "  ✓ agents.json"

# Generate mcp-configs/
mkdir -p "$AGENTSTACK_HOME/mcp-configs"
for tmpl in "$AGENTSTACK_HOME/config-templates/mcp/"*.template.json; do
    [ -f "$tmpl" ] || continue
    name=$(basename "$tmpl" .template.json)
    sed "s|{{AGENTSTACK_HOME}}|${AGENTSTACK_HOME}|g" \
        "$tmpl" > "$AGENTSTACK_HOME/mcp-configs/${name}.json"
    echo "  ✓ mcp-configs/${name}.json"
done

# Create shared/ directory tree
for dir in research research/trends drafts social marketing designs analysis crm_data forge forge/templates forge/generated-apps forge/knowledge forge/skills; do
    mkdir -p "$AGENTSTACK_HOME/shared/$dir"
done
echo "  ✓ shared/ workspace"

echo "Done."
