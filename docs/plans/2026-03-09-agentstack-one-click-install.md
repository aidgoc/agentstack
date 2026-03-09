# AgentStack One-Click Install — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make AgentStack installable by non-technical users with a single `curl | bash` command on Linux or macOS, or `docker compose up` on any platform.

**Architecture:** Replace hardcoded paths with `{{AGENTSTACK_HOME}}` templates. Add `config-templates/` directory with agent and MCP config templates. Rewrite `install.sh` and `setup.sh` to auto-detect OS, install deps, guide through Telegram/Claude setup with deep links, and auto-generate all config files. Update Docker setup for parity.

**Tech Stack:** Bash (installer), sed (template substitution), existing Python/FastAPI stack (unchanged)

---

### Task 1: Create config-templates directory with agent and MCP templates

**Files:**
- Create: `config-templates/agents.template.json`
- Create: `config-templates/mcp/atlas.template.json`
- Create: `config-templates/mcp/scribe.template.json`
- Create: `config-templates/mcp/trendy.template.json`
- Create: `config-templates/mcp/social.template.json`
- Create: `config-templates/mcp/marketing.template.json`
- Create: `config-templates/mcp/designer.template.json`
- Create: `config-templates/mcp/analyst.template.json`
- Create: `config-templates/mcp/crm.template.json`
- Create: `config-templates/mcp/dev.template.json`
- Create: `config-templates/mcp/forge.template.json`

**Step 1: Create agents.template.json**

This is the current `agents.json` but with all absolute paths replaced by `{{AGENTSTACK_HOME}}` and client-specific content (HEFT USA, HNG details) replaced with generic placeholders.

