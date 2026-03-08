# Jarvis — Design Document
**Date:** 2026-03-08
**Status:** Approved
**Author:** Atlas + HNG

---

## Overview

Jarvis is a brand-new personal AI assistant system — a complete fresh project living at `~/jarvis/`. It is **AgentStack + OpenClaw/MoltBot combined**: the terminal infrastructure and agent roster from AgentStack, plus the proactive heartbeat and natural language orchestration from OpenClaw.

**You talk to Jarvis. Jarvis talks to the agents. Agents report back to Jarvis. Jarvis replies to you.**

Jarvis runs on a new Telegram bot (separate from AgentStack). AgentStack is kept untouched as reference.

---

## Mental Model

```
You (Telegram)
      ↓
   JARVIS  ← the only thing you ever talk to
   /  |  \  \  \  \  \
Atlas Social Dev Designer Analyst Marketing Scribe Trendy
      ↓
   JARVIS
      ↓
You get the answer
```

---

## Architecture

### Four Processes

| Process | File | Purpose |
|---------|------|---------|
| Jarvis Brain | `jarvis.py` | Telegram bot + NL orchestrator |
| Heartbeat | `heartbeat.py` | 30-min proactive scheduler |
| Terminal Server | `web/server.py` | FastAPI + PTY + xterm.js Mini App |
| Cloudflare Tunnel | (external) | Public HTTPS for Mini App |

### Two Execution Modes

**Quick Mode** — most messages
- Runs `claude --print` with the target agent's system prompt + MCP config
- Returns in ~10–30 seconds
- Jarvis replies inline in Telegram chat

**Deep Mode** — complex/long-running tasks
- Spawns a named tmux session with the agent
- Optionally opens terminal Mini App link
- Jarvis sends you the link to watch in real-time

### Routing Logic

Jarvis (Claude with orchestrator prompt) reads the user's message and:
1. Identifies intent (research / write / code / design / analyse / social / trends)
2. Selects one or more agents
3. Decides quick vs deep mode based on task complexity
4. Runs agent(s), collects output
5. Summarises and replies to Telegram

---

## The Heartbeat (Proactive Autonomy)

Every 30 minutes (configurable via `.env`):
1. Jarvis reads `HEARTBEAT.md` — a human-editable task checklist
2. Runs relevant agents via `claude --print`
3. Sends a Telegram message **only if something needs attention**
4. Otherwise: silent (`HEARTBEAT_OK`)

### Example HEARTBEAT.md
```markdown
- Atlas: scan for trending news in HDD/utility construction industry
- Social: check if any scheduled posts are due today
- Analyst: flag any invoices 30+ days overdue
- Dev: check for open GitHub PRs or failing CI
- Trendy: surface any viral topics relevant to HEFT USA
```

Active hours configurable (e.g. 07:00–22:00) to prevent night alerts.

---

## Agent Roster

| Agent | Role | Quick Mode Triggers |
|-------|------|---------------------|
| **Atlas** | Research, web search, reports | research, find, what's happening, look up |
| **Social** | Platform-optimised social posts | post, caption, social, write a post |
| **Marketing** | Campaigns, strategy, funnels | campaign, strategy, marketing plan |
| **Designer** | HTML/SVG graphics, visual assets | design, image, graphic, logo, visual |
| **Analyst** | P&L, job costing, financials | analyse, cost, profit, ROI, financial |
| **Dev** | Code, bugs, features, PRs | build, code, fix, deploy, PR, debug |
| **Scribe** | Long-form writing, email copy | write, draft, article, email, copy |
| **Trendy** | Trend scouting (X, Reddit, web) | trending, viral, what's hot |

All agents share a `shared/` workspace for handoffs (e.g. Atlas writes research → Social reads it to write posts).

---

## Directory Structure

```
~/jarvis/
├── jarvis.py              ← Main bot + Jarvis orchestrator
├── heartbeat.py           ← Proactive 30-min scheduler
├── agents.json            ← Agent roster + system prompts + MCP paths
├── store.py               ← SQLite (tasks, goals, memory, activity)
├── users.py               ← Single-owner auth (HMAC tokens)
├── HEARTBEAT.md           ← Proactive task checklist (human-editable)
├── SOUL.md                ← Jarvis personality + behaviour rules
├── .env                   ← New bot token, owner ID, config
├── .env.example
├── start.sh               ← Boot all processes + watchdog
├── setup.sh               ← First-time install
├── sentinel.sh            ← Status monitor + Telegram alerts
├── web/
│   ├── server.py          ← FastAPI terminal server
│   └── static/
│       ├── terminal.html  ← xterm.js Mini App
│       └── dashboard.html ← Jarvis command centre (agent status, heartbeat log)
├── mcp-configs/
│   ├── atlas.json
│   ├── social.json
│   ├── analyst.json
│   └── designer.json
└── shared/
    ├── research/
    ├── drafts/
    ├── designs/
    ├── social/
    ├── marketing/
    └── analysis/
```

