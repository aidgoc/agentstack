#!/usr/bin/env python3
"""
AgentStack - Multi-user, multi-agent Claude Code manager via Telegram.

Any user can connect, provide their own Anthropic API key, and spawn
unlimited Claude Code agents. Each user's sessions are fully isolated.

Commands:
  /start               - Onboarding + help
  /terminal            - Open the full terminal Mini App
  /key <api_key>       - Set your Anthropic API key
  /agents              - List agent presets
  /spawn <name>        - Start a Claude Code agent
  /kill <name>         - Kill an agent
  /sessions            - List your active sessions
  /to <name> <msg>     - Message a specific agent
  /use <name>          - Switch active agent (text mode)
  /broadcast <msg>     - Message all your agents
  /killall             - Kill all your agents
  /sh <cmd>            - Run a shell command
  /logout              - Remove your API key and kill sessions
"""

import asyncio
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

import users
from terminal import SessionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("agentstack")

BOT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
AGENTS_FILE = BOT_DIR / "agents.json"

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_USERS = [s.strip() for s in os.getenv("TELEGRAM_ADMIN_USERS", "").split(",") if s.strip()]
WEBAPP_URL = os.getenv("AGENTSTACK_WEBAPP_URL", "")
MAX_SESSIONS_PER_USER = int(os.getenv("MAX_SESSIONS_PER_USER", "10"))

MAX_MSG_LEN = 4000
RATE_LIMIT = 25
RATE_WINDOW = 60


