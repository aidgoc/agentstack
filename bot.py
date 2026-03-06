#!/usr/bin/env python3
"""
AgentStack - Multi-agent Claude Code manager via Telegram.

Two modes of interaction:
1. Mini App (/terminal) - Full xterm.js terminal in Telegram WebApp
2. Text commands - Fallback for quick operations

Commands:
  /start, /help        - Show help
  /terminal            - Open the terminal Mini App
  /agents              - List available agent presets
  /spawn <name>        - Start a Claude Code agent
  /kill <name>         - Kill an agent session
  /sessions            - List active sessions
  /to <name> <msg>     - Send a message to a specific agent
  /use <name>          - Switch active agent (text mode)
  /sh <cmd>            - Run a one-shot shell command
  /broadcast <msg>     - Send a message to ALL active agents
  /killall             - Kill all agent sessions
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)

from terminal import SessionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("agentstack")

BOT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
AGENTS_FILE = BOT_DIR / "agents.json"

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USERS = [s.strip() for s in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") if s.strip()]
WEBAPP_URL = os.getenv("AGENTSTACK_WEBAPP_URL", "")  # Set after tunnel is up

MAX_MSG_LEN = 4000
RATE_LIMIT = 25
RATE_WINDOW = 60


class AgentStackBot:
    def __init__(self):
        self.sessions = SessionManager()
        self.agents = self._load_agents()
        self.active_agent: dict[str, str] = {}  # chat_id -> agent_name
        self._rate_ts: dict[str, list[float]] = {}
        self._rate_lock = threading.Lock()
        self._app = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _load_agents(self) -> dict:
        if AGENTS_FILE.exists():
            with open(AGENTS_FILE) as f:
                return json.load(f).get("agents", {})
        return {}

    def reload_agents(self):
        self.agents = self._load_agents()

    def _auth(self, user_id: str) -> bool:
        if not ALLOWED_USERS:
            return True
        return user_id in ALLOWED_USERS

    def _rate_ok(self, user_id: str) -> bool:
        now = time.time()
        with self._rate_lock:
            ts = [t for t in self._rate_ts.get(user_id, []) if now - t < RATE_WINDOW]
            if len(ts) >= RATE_LIMIT:
                self._rate_ts[user_id] = ts
                return False
            ts.append(now)
            self._rate_ts[user_id] = ts
            return True

    # -- Helpers --

    def _send(self, chat_id: str, text: str, parse_mode: str = None):
        if not self._app or not self._loop:
            return
        async def _do():
            try:
                await self._app.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            except Exception:
                if parse_mode:
                    await self._app.bot.send_message(chat_id=chat_id, text=text)
        try:
            future = asyncio.run_coroutine_threadsafe(_do(), self._loop)
            future.result(timeout=15)
        except Exception as e:
            log.error("Send failed: %s", e)

    @staticmethod
    def _split(text: str, limit: int = 3900) -> list[str]:
        if not text:
            return ["(no output)"]
        chunks = []
        while text:
            if len(text) <= limit:
                chunks.append(text)
                break
            idx = text.rfind("\n", 0, limit)
            if idx == -1:
                idx = limit
            chunks.append(text[:idx])
            text = text[idx:].lstrip("\n")
        return chunks

    def _send_output(self, chat_id: str, text: str):
        for chunk in self._split(text):
            self._send(chat_id, f"```\n{chunk}\n```", parse_mode="Markdown")

    def _build_claude_cmd(self, agent_name: str, agent_cfg: dict = None) -> list[str]:
        cmd = ["claude"]
        if agent_cfg and agent_cfg.get("prompt"):
            cmd.extend(["--system-prompt", agent_cfg["prompt"]])
        return cmd

    def _spawn_agent(self, chat_id: str, name: str, agent_cfg: dict = None) -> str:
        if self.sessions.has(name):
            return f"Agent '{name}' is already running.\nUse /kill {name} first, or /use {name} to switch."

        cmd = self._build_claude_cmd(name, agent_cfg)
        cwd = agent_cfg.get("cwd", os.path.expanduser("~")) if agent_cfg else os.path.expanduser("~")
        os.makedirs(cwd, exist_ok=True)

        def on_output(session_name: str, text: str):
            self._send_output(chat_id, text)
            if not self.sessions.has(session_name):
                self._send(chat_id, f"Agent '{session_name}' has exited.")

        try:
            self.sessions.create(name, cmd, cwd=cwd, on_output=on_output)
        except Exception as e:
            return f"Failed to spawn '{name}': {e}"

        self.active_agent[chat_id] = name

        desc = f"\n{agent_cfg['description']}" if agent_cfg and agent_cfg.get("description") else ""
        return (
            f"Agent '{name}' started.{desc}\n\n"
            f"Active agent: '{name}'\n"
            f"Terminal window opened on desktop.\n"
            f"Use /terminal for full terminal in Telegram."
        )

    # -- Handlers --

    async def _handle_start(self, update, context):
        if not self._auth(str(update.effective_user.id)):
            await update.message.reply_text("Not authorized.")
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        agents_list = "\n".join(f"  {n} - {a.get('description', '')}" for n, a in self.agents.items())

        text = (
            "AgentStack\n"
            "Multi-Agent Claude Code Manager\n"
            "================================\n\n"
            "Commands:\n"
            "  /terminal          - Open full terminal UI\n"
            "  /agents            - List agent presets\n"
            "  /spawn <name>      - Start an agent\n"
            "  /kill <name>       - Kill an agent\n"
            "  /sessions          - List active sessions\n"
            "  /to <name> <msg>   - Message specific agent\n"
            "  /use <name>        - Switch active agent\n"
            "  /sh <cmd>          - Shell command\n"
            "  /broadcast <msg>   - Message all agents\n"
            "  /killall           - Kill all agents\n\n"
            f"Agent presets:\n{agents_list}"
        )

        # Add Mini App button if URL is configured
        keyboard = []
        if WEBAPP_URL:
            keyboard.append([InlineKeyboardButton("Open Terminal", web_app={"url": WEBAPP_URL})])

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await update.message.reply_text(text, reply_markup=reply_markup)

    async def _handle_terminal(self, update, context):
        """Send a button that opens the Mini App terminal."""
        if not self._auth(str(update.effective_user.id)):
            await update.message.reply_text("Not authorized.")
            return

        if not WEBAPP_URL:
            await update.message.reply_text(
                "Mini App URL not configured.\n\n"
                "Set AGENTSTACK_WEBAPP_URL in .env to the HTTPS URL of your terminal server.\n"
                "Example: AGENTSTACK_WEBAPP_URL=https://your-domain.ngrok.io/static/terminal.html\n\n"
                "Meanwhile, use text commands: /spawn, /use, /to"
            )
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        # Generate a simple auth token from user ID + bot token
        user_id = str(update.effective_user.id)
        auth_token = hmac.new(TOKEN.encode(), user_id.encode(), hashlib.sha256).hexdigest()[:32]

        url = f"{WEBAPP_URL}?token={auth_token}"

        keyboard = [[InlineKeyboardButton("Open Terminal", web_app={"url": url})]]
        await update.message.reply_text(
            "Tap to open the terminal:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _handle_agents(self, update, context):
        if not self._auth(str(update.effective_user.id)):
            return
        self.reload_agents()
        if not self.agents:
            await update.message.reply_text("No agents configured. Edit agents.json.")
            return
        lines = ["Agent presets:\n"]
        for name, cfg in self.agents.items():
            status = " [RUNNING]" if self.sessions.has(name) else ""
            lines.append(f"  {name}{status}\n    {cfg.get('description', '')}")
        await update.message.reply_text("\n".join(lines))

    async def _handle_spawn(self, update, context):
        if not self._auth(str(update.effective_user.id)):
            await update.message.reply_text("Not authorized.")
            return
        if not context.args:
            await update.message.reply_text("Usage: /spawn <agent_name>\nSee /agents for presets.")
            return

        name = context.args[0].lower()
        chat_id = str(update.effective_chat.id)
        agent_cfg = self.agents.get(name)

        await update.message.reply_text(f"Starting '{name}'...")
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._spawn_agent, chat_id, name, agent_cfg)
        await update.message.reply_text(result)

    async def _handle_kill(self, update, context):
        if not self._auth(str(update.effective_user.id)):
            return
        if not context.args:
            await update.message.reply_text("Usage: /kill <agent_name>")
            return
        name = context.args[0].lower()
        chat_id = str(update.effective_chat.id)
        if self.sessions.destroy(name):
            if self.active_agent.get(chat_id) == name:
                del self.active_agent[chat_id]
            await update.message.reply_text(f"Agent '{name}' killed.")
        else:
            await update.message.reply_text(f"No active agent '{name}'.")

    async def _handle_killall(self, update, context):
        if not self._auth(str(update.effective_user.id)):
            return
        active = self.sessions.list_active()
        if not active:
            await update.message.reply_text("No active agents.")
            return
        self.sessions.destroy_all()
        self.active_agent.pop(str(update.effective_chat.id), None)
        await update.message.reply_text(f"Killed {len(active)} agent(s): {', '.join(active)}")

    async def _handle_sessions(self, update, context):
        if not self._auth(str(update.effective_user.id)):
            return
        chat_id = str(update.effective_chat.id)
        active = self.sessions.list_active()
        current = self.active_agent.get(chat_id, "none")
        if not active:
            await update.message.reply_text("No active agents. /spawn <name> to start one.")
            return
        lines = ["Active agents:\n"]
        for name in active:
            marker = " << active" if name == current else ""
            lines.append(f"  {name}{marker}")
        await update.message.reply_text("\n".join(lines))

    async def _handle_use(self, update, context):
        if not self._auth(str(update.effective_user.id)):
            return
        if not context.args:
            await update.message.reply_text("Usage: /use <agent_name>")
            return
        name = context.args[0].lower()
        chat_id = str(update.effective_chat.id)
        if not self.sessions.has(name):
            await update.message.reply_text(f"Agent '{name}' not running. /spawn {name} first.")
            return
        self.active_agent[chat_id] = name
        await update.message.reply_text(f"Switched to '{name}'.")

    async def _handle_to(self, update, context):
        if not self._auth(str(update.effective_user.id)):
            return
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("Usage: /to <agent_name> <message>")
            return
        name = context.args[0].lower()
        msg = " ".join(context.args[1:])
        if not self.sessions.has(name):
            await update.message.reply_text(f"Agent '{name}' not running.")
            return
        session = self.sessions.get(name)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, session.write, msg)

    async def _handle_broadcast(self, update, context):
        if not self._auth(str(update.effective_user.id)):
            return
        if not context.args:
            await update.message.reply_text("Usage: /broadcast <message>")
            return
        msg = " ".join(context.args)
        active = self.sessions.list_active()
        if not active:
            await update.message.reply_text("No active agents.")
            return
        loop = asyncio.get_event_loop()
        for name in active:
            session = self.sessions.get(name)
            if session:
                await loop.run_in_executor(None, session.write, msg)
        await update.message.reply_text(f"Broadcast to {len(active)}: {', '.join(active)}")

    async def _handle_sh(self, update, context):
        if not self._auth(str(update.effective_user.id)):
            return
        cmd_text = " ".join(context.args) if context.args else ""
        if not cmd_text:
            await update.message.reply_text("Usage: /sh <command>")
            return
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._run_sh, cmd_text)
        for chunk in self._split(result):
            await update.message.reply_text(f"```\n{chunk}\n```", parse_mode="Markdown")

    def _run_sh(self, cmd: str) -> str:
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=os.path.expanduser("~"))
            output = result.stdout
            if result.stderr:
                output += ("\n" if output else "") + result.stderr
            if result.returncode != 0:
                output += f"\n[exit code {result.returncode}]"
            return output.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return "[Timed out after 30s]"
        except Exception as e:
            return f"[Error: {e}]"

    async def _handle_reload(self, update, context):
        if not self._auth(str(update.effective_user.id)):
            return
        self.reload_agents()
        await update.message.reply_text(f"Reloaded {len(self.agents)} agent preset(s).")

    async def _handle_unknown_cmd(self, update, context):
        if not self._auth(str(update.effective_user.id)):
            return
        chat_id = str(update.effective_chat.id)
        name = self.active_agent.get(chat_id)
        if not name or not self.sessions.has(name):
            return
        text = update.message.text or ""
        session = self.sessions.get(name)
        if session and session.is_alive():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, session.write, text)

    async def _handle_message(self, update, context):
        user = update.effective_user
        chat_id = str(update.effective_chat.id)
        text = update.message.text or ""
        if not self._auth(str(user.id)):
            await update.message.reply_text("Not authorized.")
            return
        if not self._rate_ok(str(user.id)):
            await update.message.reply_text("Rate limited.")
            return
        if len(text) > MAX_MSG_LEN:
            await update.message.reply_text(f"Too long (max {MAX_MSG_LEN}).")
            return
        name = self.active_agent.get(chat_id)
        if not name or not self.sessions.has(name):
            await update.message.reply_text("No active agent. /spawn <name> to start one.")
            return
        session = self.sessions.get(name)
        if session and session.is_alive():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, session.write, text)

    # -- Lifecycle --

    def run(self):
        from telegram import Update
        from telegram.ext import Application, CommandHandler, MessageHandler, filters

        if not TOKEN:
            print("TELEGRAM_BOT_TOKEN not set.")
            sys.exit(1)

        self._app = Application.builder().token(TOKEN).build()

        handlers = {
            "start": self._handle_start,
            "help": self._handle_start,
            "terminal": self._handle_terminal,
            "agents": self._handle_agents,
            "spawn": self._handle_spawn,
            "kill": self._handle_kill,
            "killall": self._handle_killall,
            "sessions": self._handle_sessions,
            "use": self._handle_use,
            "to": self._handle_to,
            "broadcast": self._handle_broadcast,
            "sh": self._handle_sh,
            "reload": self._handle_reload,
        }
        for cmd, handler in handlers.items():
            self._app.add_handler(CommandHandler(cmd, handler))

        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        self._app.add_handler(MessageHandler(filters.COMMAND, self._handle_unknown_cmd))

        print("=" * 50)
        print("  AgentStack")
        print("  Multi-Agent Claude Code Manager")
        print("=" * 50)
        print(f"  Agents: {len(self.agents)}")
        print(f"  Users:  {ALLOWED_USERS or ['ALL']}")
        print(f"  WebApp: {WEBAPP_URL or 'not set'}")
        print()

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._run_polling(Update))
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.sessions.destroy_all()
            self._loop.close()

    async def _run_polling(self, Update):
        await self._app.initialize()
        try:
            await self._app.bot.get_updates(offset=-1, timeout=0)
        except Exception:
            pass
        await self._app.start()
        await self._app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        print("Bot is live. Send /start in Telegram.")
        print("Press Ctrl+C to stop.\n")

        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    bot = AgentStackBot()
    bot.run()