---

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Jarvis intro, status, quick help |
| `/hb` | View or edit HEARTBEAT.md |
| `/memory` | Show Jarvis SOUL.md (personality + rules) |
| `/tasks` | Task board (create, list, update) |
| `/task <id>` | View single task |
| `/done <id>` | Mark task complete |
| `/agents` | Team roster + current status |
| `/terminal` | Open Mini App terminal |
| `/sh <cmd>` | Quick raw shell command |
| `/status` | System health (processes, uptime, disk, memory) |

Plain text messages → Jarvis NL routing (no command needed).

---

## Key Files Detail

### SOUL.md
Defines Jarvis's personality, tone, routing behaviour, and hard rules (e.g. always ask before destructive shell commands, keep replies under 500 words unless asked for detail).

### agents.json
Each agent entry:
```json
{
  "atlas": {
    "description": "Deep research analyst",
    "prompt": "You are Atlas...",
    "model": "opus",
    "cwd": "/home/harshwardhan/jarvis/shared/research",
    "mcp_config": "/home/harshwardhan/jarvis/mcp-configs/atlas.json",
    "triggers": ["research", "find", "look up", "what is", "analyse"]
  }
}
```

### .env
```
TELEGRAM_BOT_TOKEN=<new jarvis bot token>
OWNER_ID=<same owner id>
JARVIS_WEBAPP_URL=
JARVIS_PORT=8766
HEARTBEAT_INTERVAL=30
HEARTBEAT_ACTIVE_HOURS=07:00-22:00
```

---

## Data Flow Examples

### Example 1 — Research Request
```
You: "jarvis research what competitors are doing in HDD drilling market"
  → Jarvis: intent=research → quick mode → atlas
  → claude --print -p atlas_prompt "research HDD drilling competitors"
  → Atlas: searches web, writes structured report
  → Jarvis: "Here's what I found: [summary + key points]"
  → Full report saved to shared/research/
```

### Example 2 — Social Post
```
You: "create an instagram post about our vermeer 24x40 job in texas"
  → Jarvis: intent=social content → quick mode → social
  → Social: writes caption, hashtags, posting time
  → Jarvis: "Here's your post: [caption] [hashtags]"
  → Saved to shared/social/
```

### Example 3 — Complex Dev Task
```
You: "build a job costing calculator web page"
  → Jarvis: intent=code, complex → deep mode → dev
  → Spawns tmux as_dev session with Dev agent
  → Jarvis: "Starting Dev agent — tap to watch: [terminal link]"
```

### Example 4 — Heartbeat Alert
```
[30 min heartbeat fires]
  → Atlas runs: finds 3 trending HDD news articles
  → Social runs: 1 scheduled post due tomorrow
  → Analyst runs: no overdue invoices
  → Jarvis sends: "📡 Morning check:
     • 3 new HDD industry articles (Atlas found)
     • Instagram post due tomorrow — want me to draft it?
     • Financials look clean ✅"
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Bot framework | python-telegram-bot 20.x |
| Web server | FastAPI + uvicorn |
| Terminal | xterm.js + WebSocket + PTY (pty module) |
| Session persistence | tmux |
| Agent execution | `claude` CLI (`--print` + interactive) |
| Database | SQLite (WAL mode) |
| Tunnel | cloudflared |
| Memory format | Markdown files (SOUL.md, HEARTBEAT.md, shared/) |

---

## What's Reused from AgentStack

| Component | Reuse level |
|-----------|-------------|
| `web/server.py` (terminal) | Copy + adapt |
| `web/static/terminal.html` | Copy + rebrand |
| `store.py` (SQLite layer) | Copy as-is |
| `users.py` (auth) | Copy as-is |
| `sentinel.sh` | Copy + adapt |
| `agents.json` structure | Reference + expand |
| mcp-configs | Copy + adapt |
| `shared/` folder structure | Copy |

---

## Success Criteria

- [ ] You can send a plain English message to Jarvis and get a real answer (routed through the right agent) in under 60 seconds
- [ ] Heartbeat fires every 30 min and proactively messages you when something needs attention
- [ ] Terminal Mini App opens on demand for complex tasks
- [ ] All 8 agents accessible via Jarvis orchestration
- [ ] `HEARTBEAT.md` is editable via `/hb` command
- [ ] System survives restarts (tmux persistence, watchdog in start.sh)

---
*Design approved by HNG on 2026-03-08*