class AgentStackBot:
    def __init__(self):
        self.sessions = SessionManager()
        self.agents = self._load_agents()
        self.active_agent: dict[str, str] = {}  # chat_id -> session_key
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

    def _is_admin(self, user_id: str) -> bool:
        return user_id in ADMIN_USERS

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

    def _user_session_count(self, user_id: str) -> int:
        all_active = self.sessions.list_active()
        return len(users.user_sessions(user_id, all_active))

    def _user_sessions(self, user_id: str) -> list[str]:
        all_active = self.sessions.list_active()
        return users.user_sessions(user_id, all_active)

    def _ensure_user(self, tg_user) -> dict:
        """Ensure user exists in DB, return user dict."""
        uid = str(tg_user.id)
        user = users.get_user(uid)
        if not user:
            user = users.create_user(uid, tg_user.username or "", tg_user.first_name or "")
        users.touch_user(uid)
        return user

    def _build_claude_cmd(self, agent_cfg: dict = None) -> list[str]:
        cmd = ["claude"]
        if agent_cfg and agent_cfg.get("prompt"):
            cmd.extend(["--system-prompt", agent_cfg["prompt"]])
        return cmd

    def _spawn_agent(self, user_id: str, chat_id: str, name: str, api_key: str, agent_cfg: dict = None) -> str:
        skey = users.session_key(user_id, name)

        if self.sessions.has(skey):
            return f"Agent '{name}' is already running.\n/kill {name} to stop it, or /use {name} to switch."

        if self._user_session_count(user_id) >= MAX_SESSIONS_PER_USER:
            return f"Session limit reached ({MAX_SESSIONS_PER_USER}). /kill an agent first."

        cmd = self._build_claude_cmd(agent_cfg)
        cwd = agent_cfg.get("cwd", os.path.expanduser("~")) if agent_cfg else os.path.expanduser("~")
        os.makedirs(cwd, exist_ok=True)

        # Pass the user's API key as env var to the Claude Code process
        env_override = {"ANTHROPIC_API_KEY": api_key} if api_key else {}

        def on_output(session_name: str, text: str):
            self._send_output(chat_id, text)
            if not self.sessions.has(session_name):
                self._send(chat_id, f"Agent '{name}' has exited.")

        try:
            self.sessions.create(skey, cmd, cwd=cwd, on_output=on_output, env_override=env_override)
        except Exception as e:
            return f"Failed to spawn '{name}': {e}"

        self.active_agent[chat_id] = skey

        desc = f"\n{agent_cfg['description']}" if agent_cfg and agent_cfg.get("description") else ""
        return (
            f"Agent '{name}' started.{desc}\n\n"
            f"Active agent: '{name}'\n"
            f"Use /terminal for the full terminal UI."
        )

    # -- Handlers --

    async def _handle_start(self, update, context):
        tg_user = update.effective_user
        user = self._ensure_user(tg_user)

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        has_key = bool(user.get("api_key"))

        if not has_key:
            text = (
                f"Welcome to AgentStack, {tg_user.first_name}!\n\n"
                "AgentStack lets you run multiple Claude Code AI agents "
                "from your phone. Each agent is a full Claude Code instance "
                "that can code, research, write, and more.\n\n"
                "To get started, set your Anthropic API key:\n"
                "  /key sk-ant-...\n\n"
                "Get a key at: https://console.anthropic.com/settings/keys\n\n"
                "Your key is stored securely and only used to run "
                "Claude Code on your behalf."
            )
            await update.message.reply_text(text)
            return

        agents_list = "\n".join(f"  {n} - {a.get('description', '')}" for n, a in self.agents.items())
        my_sessions = self._user_sessions(str(tg_user.id))
        session_info = f"  Active: {', '.join(my_sessions)}" if my_sessions else "  No active agents"

        text = (
            f"AgentStack\n"
            "================================\n"
            f"  API Key: ...{user['api_key'][-8:]}\n"
            f"{session_info}\n\n"
            "Commands:\n"
            "  /terminal      - Full terminal UI\n"
            "  /spawn <name>  - Start an agent\n"
            "  /kill <name>   - Kill an agent\n"
            "  /sessions      - List your agents\n"
            "  /to <name> <msg> - Message agent\n"
            "  /use <name>    - Switch active agent\n"
            "  /broadcast <msg> - Message all\n"
            "  /killall       - Kill all your agents\n"
            "  /key <key>     - Update API key\n"
            "  /logout        - Remove key + kill all\n\n"
            f"Agent presets:\n{agents_list}"
        )

        keyboard = []
        if WEBAPP_URL:
            token = users.make_web_token(str(tg_user.id))
            url = f"{WEBAPP_URL}?token={token}"
            keyboard.append([InlineKeyboardButton("Open Terminal", web_app={"url": url})])

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await update.message.reply_text(text, reply_markup=reply_markup)

    async def _handle_key(self, update, context):
        tg_user = update.effective_user
        uid = str(tg_user.id)
        self._ensure_user(tg_user)

        if not context.args:
            user = users.get_user(uid)
            if user and user["api_key"]:
                await update.message.reply_text(f"API key set: ...{user['api_key'][-8:]}\n\nTo change: /key sk-ant-...")
            else:
                await update.message.reply_text("No API key set.\n\nUsage: /key sk-ant-api03-...")
            return

        key = context.args[0].strip()
        if not key.startswith("sk-ant-"):
            await update.message.reply_text("That doesn't look like an Anthropic API key.\nIt should start with: sk-ant-")
            return

        users.set_api_key(uid, key)

        # Delete the message containing the key for security
        try:
            await update.message.delete()
        except Exception:
            pass

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"API key saved (ending ...{key[-8:]})\n\n"
                 "Your key message was deleted for security.\n"
                 "You're ready! Try: /spawn dev",
        )

    async def _handle_terminal(self, update, context):
        tg_user = update.effective_user
        uid = str(tg_user.id)
        user = self._ensure_user(tg_user)

        if not user.get("api_key"):
            await update.message.reply_text("Set your API key first: /key sk-ant-...")
            return

        if not WEBAPP_URL:
            await update.message.reply_text(
                "Terminal UI not available.\n"
                "Use text commands: /spawn, /use, /to"
            )
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        token = users.make_web_token(uid)
        url = f"{WEBAPP_URL}?token={token}"

        keyboard = [[InlineKeyboardButton("Open Terminal", web_app={"url": url})]]
        await update.message.reply_text(
            "Tap to open:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _handle_agents(self, update, context):
        self._ensure_user(update.effective_user)
        self.reload_agents()
        if not self.agents:
            await update.message.reply_text("No agent presets configured.")
            return
        lines = ["Agent presets:\n"]
        uid = str(update.effective_user.id)
        for name, cfg in self.agents.items():
            skey = users.session_key(uid, name)
            status = " [RUNNING]" if self.sessions.has(skey) else ""
            lines.append(f"  {name}{status}\n    {cfg.get('description', '')}")
        await update.message.reply_text("\n".join(lines))

    async def _handle_spawn(self, update, context):
        tg_user = update.effective_user
        uid = str(tg_user.id)
        user = self._ensure_user(tg_user)

        if not user.get("api_key"):
            await update.message.reply_text("Set your API key first: /key sk-ant-...")
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
        result = await loop.run_in_executor(
            None, self._spawn_agent, uid, chat_id, name, user["api_key"], agent_cfg
        )
        await update.message.reply_text(result)

    async def _handle_kill(self, update, context):
        uid = str(update.effective_user.id)
        self._ensure_user(update.effective_user)

        if not context.args:
            await update.message.reply_text("Usage: /kill <agent_name>")
            return

        name = context.args[0].lower()
        skey = users.session_key(uid, name)
        chat_id = str(update.effective_chat.id)

        if self.sessions.destroy(skey):
            if self.active_agent.get(chat_id) == skey:
                del self.active_agent[chat_id]
            await update.message.reply_text(f"Agent '{name}' killed.")
        else:
            await update.message.reply_text(f"No active agent '{name}'.")

    async def _handle_killall(self, update, context):
        uid = str(update.effective_user.id)
        self._ensure_user(update.effective_user)
        chat_id = str(update.effective_chat.id)

        my_sessions = self._user_sessions(uid)
        if not my_sessions:
            await update.message.reply_text("No active agents.")
            return

        for name in my_sessions:
            self.sessions.destroy(users.session_key(uid, name))
        self.active_agent.pop(chat_id, None)
        await update.message.reply_text(f"Killed {len(my_sessions)} agent(s): {', '.join(my_sessions)}")

    async def _handle_sessions(self, update, context):
        uid = str(update.effective_user.id)
        self._ensure_user(update.effective_user)
        chat_id = str(update.effective_chat.id)

        my_sessions = self._user_sessions(uid)
        active_skey = self.active_agent.get(chat_id, "")
        active_name = users.parse_session_key(active_skey)[1] if active_skey else ""

        if not my_sessions:
            await update.message.reply_text("No active agents. /spawn <name> to start one.")
            return

        lines = ["Your agents:\n"]
        for name in my_sessions:
            marker = " << active" if name == active_name else ""
            lines.append(f"  {name}{marker}")
        await update.message.reply_text("\n".join(lines))

    async def _handle_use(self, update, context):
        uid = str(update.effective_user.id)
        self._ensure_user(update.effective_user)

        if not context.args:
            await update.message.reply_text("Usage: /use <agent_name>")
            return

        name = context.args[0].lower()
        skey = users.session_key(uid, name)
        chat_id = str(update.effective_chat.id)

        if not self.sessions.has(skey):
            await update.message.reply_text(f"Agent '{name}' not running. /spawn {name} first.")
            return

        self.active_agent[chat_id] = skey
        await update.message.reply_text(f"Switched to '{name}'.")

    async def _handle_to(self, update, context):
        uid = str(update.effective_user.id)
        self._ensure_user(update.effective_user)

        if not context.args or len(context.args) < 2:
            await update.message.reply_text("Usage: /to <agent_name> <message>")
            return

        name = context.args[0].lower()
        msg = " ".join(context.args[1:])
        skey = users.session_key(uid, name)

        if not self.sessions.has(skey):
            await update.message.reply_text(f"Agent '{name}' not running.")
            return

        session = self.sessions.get(skey)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, session.write, msg)

    async def _handle_broadcast(self, update, context):
        uid = str(update.effective_user.id)
        self._ensure_user(update.effective_user)

        if not context.args:
            await update.message.reply_text("Usage: /broadcast <message>")
            return

        msg = " ".join(context.args)
        my_sessions = self._user_sessions(uid)

        if not my_sessions:
            await update.message.reply_text("No active agents.")
            return

        loop = asyncio.get_event_loop()
        for name in my_sessions:
            skey = users.session_key(uid, name)
            session = self.sessions.get(skey)
            if session:
                await loop.run_in_executor(None, session.write, msg)
        await update.message.reply_text(f"Broadcast to {len(my_sessions)}: {', '.join(my_sessions)}")

    async def _handle_sh(self, update, context):
        uid = str(update.effective_user.id)
        user = self._ensure_user(update.effective_user)
        if not user.get("api_key"):
            await update.message.reply_text("Set your API key first: /key sk-ant-...")
            return

        if not self._is_admin(uid):
            await update.message.reply_text("Shell access is admin-only for security.")
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

    async def _handle_logout(self, update, context):
        uid = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)

        # Kill all user sessions
        my_sessions = self._user_sessions(uid)
        for name in my_sessions:
            self.sessions.destroy(users.session_key(uid, name))
        self.active_agent.pop(chat_id, None)

        # Remove API key
        users.set_api_key(uid, "")
        await update.message.reply_text(
            f"Logged out. Killed {len(my_sessions)} agent(s).\n"
            "API key removed. Use /key to set a new one."
        )

    async def _handle_reload(self, update, context):
        uid = str(update.effective_user.id)
        if not self._is_admin(uid):
            return
        self.reload_agents()
        await update.message.reply_text(f"Reloaded {len(self.agents)} agent preset(s).")

    async def _handle_admin(self, update, context):
        """Admin-only: list all users and sessions."""
        uid = str(update.effective_user.id)
        if not self._is_admin(uid):
            return

        all_users = users.get_all_users()
        all_sessions = self.sessions.list_active()

        lines = [f"Users: {len(all_users)}  |  Sessions: {len(all_sessions)}\n"]
        for u in all_users:
            key_status = f"...{u['api_key'][-8:]}" if u["api_key"] else "no key"
            u_sessions = users.user_sessions(u["user_id"], all_sessions)
            sess_info = f" [{len(u_sessions)} agents]" if u_sessions else ""
            lines.append(f"  @{u['username'] or u['user_id']} ({key_status}){sess_info}")

        await update.message.reply_text("\n".join(lines))

    async def _handle_unknown_cmd(self, update, context):
        uid = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        skey = self.active_agent.get(chat_id)
        if not skey or not self.sessions.has(skey):
            return
        text = update.message.text or ""
        session = self.sessions.get(skey)
        if session and session.is_alive():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, session.write, text)

    async def _handle_message(self, update, context):
        tg_user = update.effective_user
        uid = str(tg_user.id)
        chat_id = str(update.effective_chat.id)
        text = update.message.text or ""

        user = self._ensure_user(tg_user)

        if not self._rate_ok(uid):
            await update.message.reply_text("Rate limited.")
            return

        if not user.get("api_key"):
            await update.message.reply_text(
                "Welcome! Set your Anthropic API key to get started:\n"
                "  /key sk-ant-..."
            )
            return

        if len(text) > MAX_MSG_LEN:
            await update.message.reply_text(f"Too long (max {MAX_MSG_LEN}).")
            return

        skey = self.active_agent.get(chat_id)
        if not skey or not self.sessions.has(skey):
            await update.message.reply_text("No active agent. /spawn <name> to start one.")
            return

        session = self.sessions.get(skey)
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
            "key": self._handle_key,
            "agents": self._handle_agents,
            "spawn": self._handle_spawn,
            "kill": self._handle_kill,
            "killall": self._handle_killall,
            "sessions": self._handle_sessions,
            "use": self._handle_use,
            "to": self._handle_to,
            "broadcast": self._handle_broadcast,
            "sh": self._handle_sh,
            "logout": self._handle_logout,
            "reload": self._handle_reload,
            "admin": self._handle_admin,
        }
        for cmd, handler in handlers.items():
            self._app.add_handler(CommandHandler(cmd, handler))

        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        self._app.add_handler(MessageHandler(filters.COMMAND, self._handle_unknown_cmd))

        user_count = len(users.get_all_users())
        print("=" * 50)
        print("  AgentStack")
        print("  Multi-User Claude Code Manager")
        print("=" * 50)
        print(f"  Agents:  {len(self.agents)} presets")
        print(f"  Users:   {user_count} registered")
        print(f"  Admins:  {ADMIN_USERS or ['none']}")
        print(f"  Limit:   {MAX_SESSIONS_PER_USER} sessions/user")
        print(f"  WebApp:  {WEBAPP_URL or 'not set'}")
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