```json
{
  "agents": {
    "atlas": {
      "description": "Deep research analyst. Searches web, X, Reddit. Outputs research reports.",
      "prompt": "You are Atlas, a deep research analyst. Your job is to research topics thoroughly using web search, analyze trends, and produce structured research reports. Save all findings to {{AGENTSTACK_HOME}}/shared/research/ as markdown files. Be thorough, cite sources, and identify patterns.",
      "model": "opus",
      "cwd": "{{AGENTSTACK_HOME}}/shared/research",
      "mcp_config": "{{AGENTSTACK_HOME}}/mcp-configs/atlas.json"
    },
    "scribe": {
      "description": "Copywriter. Takes research and writes content matched to brand voice.",
      "prompt": "You are Scribe, a copywriter. Read research reports from {{AGENTSTACK_HOME}}/shared/research/ and write engaging content drafts. Match the brand voice and style. Save drafts to {{AGENTSTACK_HOME}}/shared/drafts/ as markdown files. Focus on clarity, hooks, and actionable insights.",
      "model": "sonnet",
      "cwd": "{{AGENTSTACK_HOME}}/shared/drafts"
    },
    "trendy": {
      "description": "Trend scout. Monitors X and Reddit for viral patterns and opportunities.",
      "prompt": "You are Trendy, a trend scout. Search X, Reddit, and the web for trending topics, viral patterns, and competitor gaps. Report findings in structured format. Save trend reports to {{AGENTSTACK_HOME}}/shared/research/trends/ as markdown files.",
      "model": "sonnet",
      "cwd": "{{AGENTSTACK_HOME}}/shared/research"
    },
    "social": {
      "description": "Social media manager. Creates platform-optimized posts for LinkedIn, Instagram, X, Facebook.",
      "prompt": "You are Social, the social media manager. Create platform-optimized posts for LinkedIn, Instagram, X (Twitter), and Facebook.\n\nPlatform rules: LinkedIn = professional/long-form, Instagram = visual/hashtags, X = punchy/short, Facebook = community/engagement.\n\nRead research from {{AGENTSTACK_HOME}}/shared/research/ for trends to reference.\n\nSave all posts to {{AGENTSTACK_HOME}}/shared/social/ as markdown files. Name format: YYYY-MM-DD-platform-topic.md\n\nFor each post include: platform, caption, hashtags, best posting time, and engagement hooks.",
      "model": "sonnet",
      "cwd": "{{AGENTSTACK_HOME}}/shared/social",
      "mcp_config": "{{AGENTSTACK_HOME}}/mcp-configs/social.json"
    },
    "marketing": {
      "description": "Marketing strategist. Builds campaigns, funnels, brand positioning, and lead gen.",
      "prompt": "You are Marketing, the head of marketing strategy. Your capabilities:\n1. STRATEGY: Build marketing plans, define target audiences, competitive positioning\n2. CAMPAIGNS: Email sequences, ad copy, landing page copy\n3. LEAD GEN: Lead magnets, proposal templates, case studies\n4. BRAND: Maintain brand voice and messaging consistency\n5. ANALYSIS: Competitor research, gap identification, market opportunities\n6. CONTENT PLANNING: Coordinate with Social agent and Scribe\n\nSave all work to {{AGENTSTACK_HOME}}/shared/marketing/ as markdown files. Be specific with numbers, timelines, and budgets. No fluff — actionable plans only.",
      "model": "sonnet",
      "cwd": "{{AGENTSTACK_HOME}}/shared/marketing",
      "mcp_config": "{{AGENTSTACK_HOME}}/mcp-configs/marketing.json"
    },
    "designer": {
      "description": "Graphic designer. Creates SVG/HTML graphics, AI images, and visual assets.",
      "prompt": "You are Designer, the in-house graphic designer. You create visual assets using code and AI image APIs.\n\nCapabilities:\n1. SVG GRAPHICS: Logos, icons, infographics, social media graphics\n2. HTML/CSS: Email templates, landing pages, one-pagers, flyers\n3. DATA VIZ: Charts, graphs, project timelines\n4. AI IMAGE GENERATION: Via API calls (Gemini, OpenRouter, FLUX)\n\nSocial media sizes: Instagram (1080x1080), Story (1080x1920), LinkedIn (1200x627), Facebook (1200x630)\n\nSave all designs to {{AGENTSTACK_HOME}}/shared/designs/\nRead briefs from {{AGENTSTACK_HOME}}/shared/social/ and {{AGENTSTACK_HOME}}/shared/marketing/",
      "model": "sonnet",
      "cwd": "{{AGENTSTACK_HOME}}/shared/designs",
      "mcp_config": "{{AGENTSTACK_HOME}}/mcp-configs/designer.json"
    },
    "analyst": {
      "description": "Business analyst. P&L, cash flow, job costing, ROI analysis using SQLite.",
      "prompt": "You are Analyst, the business and financial analyst. Your capabilities:\n1. JOB COSTING: Calculate project costs (labor, materials, equipment, overhead)\n2. P&L ANALYSIS: Revenue tracking, expense categorization, profit margins\n3. CASH FLOW: Forecast cash flow, track receivables, flag issues\n4. KPIs: Track key metrics, benchmarks, productivity indicators\n\nYou have access to SQLite for structured data at {{AGENTSTACK_HOME}}/shared/analysis/data.db\n\nWhen doing analysis: show your math, use tables, provide actionable recommendations.\n\nSave all analysis to {{AGENTSTACK_HOME}}/shared/analysis/ as markdown files.",
      "model": "opus",
      "cwd": "{{AGENTSTACK_HOME}}/shared/analysis",
      "mcp_config": "{{AGENTSTACK_HOME}}/mcp-configs/analyst.json"
    },
    "crm": {
      "description": "CRM agent. Manages contacts, deals, follow-ups.",
      "prompt": "You are CRM Agent. Manage contacts, deals, and follow-ups stored in {{AGENTSTACK_HOME}}/shared/crm_data/. Track interactions, set reminders, and maintain a pipeline. Use markdown files for data storage. Keep everything organized and actionable.",
      "model": "sonnet",
      "cwd": "{{AGENTSTACK_HOME}}/shared/crm_data"
    },
    "dev": {
      "description": "Senior developer. Reviews code, ships features, fixes bugs.",
      "prompt": "You are a senior developer. Review code, identify issues, build features, and ship pull requests. Be thorough with testing and security.",
      "model": "opus",
      "cwd": "~"
    },
    "forge": {
      "description": "Frappe app builder. Generates complete Frappe apps from natural language.",
      "prompt": "You are Frappe Forge, an AI agent that generates complete, deployable Frappe Framework v15 applications from natural language business descriptions.\n\nYour pipeline:\n1. UNDERSTAND — Ask clarifying questions about the business domain\n2. ARCHITECT — Design the data model (DocTypes, relationships, permissions)\n3. GENERATE — Write all app files (JSON schemas, Python controllers, JS client scripts, hooks.py)\n4. INSTALL — Run bench commands to install, migrate, build, and test\n5. ITERATE — Modify existing apps when requirements change\n\nReference your CLAUDE.md for complete Frappe schema reference.\nReference templates at {{AGENTSTACK_HOME}}/shared/forge/templates/ for code patterns.\n\nBench location: ~/frappe-bench/\nGenerated apps go to: ~/frappe-bench/apps/\nDev site: dev.localhost",
      "model": "opus",
      "cwd": "{{AGENTSTACK_HOME}}/shared/forge",
      "mcp_config": "{{AGENTSTACK_HOME}}/mcp-configs/forge.json",
      "flags": "--dangerously-skip-permissions"
    }
  },
  "default_agent": "atlas"
}
```

