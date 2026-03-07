# AgentStack

Your personal terminal, from Telegram. One machine, one bot, one owner, unlimited sessions.

Open a full xterm.js terminal inside Telegram — run Claude Code, bash, ssh, anything. Spawn pre-configured AI agent sessions with tools loaded. All running on your own computer.

## Setup (2 steps)

**Step 1:** Run this in your terminal (Mac or Linux):

```bash
curl -sL https://raw.githubusercontent.com/aidgoc/agentstack/main/install.sh | bash
```

It installs everything automatically and asks for two things:
- **Bot token** — get one from [@BotFather](https://t.me/BotFather) (send `/newbot`)
- **Your Telegram user ID** — get it from [@userinfobot](https://t.me/userinfobot) (send `/start`)

**Step 2:** Open your bot on Telegram and tap **"Terminal"**.

That's it. You have a full terminal inside Telegram.

> **Note:** Claude Code uses your Anthropic account (not an API key). Run `claude` in any terminal to sign in with your browser the first time.

## What You Get

- **Full terminal** inside Telegram via xterm.js — bash, ssh, vim, anything
- **Claude Code sessions** with pre-loaded system prompts and MCP tools
- **9 pre-built agents** — research, writing, social media, marketing, design, analytics, CRM, dev, trend scouting
- **Session persistence** — sessions survive server restarts (via tmux)
- **Auto-healing** — sentinel watchdog monitors services, auto-restarts failures, alerts on Telegram
- **File upload/download** — drag and drop files into the terminal
- **Mobile-optimized** — pinch-to-zoom, special key toolbar, haptic feedback

## Agent Presets

| Agent | What it does | MCP Tools |
|-------|-------------|-----------|
| **atlas** | Deep research analyst | fetch, filesystem |
| **scribe** | Copywriter matched to brand voice | — |
| **trendy** | Trend scout for X/Reddit/web | — |
| **social** | Social media post generator | fetch, filesystem |
| **marketing** | Marketing strategy & campaigns | fetch, filesystem |
| **designer** | SVG/HTML graphic designer | fetch, filesystem, puppeteer |
| **analyst** | Business/financial analysis | fetch, filesystem, sqlite |
| **crm** | Contact & deal management | — |
| **dev** | Senior developer | — |

Edit `agents.json` to customize prompts, models, or add your own agents.

## Commands

After install, manage with:

```bash
agentstack            # start everything
agentstack stop       # stop all services
agentstack sentinel   # start watchdog (auto-heal + Telegram alerts)
agentstack logs       # tail all logs
agentstack health     # check server status
agentstack update     # pull latest code
```

### Telegram Bot Commands

| Command | What it does |
|---------|-------------|
| `/start` | Welcome + open terminal |
| `/terminal` | Open terminal UI |
| `/sh <cmd>` | Quick shell command |
| `/org` | Company overview |
| `/tasks` | List tasks |
| `/task <title>` | Create or view a task |
| `/team` | List agents |
| `/hire <name>` | Create an agent |
| `/done <id>` | Mark task done |

## Architecture

```
You (Telegram)
  |
  v
Telegram Bot (bot.py)
  |-- /start, /sh, /tasks, /team ...
  |-- generates HMAC auth token
  v
Telegram Mini App (terminal.html)
  |-- xterm.js + WebGL renderer
  |-- WebSocket connection
  v
FastAPI Server (web/server.py)
  |-- WebSocket ↔ PTY sessions
  |-- tmux backend (session persistence)
  |-- 64KB replay buffer (reconnect recovery)
  |-- ping/pong keepalive (20s)
  v
Cloudflare Tunnel (cloudflared)
  |-- auto HTTPS, random URL per restart
  |-- sentinel auto-syncs URL changes
  v
Your Machine
  |-- bash, claude, ssh, python ...
```

## File Structure

```
agentstack/
├── install.sh          # One-liner installer (curl | bash)
├── setup.sh            # Git-clone installer (bash setup.sh)
├── start.sh            # Launches all services
├── sentinel.sh         # Watchdog: monitors, auto-heals, alerts
├── bot.py              # Telegram bot (owner-only, HMAC auth)
├── users.py            # Auth: HMAC tokens, owner verification
├── store.py            # SQLite: tasks, agents, goals, activity
├── agents.json         # Agent presets (prompts, models, MCP configs)
├── paperclip.py        # Paperclip API client (optional integration)
├── requirements.txt    # Python dependencies
├── web/
│   ├── server.py       # FastAPI + WebSocket terminal server
│   └── static/
│       └── terminal.html   # xterm.js terminal UI (all-in-one)
├── mcp-configs/        # Per-agent MCP tool configurations
│   ├── atlas.json
│   ├── social.json
│   ├── marketing.json
│   ├── designer.json
│   └── analyst.json
├── shared/             # Inter-agent workspace
│   ├── research/
│   ├── drafts/
│   ├── social/
│   ├── marketing/
│   ├── designs/
│   ├── analysis/
│   └── crm_data/
├── macos/
│   └── install-service.sh  # launchd auto-start on login
├── Dockerfile          # Docker build
├── docker-compose.yml  # Docker Compose config
└── .env.example        # Template for required env vars
```

## Docker (alternative)

```bash
git clone https://github.com/aidgoc/agentstack.git
cd agentstack
cp .env.example .env    # add bot token + owner ID
docker compose up -d
```

## How It's Free

- **Telegram bot** — free (Telegram Bot API)
- **Cloudflare tunnel** — free (Quick Tunnels, no account needed)
- **Claude Code** — uses your Anthropic account (pay-as-you-go or subscription)
- **Everything else** — runs on your own machine

## License

MIT
