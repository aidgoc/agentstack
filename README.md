# AgentStack

Run multiple Claude Code AI agents from Telegram. Any user connects, brings their own Anthropic API key, and gets unlimited Claude Code instances — each one is a full AI agent that can code, research, write, and more.

## How it works

1. User opens the Telegram bot and sends `/start`
2. User provides their Anthropic API key via `/key sk-ant-...`  (auto-deleted for security)
3. User taps **"Open Terminal"** — a full xterm.js terminal appears inside Telegram
4. User spawns agents (researcher, copywriter, developer, or custom) — each is a Claude Code instance
5. Switch between agents with tabs. All sessions are isolated per user.

```
User A (phone)  ──→  Telegram Bot  ──→  WebSocket Server  ──→  PTY: claude (user A's key)
User B (phone)  ──→       │        ──→       │             ──→  PTY: claude (user B's key)
                          │                  │
                     Auth + routing      Per-user isolation
```

Each user's agents run with **their own API key**. The server operator pays nothing for AI usage — each user pays their own Anthropic bill.

## Quick Start

### Prerequisites

| Tool | Mac | Linux |
|------|-----|-------|
| Python 3.10+ | `brew install python` | Pre-installed |
| tmux | `brew install tmux` | `sudo apt install tmux` |
| cloudflared | `brew install cloudflared` | [Download](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) |
| Claude Code | `npm install -g @anthropic-ai/claude-code` | Same |

### Setup

```bash
git clone https://github.com/aidgoc/agentstack.git
cd agentstack
cp .env.example .env
nano .env   # add TELEGRAM_BOT_TOKEN
pip install -r requirements.txt
bash start.sh
```

### Create a Telegram Bot

1. Open [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy token to `TELEGRAM_BOT_TOKEN` in `.env`
3. Optionally add your Telegram user ID to `TELEGRAM_ADMIN_USERS` for admin commands

### Run on Mac

```bash
brew install tmux cloudflared python
npm install -g @anthropic-ai/claude-code
git clone https://github.com/aidgoc/agentstack.git
cd agentstack
cp .env.example .env
nano .env
pip3 install -r requirements.txt
bash start.sh
```

### Run with Docker

```bash
git clone https://github.com/aidgoc/agentstack.git
cd agentstack
cp .env.example .env
nano .env
docker compose up -d
docker compose logs -f
```

## User Flow

### For end users (your clients)

1. Open bot in Telegram → `/start`
2. Set API key: `/key sk-ant-api03-...`
3. Tap **"Open Terminal"** or `/terminal`
4. Spawn agents from the UI or via `/spawn dev`
5. Type to your agents. Switch between them with tabs.

### Text commands

| Command | Description |
|---------|-------------|
| `/start` | Onboarding + help |
| `/key <api_key>` | Set Anthropic API key |
| `/terminal` | Open Mini App terminal |
| `/spawn <name>` | Start an agent |
| `/kill <name>` | Kill an agent |
| `/sessions` | List your agents |
| `/use <name>` | Switch active agent |
| `/to <name> <msg>` | Message specific agent |
| `/broadcast <msg>` | Message all agents |
| `/killall` | Kill all your agents |
| `/logout` | Remove key + kill sessions |

### Admin commands

| Command | Description |
|---------|-------------|
| `/admin` | List all users and sessions |
| `/sh <cmd>` | Run shell command |
| `/reload` | Reload agents.json |

## Agent Presets

Defined in `agents.json`:

```json
{
  "agents": {
    "atlas": {
      "description": "Deep research analyst",
      "prompt": "You are Atlas, a research analyst...",
      "cwd": "~/research"
    },
    "dev": {
      "description": "Senior developer",
      "prompt": "You are a senior developer...",
      "cwd": "~"
    }
  }
}
```

Users can spawn presets or any custom name. Custom names get a plain Claude Code instance.

## Architecture

```
agentstack/
├── start.sh           # One-command launcher
├── bot.py             # Multi-user Telegram bot
├── users.py           # User DB (SQLite) + auth tokens
├── terminal.py        # Tmux session manager (text mode)
├── web/
│   ├── server.py      # FastAPI + WebSocket + PTY (Mini App)
│   └── static/
│       └── terminal.html  # xterm.js terminal UI
├── agents.json        # Agent presets
├── data/              # SQLite DB (auto-created, gitignored)
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

### Multi-user isolation

- Sessions are keyed as `user_id:agent_name` — no cross-user access
- Each PTY process gets the user's own `ANTHROPIC_API_KEY` in its environment
- Web tokens are HMAC-signed per user
- Rate limiting per user
- Configurable session limit per user (`MAX_SESSIONS_PER_USER`)

### Auto-tunnel

`start.sh` handles the cloudflared tunnel automatically:
1. Starts web server
2. Starts cloudflared → parses the HTTPS URL
3. Updates `.env` with new URL
4. Sets Telegram bot menu button via API
5. Starts bot

New URL is configured automatically on every restart.

## Configuration

| Env Var | Description | Default |
|---------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather | Required |
| `TELEGRAM_ADMIN_USERS` | Comma-separated admin user IDs | None |
| `MAX_SESSIONS_PER_USER` | Max concurrent agents per user | 10 |
| `AGENTSTACK_PORT` | Web server port | 8765 |
| `AGENTSTACK_WEBAPP_URL` | Auto-set by start.sh | Auto |

## License

MIT