**Step 2: Create MCP templates**

Each file in `config-templates/mcp/` follows the same pattern. Example `atlas.template.json`:
```json
{
  "mcpServers": {
    "fetch": {
      "command": "uvx",
      "args": ["mcp-server-fetch"],
      "env": {}
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem",
               "{{AGENTSTACK_HOME}}/shared/research"]
    }
  }
}
```

Create one template per agent based on current mcp-configs. For agents without mcp_config (scribe, trendy, crm, dev), no MCP template needed.

MCP templates by agent:
- `atlas.template.json` — fetch + filesystem (shared/research)
- `social.template.json` — fetch + filesystem (shared/social, shared/research, shared/drafts)
- `marketing.template.json` — fetch + filesystem (shared/marketing, shared/social, shared/research)
- `designer.template.json` — fetch + filesystem (shared/designs, shared/social, shared/marketing) + puppeteer
- `analyst.template.json` — fetch + filesystem (shared/analysis, shared) + sqlite (shared/analysis/data.db)
- `forge.template.json` — fetch + filesystem (shared/forge, shared/research)

Note: forge template does NOT include `~/frappe-bench/apps` — that path only exists if Forge is set up. The Forge setup step adds it.

**Step 3: Commit**

```bash
git add config-templates/
git commit -m "feat: add config templates with path placeholders for portable install"
```

---

### Task 2: Write the generate-configs helper script

**Files:**
- Create: `generate-configs.sh`

**Step 1: Write the script**

This script takes `AGENTSTACK_HOME` (defaults to pwd), reads templates, substitutes `{{AGENTSTACK_HOME}}`, and writes output files.

```bash
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
```

**Step 2: Commit**

```bash
git add generate-configs.sh
git commit -m "feat: add generate-configs.sh for portable config generation"
```

---

### Task 3: Rewrite install.sh with guided setup and deep links

**Files:**
- Modify: `install.sh`

**Step 1: Rewrite install.sh**

The new installer:
1. Detects OS (macOS/Linux distro) and architecture
2. Installs system deps (brew/apt/dnf/pacman) — with `sudo` only on Linux
3. Opens Telegram deep links for bot setup (`tg://resolve?domain=BotFather`)
4. Validates bot token by calling Telegram API (`getMe`)
5. Opens deep link for user ID (`tg://resolve?domain=userinfobot`)
6. Claude Code auth (API key prompt or skip for OAuth)
7. Runs `generate-configs.sh` to create agents.json + mcp-configs/
8. Optional Frappe Forge setup prompt
9. Creates `agentstack` CLI command in `~/.local/bin/`
10. Optional auto-start (systemd/launchd)
11. Launches and runs health check

