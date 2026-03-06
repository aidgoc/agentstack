# AgentStack

Run unlimited Claude Code agents from Telegram. Each user brings their own API key.

## Install & Run

```bash
git clone https://github.com/aidgoc/agentstack.git
cd agentstack
bash setup.sh
```

That's it. It installs deps, asks for your bot token, starts everything.

Need a bot token? Open [@BotFather](https://t.me/BotFather) on Telegram → `/newbot`.

## What happens

- Any Telegram user opens your bot → `/start`
- They set their Anthropic API key → `/key sk-ant-...` (message auto-deleted)
- They tap **"Open Terminal"** → full xterm.js terminal inside Telegram
- They spawn agents → each one is a Claude Code instance with their own key
- Switch between agents with tabs. Fully isolated per user.

## Commands

| Command | What it does |
|---------|-------------|
| `/start` | Onboard + help |
| `/key sk-ant-...` | Set your API key |
| `/terminal` | Open terminal UI |
| `/spawn <name>` | Start an agent |
| `/kill <name>` | Stop an agent |
| `/sessions` | List your agents |
| `/use <name>` | Switch active agent |
| `/to <name> <msg>` | Message specific agent |
| `/broadcast <msg>` | Message all agents |
| `/killall` | Stop all your agents |
| `/logout` | Remove key + stop all |

## Agent presets

Edit `agents.json` to add/change presets. Ships with: atlas (researcher), scribe (writer), trendy (trends), crm, dev.

## Docker

```bash
git clone https://github.com/aidgoc/agentstack.git
cd agentstack
cp .env.example .env
nano .env   # add bot token
docker compose up -d
```

## License

MIT
