# AgentStack — One-Click Installable Project Design

**Date:** 2026-03-09
**Status:** Approved
**Goal:** Make AgentStack installable by non-technical users with a single command

---

## Architecture

Three install paths, one guided experience:

| Path | Target | Command |
|------|--------|---------|
| Linux | Ubuntu/Debian, Fedora, Arch | `curl -sL https://agentstack.sh/install \| bash` |
| macOS | Intel + Apple Silicon | Same curl command (detects OS) |
| Docker | Any platform | `git clone + docker compose up` |

All three paths converge on the same guided setup flow that configures Telegram bot, Claude auth, agents, and MCP configs automatically.

---

## What Changes

### 1. Smart Installer (install.sh rewrite)
- Detects OS (Linux distro / macOS / unsupported)
- Installs system deps automatically (apt/brew/dnf)
- Opens Telegram deep links for bot creation + user ID
- Step-by-step prompts with validation (checks bot token format, tests API call)
- Auto-generates agents.json from template with correct paths
- Auto-generates all mcp-configs/*.json from templates with correct paths
- Creates shared/ directory tree
- Optional Frappe Forge prompt — installs bench infrastructure if user opts in
- Sets up auto-start (systemd on Linux, launchd on macOS)
- Launches AgentStack at the end

### 2. Path-aware config generation
- New: config-templates/agents.template.json — uses {{AGENTSTACK_HOME}} placeholders
- New: config-templates/mcp/*.template.json — one per agent, with path placeholders
- Installer replaces placeholders with actual paths and writes to agents.json + mcp-configs/
- No more hardcoded /home/harshwardhan/ anywhere

### 3. Setup validation
- After install, run health check:
  - Bot token valid? (test Telegram API call)
  - Claude Code accessible? (test claude --version)
  - Web server starts? (test localhost:8765/health)
  - Tunnel works? (test cloudflare URL)
- Report pass/fail with fix suggestions

### 4. Docker path
- Updated Dockerfile + docker-compose.yml
- .env.example with clear comments
- docker-compose up handles everything after user fills in .env
- Volume mounts for shared/, Claude auth, and SQLite DB

### 5. Uninstall + Upgrade
- agentstack uninstall — clean removal
- agentstack upgrade — git pull + re-run setup (preserves .env, agents.json, shared/)

---

## File Changes

```
agentstack/
├── install.sh                          # REWRITE — smart OS-detecting installer
├── setup.sh                            # REWRITE — guided setup with validation
├── config-templates/                   # NEW — path-aware templates
│   ├── agents.template.json
│   └── mcp/
│       ├── atlas.template.json
│       ├── social.template.json
│       ├── marketing.template.json
│       ├── designer.template.json
│       ├── analyst.template.json
│       ├── forge.template.json
│       ├── scribe.template.json
│       ├── trendy.template.json
│       ├── crm.template.json
│       └── dev.template.json
├── agents.example.json                 # UPDATE — reference only
├── Dockerfile                          # UPDATE — cleaner, multi-stage
├── docker-compose.yml                  # UPDATE — better volume/env handling
├── Makefile                            # UPDATE — add install/uninstall/upgrade
├── README.md                           # REWRITE — user-facing, not developer-facing
└── macos/
    └── install-service.sh              # UPDATE — integrate into main installer
```

## What Stays the Same
- bot.py, web/server.py, users.py, store.py — core code unchanged
- terminal.html — no changes
- start.sh, sentinel.sh — minor tweaks at most
- .gitignore — same exclusions

---

## Install Flow (User Experience)

```
$ curl -sL https://raw.githubusercontent.com/aidgoc/agentstack/main/install.sh | bash

🤖 AgentStack Installer
========================

Detecting system... macOS (Apple Silicon) ✓
Installing dependencies... python3 ✓  node ✓  tmux ✓  cloudflared ✓  claude ✓

─── Telegram Bot Setup ───
Opening @BotFather in Telegram...
  1. Send /newbot to @BotFather
  2. Choose a name and username for your bot
  3. Copy the token
Paste your bot token: 1234567890:ABCdefGHI...
  ✓ Bot token valid! Bot name: @MyAgentBot

Opening @userinfobot in Telegram...
  Send any message to @userinfobot and paste your ID:
Your Telegram user ID: 12345678
  ✓ User ID confirmed

─── Claude Code Setup ───
Choose authentication method:
  1. API key (recommended for servers)
  2. Browser login (OAuth)
Choice [1]: 1
Paste your Anthropic API key: sk-ant-...
  ✓ Claude Code authenticated

─── Frappe Forge (Optional) ───
Install Frappe app generation? Adds ~2GB of dependencies. [y/N]: n
  Skipped. You can add it later with: agentstack enable forge

─── Configuring Agents ───
Setting up 9 agents... ✓
  atlas, scribe, trendy, social, marketing, designer, analyst, crm, dev

─── Starting AgentStack ───
Web server... ✓ http://localhost:8765
Tunnel... ✓ https://abc-xyz.trycloudflare.com
Bot... ✓ @MyAgentBot is live!

✅ AgentStack is running!
Open Telegram → message @MyAgentBot → tap "Terminal"
```

---

## Agent Definitions (ships with all 10)

| Agent | Role | MCP Tools |
|-------|------|-----------|
| atlas | Research analyst | fetch, filesystem (shared/research) |
| scribe | Copywriter | filesystem (shared/drafts) |
| trendy | Trend scout | fetch |
| social | Social media manager | fetch, filesystem (shared/social) |
| marketing | Marketing strategist | fetch, filesystem (shared/marketing) |
| designer | Graphic designer | fetch, filesystem (shared/designs), puppeteer |
| analyst | Business analyst | fetch, filesystem (shared/analysis), sqlite |
| crm | CRM manager | filesystem (shared/crm_data) |
| dev | Senior developer | filesystem (project root) |
| forge | Frappe app builder | fetch, filesystem (shared/forge, frappe-bench/apps) |

---

## Config Template Format

agents.template.json uses {{AGENTSTACK_HOME}} placeholder:
```json
{
  "agents": {
    "atlas": {
      "description": "...",
      "prompt": "...",
      "model": "sonnet",
      "mcp_config": "{{AGENTSTACK_HOME}}/mcp-configs/atlas.json"
    }
  }
}
```

MCP templates use same placeholder:
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem",
               "{{AGENTSTACK_HOME}}/shared/research"]
    }
  }
}
```

Installer does: `sed "s|{{AGENTSTACK_HOME}}|$(pwd)|g" template > output`
