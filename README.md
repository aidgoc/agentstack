# AgentStack

Multi-agent Claude Code manager via Telegram. Spawn, control, and switch between multiple Claude Code instances from your phone — each one is a full AI agent.

## What it does

- **Spawn named agents** from Telegram — each runs Claude Code in its own terminal session
- **Full terminal UI** inside Telegram via Mini App (xterm.js with colors, cursor, scrollback)
- **Switch between agents** with tabs — run a researcher, copywriter, and developer in parallel
- **Text commands** as fallback — `/spawn`, `/to`, `/broadcast` work without the Mini App
- **Auto-tunnel** — Cloudflare tunnel URL is detected and configured automatically on every restart

## Architecture

```
Telegram  ──→  Bot (python-telegram-bot)
                 │
                 ├── Text commands (/spawn, /to, /broadcast)
                 │
                 └── Mini App button ──→  Web Server (FastAPI + WebSocket)
                                              │
                                              ├── xterm.js terminal in browser
                                              │
                                              └── PTY sessions (one per agent)
                                                    │
                                                    └── Claude Code CLI
```

Each agent is a Claude Code instance running in a PTY. The web server bridges WebSocket connections from the Mini App to PTY file descriptors for real-time terminal I/O.

## Quick Start

### Prerequisites

| Tool | Install (Mac) | Install (Linux) |
|------|--------------|-----------------|
| Python 3.10+ | `brew install python` | Pre-installed |
| tmux | `brew install tmux` | `sudo apt install tmux` |
| cloudflared | `brew install cloudflared` | [See docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) |
| Claude Code | `npm install -g @anthropic-ai/claude-code` | Same |

### Setup

```bash
# Clone
git clone https://github.com/aidgoc/agentstack.git
cd agentstack

# Configure
cp .env.example .env
# Edit .env — add your Telegram bot token and user ID

# Install Python deps
pip install -r requirements.txt

# Run
bash start.sh
```

### Create a Telegram Bot

1. Open [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot`, follow prompts
3. Copy the token to `TELEGRAM_BOT_TOKEN` in `.env`
4. Get your user ID: send a message to [@userinfobot](https://t.me/userinfobot)
5. Add your ID to `TELEGRAM_ALLOWED_USERS` in `.env`

### Run on Mac

```bash
# Install everything
brew install tmux cloudflared python
npm install -g @anthropic-ai/claude-code

# Clone and configure
git clone https://github.com/aidgoc/agentstack.git
cd agentstack
cp .env.example .env
nano .env  # add your tokens

# Install and run
pip3 install -r requirements.txt
bash start.sh
```

That's it. Open Telegram, tap the "Terminal" button in the bot chat.

### Run with Docker

```bash
# Clone and configure
git clone https://github.com/aidgoc/agentstack.git
cd agentstack
cp .env.example .env
nano .env  # add your tokens

# Run
docker compose up -d

# View logs
docker compose logs -f
```

Note: Claude Code CLI needs to be authenticated. Mount your `~/.claude` directory (already configured in `docker-compose.yml`).

## Usage

### Mini App (recommended)

1. Open bot in Telegram
2. Tap **"Terminal"** button (bottom of chat)
3. Tap **"+ Spawn"** → pick an agent preset
4. Full terminal appears — type directly to Claude Code
5. Switch agents using tabs at the top

### Text Commands

| Command | Description |
|---------|-------------|
| `/start` | Show help + Mini App button |
| `/terminal` | Open Mini App |
| `/spawn <name>` | Start an agent (opens terminal on desktop too) |
| `/kill <name>` | Kill an agent |
| `/sessions` | List active agents |
| `/use <name>` | Switch active agent for text mode |
| `/to <name> <msg>` | Send message to specific agent |
| `/broadcast <msg>` | Message ALL active agents |
| `/sh <cmd>` | Run a shell command |
| `/killall` | Kill all agents |
| `/agents` | List presets |
| `/reload` | Reload agents.json |

### Terminal Shortcuts (text mode)

| Shortcut | Key |
|----------|-----|
| `/cc` | Ctrl+C |
| `/cd` | Ctrl+D |
| `/up` `/down` | Arrow keys |
| `/enter` | Enter |
| `/tab` | Tab |
| `/y` `/n` | yes / no + Enter |
| `/esc` | Escape |

## Agent Presets

Configured in `agents.json`. Each preset defines a name, system prompt, and working directory:

```json
{
  "agents": {
    "atlas": {
      "description": "Deep research analyst",
      "prompt": "You are Atlas, a deep research analyst...",
      "cwd": "/path/to/research"
    },
    "scribe": {
      "description": "Copywriter",
      "prompt": "You are Scribe, a copywriter...",
      "cwd": "/path/to/drafts"
    }
  }
}
```

Default presets: **atlas** (research), **scribe** (copywriter), **trendy** (trend scout), **crm** (CRM), **dev** (developer).

Edit `agents.json` to add your own. Run `/reload` in Telegram to pick up changes.

## How It Works

1. `start.sh` launches the web server, cloudflared tunnel, and Telegram bot
2. Cloudflared generates a random HTTPS URL (changes on restart)
3. The script parses this URL and:
   - Updates `.env` with the new `AGENTSTACK_WEBAPP_URL`
   - Sets the Telegram bot's menu button via API
4. Bot reads the URL from env and serves Mini App buttons
5. Mini App connects via WebSocket to the web server
6. Web server spawns PTY processes running Claude Code
7. Real-time I/O flows: xterm.js ↔ WebSocket ↔ PTY ↔ Claude Code

## Files

```
agentstack/
├── start.sh           # One-command launcher (web + tunnel + bot)
├── bot.py             # Telegram bot with all commands
├── terminal.py        # Tmux session manager (text mode fallback)
├── web/
│   ├── server.py      # FastAPI + WebSocket + PTY bridge
│   └── static/
│       └── terminal.html  # xterm.js Mini App UI
├── agents.json        # Agent presets (name, prompt, cwd)
├── .env.example       # Configuration template
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## License

MIT
