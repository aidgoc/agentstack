# AgentStack

Your personal terminal, from Telegram. One machine, one bot, one owner, unlimited sessions.

Open a full xterm.js terminal inside Telegram Mini App. Run Claude Code, bash, ssh — anything. Spawn multiple agent sessions with pre-configured prompts.

## Install

```bash
curl -sL https://raw.githubusercontent.com/aidgoc/agentstack/main/install.sh | bash
```

That's it. One command. It installs everything, asks for your Telegram bot token, and starts.

Need a bot token? Open [@BotFather](https://t.me/BotFather) on Telegram → `/newbot`.

After install, manage with:
```bash
agentstack          # start
agentstack stop     # stop
agentstack logs     # view logs
agentstack update   # pull latest
```

## How It Works

1. Open your bot on Telegram → `/start`
2. Tap **"Open Terminal"** → full terminal inside Telegram
3. Spawn sessions → each one is a real PTY (bash, Claude Code, etc.)
4. Switch between sessions with tabs

## Bot Commands

| Command | What it does |
|---------|-------------|
| `/start` | Welcome + open terminal |
| `/terminal` | Open terminal UI |
| `/sh <cmd>` | Quick shell command |
| `/org` | Paperclip org overview |
| `/tasks` | List tasks |
| `/task <title>` | Create or view a task |
| `/team` | List agents |
| `/hire <name>` | Create an agent |
| `/done <id>` | Mark task done |

## Agent Presets

Edit `agents.json` to add/change presets. Ships with: atlas (researcher), scribe (writer), trendy (trends), crm, dev.

## Auto-Start on macOS

```bash
bash macos/install-service.sh
```

This installs a launchd service that starts AgentStack on login.

## Docker

```bash
cp .env.example .env
nano .env   # add bot token + owner ID
docker compose up -d
```

## Architecture

```
Telegram → Bot (python-telegram-bot)
             ↓ generates HMAC token
         Mini App → WebSocket → FastAPI → PTY sessions
             ↑ via Cloudflare quick tunnel
```

## License

MIT
