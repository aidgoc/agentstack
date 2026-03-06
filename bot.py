#!/usr/bin/env python3
"""
AgentStack — 1 computer, 1 bot, 1 owner, unlimited terminals from Telegram.

Open a full terminal inside Telegram Mini App. Run claude, ssh, anything.
Only the owner (OWNER_ID) can use this bot. Everyone else is ignored.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)

import users
import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("agentstack")

BOT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
AGENTS_FILE = BOT_DIR / "agents.json"

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OWNER_ID = os.getenv("OWNER_ID", "")
WEBAPP_URL = os.getenv("AGENTSTACK_WEBAPP_URL", "")

MAX_MSG_LEN = 4000


def _owner_only(handler):
    """Decorator: silently ignore non-owner messages."""
    async def wrapper(self, update, context):
        if not users.is_owner(update.effective_user.id):
            return
        return await handler(self, update, context)
    return wrapper


class AgentStackBot:
    def __init__(self):
        self.agents = self._load_agents()
        self._app = None
        self._loop = None
        # Sync agents.json presets into local DB
        store.sync_agents_from_json(str(AGENTS_FILE))

    def _load_agents(self) -> dict:
        if AGENTS_FILE.exists():
            with open(AGENTS_FILE) as f:
                return json.load(f).get("agents", {})
        return {}

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

    # ── Handlers ──────────────────────────────────────

    @_owner_only
    async def _handle_start(self, update, context):
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        text = (
            "AgentStack\n"
            "================================\n"
            "Your personal terminal, from Telegram.\n\n"
            "Tap 'Open Terminal' to get a full shell.\n"
            "Run claude, ssh — anything.\n\n"
            "Commands:\n"
            "  /terminal - Open terminal\n"
            "  /sh <cmd> - Quick shell command\n\n"
            "Org:\n"
            "  /org  /tasks  /task  /team\n"
            "  /hire  /goals  /activity  /done"
        )

        keyboard = []
        if WEBAPP_URL:
            token = users.make_web_token()
            keyboard.append([InlineKeyboardButton("Open Terminal", web_app={"url": f"{WEBAPP_URL}?token={token}"})])

        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)

    @_owner_only
    async def _handle_terminal(self, update, context):
        if not WEBAPP_URL:
            await update.message.reply_text("Terminal not available. Cloudflare tunnel may be down.")
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        token = users.make_web_token()
        keyboard = [[InlineKeyboardButton("Open Terminal", web_app={"url": f"{WEBAPP_URL}?token={token}"})]]
        await update.message.reply_text("Tap to open:", reply_markup=InlineKeyboardMarkup(keyboard))

    @_owner_only
    async def _handle_sh(self, update, context):
        cmd_text = " ".join(context.args) if context.args else ""
        if not cmd_text:
            await update.message.reply_text("Usage: /sh <command>")
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, self._run_sh, cmd_text)
        for chunk in self._split(result):
            await update.message.reply_text(f"```\n{chunk}\n```", parse_mode="Markdown")

    def _run_sh(self, cmd: str) -> str:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=os.path.expanduser("~"))
            out = r.stdout
            if r.stderr:
                out += ("\n" if out else "") + r.stderr
            if r.returncode != 0:
                out += f"\n[exit code {r.returncode}]"
            return out.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return "[Timed out after 30s]"
        except Exception as e:
            return f"[Error: {e}]"

    # ── Org & Tasks (local SQLite) ─────────────────────

    @_owner_only
    async def _handle_org(self, update, context):
        try:
            stats = store.get_stats()
            agents = store.list_agents()
            name = store.get_config("company_name", "AgentStack HQ")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
            return

        agent_lines = "\n".join(f"  {store.fmt_agent(a)}" for a in agents) or "  (none)"

        await update.message.reply_text(
            f"{'=' * 35}\n  {name}\n{'=' * 35}\n"
            f"Agents: {stats['agents']}\n{agent_lines}\n\n"
            f"Tasks: {stats['tasks_total']}  (todo:{stats['tasks_todo']} wip:{stats['tasks_wip']} done:{stats['tasks_done']})\n"
            f"Goals: {stats['goals']}\n\n"
            "/tasks /task /assign /team /hire /goals /activity /done"
        )

    @_owner_only
    async def _handle_tasks(self, update, context):
        try:
            status = context.args[0] if context.args else None
            issues = store.list_issues(status=status)
        except Exception as e:
            await update.message.reply_text(f"Error: {e}"); return
        if not issues:
            await update.message.reply_text("No tasks. /task <title> to create one."); return
        lines = ["Tasks:\n"] + [f"  {store.fmt_issue(i)}" for i in issues[:25]]
        if len(issues) > 25: lines.append(f"\n  ... +{len(issues)-25} more")
        await update.message.reply_text("\n".join(lines))

    @_owner_only
    async def _handle_task(self, update, context):
        if not context.args:
            await update.message.reply_text("/task <title> or /task AGE-1"); return

        first = context.args[0]
        if "-" in first and first.split("-")[0].isalpha():
            try:
                issue = store.get_issue(first)
                if not issue:
                    await update.message.reply_text(f"Task '{first}' not found."); return
                comments = store.list_comments(issue["id"])
                assignee = "unassigned"
                if issue.get("assignee_agent_id"):
                    agent = store.get_agent(issue["assignee_agent_id"])
                    if agent:
                        assignee = agent["name"]
                text = f"{issue['identifier']} - {issue['title']}\nStatus: {issue['status']}  Priority: {issue['priority']}\nAssigned: {assignee}"
                if issue.get("description"): text += f"\n\n{issue['description']}"
                if comments:
                    text += f"\n\nComments ({len(comments)}):"
                    for cm in comments[-5:]:
                        text += f"\n  [{cm['author']}] {cm['body'][:100]}"
                await update.message.reply_text(text)
            except Exception as e:
                await update.message.reply_text(f"Error: {e}")
            return

        try:
            issue = store.create_issue(" ".join(context.args))
            await update.message.reply_text(f"Created: {issue['identifier']} - {issue['title']}")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    @_owner_only
    async def _handle_assign(self, update, context):
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("/assign <task-id> <agent-name>"); return
        try:
            agents = store.list_agents()
            name = context.args[1].lower()
            agent = next((a for a in agents if a["name"].lower() == name or a["short_name"].lower() == name), None)
            if not agent:
                await update.message.reply_text(f"Agent '{name}' not found. Have: {', '.join(a['name'] for a in agents)}"); return
            issue = store.get_issue(context.args[0])
            if not issue:
                await update.message.reply_text(f"Task '{context.args[0]}' not found."); return
            store.update_issue(issue["id"], assignee_agent_id=agent["id"])
            await update.message.reply_text(f"Assigned {issue['identifier']} to {agent['name']}")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    @_owner_only
    async def _handle_team(self, update, context):
        try:
            agents = store.list_agents()
        except Exception as e:
            await update.message.reply_text(f"Error: {e}"); return
        if not agents:
            await update.message.reply_text("No agents. /hire <name> <role>"); return
        await update.message.reply_text("Team:\n" + "\n".join(f"  {store.fmt_agent(a)}" for a in agents))

    @_owner_only
    async def _handle_hire(self, update, context):
        if not context.args:
            await update.message.reply_text(f"/hire <name> [role]\nRoles: {', '.join(store.AGENT_ROLES)}"); return
        name = context.args[0]
        role = context.args[1].lower() if len(context.args) > 1 else "general"
        try:
            agent = store.create_agent(name, name.lower().replace(" ", "-"), role=role, title=name)
            await update.message.reply_text(f"Hired: {store.fmt_agent(agent)}")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    @_owner_only
    async def _handle_goals(self, update, context):
        if context.args:
            try:
                goal = store.create_goal(" ".join(context.args))
                await update.message.reply_text(f"Goal created: {goal.get('title')}")
            except Exception as e:
                await update.message.reply_text(f"Error: {e}")
            return
        try:
            goals = store.list_goals()
        except Exception as e:
            await update.message.reply_text(f"Error: {e}"); return
        if not goals:
            await update.message.reply_text("No goals. /goals <title>"); return
        await update.message.reply_text("Goals:\n" + "\n".join(f"  - {g.get('title')}" for g in goals))

    @_owner_only
    async def _handle_activity(self, update, context):
        try:
            activity = store.get_activity(limit=15)
        except Exception as e:
            await update.message.reply_text(f"Error: {e}"); return
        if not activity:
            await update.message.reply_text("No activity."); return
        lines = ["Activity:\n"]
        for a in activity[:15]:
            action = a.get("action", "?").replace(".", " ").replace("_", " ")
            lines.append(f"  {action}")
        await update.message.reply_text("\n".join(lines))

    @_owner_only
    async def _handle_comment(self, update, context):
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("/comment <task-id> <message>"); return
        try:
            issue = store.get_issue(context.args[0])
            if not issue:
                await update.message.reply_text(f"Task '{context.args[0]}' not found."); return
            store.add_comment(issue["id"], " ".join(context.args[1:]))
            await update.message.reply_text(f"Comment added to {issue['identifier']}")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    @_owner_only
    async def _handle_done(self, update, context):
        if not context.args:
            await update.message.reply_text("/done <task-id>"); return
        try:
            issue = store.get_issue(context.args[0])
            if not issue:
                await update.message.reply_text(f"Task '{context.args[0]}' not found."); return
            store.update_issue(issue["id"], status="done")
            await update.message.reply_text(f"Done: {issue['identifier']} - {issue['title']}")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    # ── Run ───────────────────────────────────────────

    def run(self):
        from telegram import Update
        from telegram.ext import Application, CommandHandler, MessageHandler, filters

        if not TOKEN:
            print("TELEGRAM_BOT_TOKEN not set."); sys.exit(1)
        if not OWNER_ID:
            print("OWNER_ID not set. Add your Telegram user ID to .env"); sys.exit(1)

        self._app = Application.builder().token(TOKEN).build()

        for cmd, handler in {
            "start": self._handle_start,
            "help": self._handle_start,
            "terminal": self._handle_terminal,
            "sh": self._handle_sh,
            "org": self._handle_org,
            "tasks": self._handle_tasks,
            "task": self._handle_task,
            "assign": self._handle_assign,
            "team": self._handle_team,
            "hire": self._handle_hire,
            "goals": self._handle_goals,
            "activity": self._handle_activity,
            "comment": self._handle_comment,
            "done": self._handle_done,
        }.items():
            self._app.add_handler(CommandHandler(cmd, handler))

        print("=" * 40)
        print("  AgentStack")
        print("  1 machine, 1 bot, 1 owner")
        print("=" * 40)
        print(f"  Owner:   {OWNER_ID}")
        print(f"  WebApp:  {WEBAPP_URL or 'not set'}")
        print()

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._run_polling(Update))
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self._loop.close()

    async def _run_polling(self, Update):
        await self._app.initialize()
        try:
            await self._app.bot.get_updates(offset=-1, timeout=0)
        except Exception:
            pass
        await self._app.start()
        await self._app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        print("Bot is live. Send /start in Telegram.")
        print("Press Ctrl+C to stop.\n")
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    AgentStackBot().run()