Key improvements over current:
- `open`/`xdg-open` deep links to @BotFather and @userinfobot
- Bot token validation: `curl -s https://api.telegram.org/bot$TOKEN/getMe` — check `.ok == true`
- User ID format validation: must be numeric
- Progress display with step numbers and checkmarks
- `generate-configs.sh` called instead of manual config

The full script is ~400 lines. Key new sections:

```bash
# ── Telegram deep links ───────────────────────────
open_link() {
    if [ "$PLATFORM" = "mac" ]; then
        open "$1" 2>/dev/null || true
    else
        xdg-open "$1" 2>/dev/null || true
    fi
}

# Bot setup with deep link
echo ""
echo "  ─── Telegram Bot Setup ───"
echo ""
echo "  Step 1: Create a bot with @BotFather"
echo "    Opening Telegram..."
open_link "https://t.me/BotFather"
echo "    1. Send /newbot to @BotFather"
echo "    2. Choose a name and username for your bot"
echo "    3. Copy the token it gives you"
echo ""
read -p "  Paste your bot token: " BOT_TOKEN

# Validate token
if [ -z "$BOT_TOKEN" ]; then
    echo "  No token provided. Run this again when ready."
    exit 1
fi
GETME=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getMe")
if echo "$GETME" | grep -q '"ok":true'; then
    BOT_NAME=$(echo "$GETME" | grep -o '"username":"[^"]*"' | cut -d'"' -f4)
    echo "  ✓ Token valid! Bot: @${BOT_NAME}"
else
    echo "  ✗ Invalid token. Check and try again."
    exit 1
fi

# User ID with deep link
echo ""
echo "  Step 2: Get your Telegram user ID"
echo "    Opening @userinfobot..."
open_link "https://t.me/userinfobot"
echo "    Send any message — it will reply with your ID."
echo ""
read -p "  Your Telegram user ID: " OWNER_ID
if ! [[ "$OWNER_ID" =~ ^[0-9]+$ ]]; then
    echo "  ✗ User ID must be a number. Try again."
    exit 1
fi
echo "  ✓ User ID saved"
```

**Step 2: Commit**

```bash
git add install.sh
git commit -m "feat: rewrite install.sh with guided setup, deep links, and validation"
```

---

### Task 4: Rewrite setup.sh to use generate-configs.sh

**Files:**
- Modify: `setup.sh`

**Step 1: Update setup.sh**

The `setup.sh` is the git-clone path (for users who clone the repo manually). It should:
1. Call existing dep install + configure + claude_auth functions (keep those)
2. After `.env` is written, call `bash generate-configs.sh` to create agents.json + mcp-configs/
3. Remove the hardcoded xdg-open interceptor section (move to a separate optional step)

Key change — add after the `configure` function call:

```bash
# ── Generate agent configs ─────────────────────────
echo ""
echo "Generating agent configurations..."
bash generate-configs.sh "$(pwd)"
```

**Step 2: Commit**

```bash
git add setup.sh
git commit -m "feat: update setup.sh to use generate-configs.sh"
```

---

### Task 5: Update agents.example.json

**Files:**
- Modify: `agents.example.json`

**Step 1: Update the example**

Replace the current `agents.example.json` with a cleaner version that uses relative paths and clearly documents the format. This is a reference file for users who want to understand the structure — the actual `agents.json` is generated by `generate-configs.sh`.

```json
{
  "agents": {
    "atlas": {
      "description": "Deep research analyst. Searches web, X, Reddit. Outputs research reports.",
      "prompt": "You are Atlas, a deep research analyst...",
      "model": "opus",
      "cwd": "shared/research",
      "mcp_config": "mcp-configs/atlas.json"
    },
    "dev": {
      "description": "Senior developer. Reviews code, ships features, fixes bugs.",
      "prompt": "You are a senior developer...",
      "model": "opus",
      "cwd": "~"
    }
  },
  "default_agent": "atlas"
}
```

Add a comment header explaining the format (JSON doesn't support comments, so add a `"_comment"` field or document in README).

**Step 2: Commit**

```bash
git add agents.example.json
git commit -m "docs: update agents.example.json with cleaner format"
```

---

### Task 6: Update Dockerfile and docker-compose.yml

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`

**Step 1: Update Dockerfile**

Add `generate-configs.sh` call and Node.js install (needed for MCP servers via npx):

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tmux curl ca-certificates git && \
    rm -rf /var/lib/apt/lists/*

# Node.js (for npx MCP servers)
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# cloudflared
RUN ARCH=$(dpkg --print-architecture) && \
    curl -L "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}" \
    -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared

# Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code 2>/dev/null || true
ENV PATH="/root/.local/bin:$PATH"

# uv (for uvx MCP servers)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x start.sh generate-configs.sh

# Generate configs at build time (can be overridden by volume mounts)
RUN bash generate-configs.sh /app

RUN mkdir -p /app/shared

EXPOSE 8765

CMD ["bash", "start.sh"]
```

**Step 2: Update docker-compose.yml**

```yaml
services:
  agentstack:
    build: .
    container_name: agentstack
    restart: unless-stopped
    env_file: .env
    ports:
      - "8765:8765"
    volumes:
      # Persist shared workspace (agent outputs)
      - ./shared:/app/shared
      # Mount Claude Code auth (API key or OAuth credentials)
      - ~/.claude:/root/.claude
      # Override generated configs if customized
      - ./agents.json:/app/agents.json
      - ./mcp-configs:/app/mcp-configs
    environment:
      - AGENTSTACK_PORT=8765
```

**Step 3: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: update Docker setup with Node.js, uv, and config generation"
```

---

### Task 7: Update Makefile with install/uninstall/upgrade targets

**Files:**
- Modify: `Makefile`

**Step 1: Add new targets**

```makefile
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
```

**Step 2: Commit**

```bash
git add Makefile
git commit -m "feat: add install/uninstall/upgrade/generate-configs to Makefile"
```

---

### Task 8: Update .env.example with clearer docs

**Files:**
- Modify: `.env.example`

**Step 1: Rewrite .env.example**

```bash
# ─── AgentStack Configuration ───────────────────────
#
# Copy this file to .env and fill in the values:
#   cp .env.example .env
#
# Or let the installer do it for you:
#   curl -sL https://raw.githubusercontent.com/aidgoc/agentstack/main/install.sh | bash

# ── Required ────────────────────────────────────────
# Get a bot token: open Telegram → message @BotFather → send /newbot
TELEGRAM_BOT_TOKEN=

# Get your user ID: open Telegram → message @userinfobot → send /start
OWNER_ID=

# ── Claude Code Authentication ─────────────────────
# Option A: API key (recommended — works on servers, no browser needed)
# Get one at: https://console.anthropic.com/settings/keys
# ANTHROPIC_API_KEY=sk-ant-...
#
# Option B: OAuth login (requires browser access)
# Leave ANTHROPIC_API_KEY blank. SSH into the machine and run: claude
# Complete the browser login once. Don't do this from the Telegram terminal.

# ── Optional ────────────────────────────────────────
# AGENTSTACK_PORT=8765           # Web server port (default: 8765)
# WEB_TOKEN_TTL=14400            # Session token lifetime in seconds (default: 4 hours)

# ── Auto-set (do not edit) ──────────────────────────
# AGENTSTACK_WEBAPP_URL=         # Set by start.sh on each launch
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: rewrite .env.example with clearer instructions"
```

---

### Task 9: Rewrite README.md for end users

**Files:**
- Modify: `README.md`

**Step 1: Rewrite README**

Keep the same structure but improve:
- Lead with the one-liner install command
- Add "What you need" section (Telegram account, Anthropic account)
- Update agent table to include all 10 agents (add forge)
- Add Docker section with clearer instructions
- Add Troubleshooting section
- Remove developer-facing details (architecture diagram stays, it's useful)

Key additions:

```markdown
## What You Need

- A computer (Mac or Linux) that stays on
- A Telegram account
- An Anthropic account ([sign up free](https://console.anthropic.com))

## Install (1 command)

```bash
curl -sL https://raw.githubusercontent.com/aidgoc/agentstack/main/install.sh | bash
```

The installer walks you through everything:
1. Installs dependencies automatically
2. Opens Telegram to help you create a bot
3. Sets up Claude Code authentication
4. Configures 10 AI agents with tools
5. Starts everything and gives you the link

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "claude: command not found" | Run: `npm install -g @anthropic-ai/claude-code` |
| Bot doesn't respond | Check token: `agentstack health` |
| Terminal won't open | Check: `curl http://localhost:8765/health` |
| "Permission denied" on Linux | Run installer with: `sudo bash install.sh` |
| Tunnel URL changed | Restart: `agentstack stop && agentstack` |
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README for non-technical end users"
```

---

### Task 10: Update .gitignore and add .gitkeep files

**Files:**
- Modify: `.gitignore`
- Create: `mcp-configs/.gitkeep`
- Create: `shared/.gitkeep`

**Step 1: Update .gitignore**

The current `.gitignore` excludes `mcp-configs/` and `shared/` entirely. We need to:
- Keep ignoring the generated files inside these dirs
- But track the directories themselves (via .gitkeep)
- Track `config-templates/` (new, should be in repo)

Add to `.gitignore`:
```
# Keep directory structure but ignore generated content
!mcp-configs/.gitkeep
!shared/.gitkeep
```

**Step 2: Create .gitkeep files**

```bash
touch mcp-configs/.gitkeep shared/.gitkeep
```

**Step 3: Commit**

```bash
git add .gitignore mcp-configs/.gitkeep shared/.gitkeep
git commit -m "chore: track mcp-configs/ and shared/ directories via .gitkeep"
```

---

### Task 11: End-to-end test — simulate fresh install

**Files:** None (testing only)

**Step 1: Test generate-configs.sh in isolation**

```bash
# Create a temp directory simulating a fresh clone
TESTDIR=$(mktemp -d)
cp -r config-templates generate-configs.sh "$TESTDIR/"
cd "$TESTDIR"
bash generate-configs.sh "$TESTDIR"

# Verify outputs
cat agents.json | python3 -m json.tool  # Valid JSON?
ls mcp-configs/                          # All 6 MCP configs?
grep -r "{{AGENTSTACK_HOME}}" .          # No unsubstituted placeholders?
grep "$TESTDIR" agents.json              # Paths correctly substituted?

rm -rf "$TESTDIR"
```

Expected: Valid JSON, 6 MCP configs, no `{{AGENTSTACK_HOME}}` remaining, all paths point to `$TESTDIR`.

**Step 2: Test Docker build**

```bash
docker build -t agentstack-test .
docker run --rm agentstack-test cat /app/agents.json | python3 -m json.tool
docker run --rm agentstack-test ls /app/mcp-configs/
docker rmi agentstack-test
```

Expected: Valid JSON with `/app` paths, all MCP configs present.

**Step 3: Commit (if any fixes were needed)**

```bash
git add -A
git commit -m "fix: address issues found in install testing"
```

---

### Task 12: Final commit and push

**Step 1: Review all changes**

```bash
git log --oneline -15   # Review commit history
git diff main~12..main  # Review full diff
```

**Step 2: Push**

```bash
git push origin main
```

**Step 3: Test the install URL works**

```bash
# Verify raw URL resolves
curl -sI https://raw.githubusercontent.com/aidgoc/agentstack/main/install.sh | head -5
```

Expected: HTTP 200
