"""
AgentStack local store — SQLite backend for tasks, agents, goals, activity.

Replaces the Paperclip dependency. Single file, zero external deps.
"""

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agentstack.db")

AGENT_ROLES = ["ceo", "cto", "cmo", "cfo", "engineer", "designer", "pm", "qa", "devops", "researcher", "general"]
ISSUE_STATUSES = ["backlog", "todo", "in_progress", "in_review", "done", "cancelled"]
PRIORITIES = ["urgent", "high", "medium", "low"]

_local = threading.local()


def _conn():
    if not hasattr(_local, 'conn') or _local.conn is None:
        c = sqlite3.connect(DB_PATH, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        _local.conn = c
    return _local.conn


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _id():
    return str(uuid.uuid4())


def init():
    """Create tables if they don't exist."""
    c = _conn()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            short_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'general',
            title TEXT,
            status TEXT NOT NULL DEFAULT 'idle',
            system_prompt TEXT,
            model TEXT,
            cwd TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS issues (
            id TEXT PRIMARY KEY,
            issue_number INTEGER NOT NULL,
            identifier TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'todo',
            priority TEXT NOT NULL DEFAULT 'medium',
            assignee_agent_id TEXT REFERENCES agents(id),
            parent_id TEXT REFERENCES issues(id),
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            cancelled_at TEXT
        );

        CREATE TABLE IF NOT EXISTS issue_comments (
            id TEXT PRIMARY KEY,
            issue_id TEXT NOT NULL REFERENCES issues(id),
            author TEXT NOT NULL DEFAULT 'board',
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS goals (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS activity (
            id TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id TEXT,
            details TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    # Initialize issue counter and prefix if not set
    cur = c.execute("SELECT value FROM config WHERE key = 'issue_prefix'")
    if not cur.fetchone():
        c.execute("INSERT INTO config (key, value) VALUES ('issue_prefix', 'AGE')")
        c.execute("INSERT INTO config (key, value) VALUES ('issue_counter', '0')")
        c.execute("INSERT INTO config (key, value) VALUES ('company_name', 'AgentStack HQ')")
    c.commit()


def _log_activity(c, action, entity_type=None, entity_id=None, details=None):
    c.execute(
        "INSERT INTO activity (id, action, entity_type, entity_id, details, created_at) VALUES (?,?,?,?,?,?)",
        (_id(), action, entity_type, entity_id, json.dumps(details) if details else None, _now()),
    )


def _dict(row):
    return dict(row) if row else None


def _dicts(rows):
    return [dict(r) for r in rows]


# ── Agents ───────────────────────────────────────────

def list_agents():
    c = _conn()
    rows = c.execute("SELECT * FROM agents ORDER BY created_at").fetchall()
    return _dicts(rows)


def create_agent(name, short_name, role="general", title="", system_prompt="", model="sonnet", cwd=""):
    c = _conn()
    aid = _id()
    now = _now()
    role = role if role in AGENT_ROLES else "general"
    c.execute(
        "INSERT INTO agents (id, name, short_name, role, title, system_prompt, model, cwd, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (aid, name, short_name, role, title or name, system_prompt, model, cwd, now),
    )
    _log_activity(c, "agent.created", "agent", aid, {"name": name, "role": role})
    c.commit()
    row = c.execute("SELECT * FROM agents WHERE id = ?", (aid,)).fetchone()
    return _dict(row)


def get_agent(agent_id):
    c = _conn()
    row = c.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    return _dict(row)


def update_agent(agent_id, **fields):
    c = _conn()
    allowed = {"name", "short_name", "role", "title", "status", "system_prompt", "model", "cwd"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_agent(agent_id)
    sets = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [agent_id]
    c.execute(f"UPDATE agents SET {sets} WHERE id = ?", vals)
    _log_activity(c, "agent.updated", "agent", agent_id, updates)
    c.commit()
    row = c.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    return _dict(row)


def delete_agent(agent_id):
    c = _conn()
    c.execute("UPDATE issues SET assignee_agent_id = NULL WHERE assignee_agent_id = ?", (agent_id,))
    c.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    _log_activity(c, "agent.deleted", "agent", agent_id)
    c.commit()


# ── Issues (Tasks) ───────────────────────────────────

def _next_identifier(c):
    row = c.execute("SELECT value FROM config WHERE key = 'issue_prefix'").fetchone()
    prefix = row["value"] if row else "AGE"
    row = c.execute("SELECT value FROM config WHERE key = 'issue_counter'").fetchone()
    counter = int(row["value"]) + 1 if row else 1
    c.execute("UPDATE config SET value = ? WHERE key = 'issue_counter'", (str(counter),))
    return counter, f"{prefix}-{counter}"


def list_issues(status=None, assignee_agent_id=None):
    c = _conn()
    q = "SELECT * FROM issues WHERE 1=1"
    params = []
    if status:
        q += " AND status = ?"
        params.append(status)
    if assignee_agent_id:
        q += " AND assignee_agent_id = ?"
        params.append(assignee_agent_id)
    q += " ORDER BY created_at DESC"
    rows = c.execute(q, params).fetchall()
    return _dicts(rows)


def create_issue(title, description="", priority="medium", assignee_agent_id=None):
    c = _conn()
    iid = _id()
    now = _now()
    number, identifier = _next_identifier(c)
    priority = priority if priority in PRIORITIES else "medium"
    c.execute(
        "INSERT INTO issues (id, issue_number, identifier, title, description, status, priority, assignee_agent_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (iid, number, identifier, title, description, "todo", priority, assignee_agent_id, now),
    )
    _log_activity(c, "issue.created", "issue", iid, {"identifier": identifier, "title": title})
    c.commit()
    row = c.execute("SELECT * FROM issues WHERE id = ?", (iid,)).fetchone()
    return _dict(row)


def get_issue(issue_id_or_identifier):
    c = _conn()
    row = c.execute("SELECT * FROM issues WHERE id = ? OR identifier = ?", (issue_id_or_identifier, issue_id_or_identifier.upper() if isinstance(issue_id_or_identifier, str) else issue_id_or_identifier)).fetchone()
    return _dict(row)


def update_issue(issue_id, **fields):
    c = _conn()
    allowed = {"title", "description", "status", "priority", "assignee_agent_id", "parent_id"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_issue(issue_id)

    # Side effects for status changes
    now = _now()
    if "status" in updates:
        s = updates["status"]
        if s == "in_progress":
            updates["started_at"] = now
        elif s == "done":
            updates["completed_at"] = now
        elif s == "cancelled":
            updates["cancelled_at"] = now

    sets = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [issue_id]
    c.execute(f"UPDATE issues SET {sets} WHERE id = ?", vals)
    _log_activity(c, "issue.updated", "issue", issue_id, updates)
    c.commit()
    row = c.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
    return _dict(row)


# ── Comments ─────────────────────────────────────────

def add_comment(issue_id, body, author="board"):
    c = _conn()
    cid = _id()
    now = _now()
    c.execute(
        "INSERT INTO issue_comments (id, issue_id, author, body, created_at) VALUES (?,?,?,?,?)",
        (cid, issue_id, author, body, now),
    )
    _log_activity(c, "comment.added", "issue", issue_id, {"body": body[:100]})
    c.commit()
    row = c.execute("SELECT * FROM issue_comments WHERE id = ?", (cid,)).fetchone()
    return _dict(row)


def list_comments(issue_id):
    c = _conn()
    rows = c.execute("SELECT * FROM issue_comments WHERE issue_id = ? ORDER BY created_at", (issue_id,)).fetchall()
    return _dicts(rows)


# ── Goals ────────────────────────────────────────────

def list_goals():
    c = _conn()
    rows = c.execute("SELECT * FROM goals ORDER BY created_at").fetchall()
    return _dicts(rows)


def create_goal(title, description=""):
    c = _conn()
    gid = _id()
    now = _now()
    c.execute(
        "INSERT INTO goals (id, title, description, created_at) VALUES (?,?,?,?)",
        (gid, title, description, now),
    )
    _log_activity(c, "goal.created", "goal", gid, {"title": title})
    c.commit()
    row = c.execute("SELECT * FROM goals WHERE id = ?", (gid,)).fetchone()
    return _dict(row)


# ── Activity ─────────────────────────────────────────

def get_activity(limit=20):
    c = _conn()
    rows = c.execute("SELECT * FROM activity ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return _dicts(rows)


# ── Config ───────────────────────────────────────────

def get_config(key, default=None):
    c = _conn()
    row = c.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_config(key, value):
    c = _conn()
    c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
    c.commit()


# ── Stats ────────────────────────────────────────────

def get_stats():
    c = _conn()
    agents = c.execute("SELECT COUNT(*) as n FROM agents").fetchone()["n"]
    total = c.execute("SELECT COUNT(*) as n FROM issues").fetchone()["n"]
    todo = c.execute("SELECT COUNT(*) as n FROM issues WHERE status = 'todo'").fetchone()["n"]
    wip = c.execute("SELECT COUNT(*) as n FROM issues WHERE status = 'in_progress'").fetchone()["n"]
    done = c.execute("SELECT COUNT(*) as n FROM issues WHERE status = 'done'").fetchone()["n"]
    goals = c.execute("SELECT COUNT(*) as n FROM goals").fetchone()["n"]
    return {"agents": agents, "tasks_total": total, "tasks_todo": todo, "tasks_wip": wip, "tasks_done": done, "goals": goals}


# ── Formatting helpers ───────────────────────────────

def fmt_issue(issue):
    status_icons = {
        "todo": "[ ]", "in_progress": "[~]", "in_review": "[?]",
        "done": "[x]", "cancelled": "[-]", "backlog": "[.]",
    }
    priority_icons = {"urgent": "!!!", "high": "!!", "medium": "!", "low": "."}
    s = status_icons.get(issue.get("status", ""), "[ ]")
    p = priority_icons.get(issue.get("priority", ""), "")
    ident = issue.get("identifier", "")
    title = issue.get("title", "")
    assignee = ""
    if issue.get("assignee_agent_id"):
        agent = get_agent(issue["assignee_agent_id"])
        if agent:
            assignee = f" @{agent['short_name']}"
    return f"{s} {ident} {p} {title}{assignee}"


def fmt_agent(agent):
    status_icons = {"idle": "(-)", "active": "(*)", "terminated": "(x)"}
    s = status_icons.get(agent.get("status", ""), "(?)")
    return f"{s} {agent['name']} [{agent.get('role', '')}] - {agent.get('title', '')}"


# ── Sync agents.json → DB ───────────────────────────

def sync_agents_from_json(agents_file):
    """Import agent presets from agents.json into the DB if they don't exist."""
    if not os.path.exists(agents_file):
        return
    with open(agents_file) as f:
        data = json.load(f).get("agents", {})

    existing = {a["short_name"]: a for a in list_agents()}
    for key, cfg in data.items():
        if key not in existing:
            create_agent(
                name=key.capitalize(),
                short_name=key,
                role=_guess_role(cfg.get("description", "")),
                title=cfg.get("description", "")[:80],
                system_prompt=cfg.get("prompt", ""),
                model=cfg.get("model", "sonnet"),
                cwd=cfg.get("cwd", ""),
            )


def _guess_role(desc):
    desc = desc.lower()
    if "copywrite" in desc or "writer" in desc or "content" in desc:
        return "general"
    if "research" in desc or "analyst" in desc or "scout" in desc:
        return "researcher"
    if "develop" in desc or "code" in desc or "engineer" in desc:
        return "engineer"
    if "crm" in desc or "manage" in desc or "pm" in desc:
        return "pm"
    for role in ["designer", "qa", "devops"]:
        if role in desc:
            return role
    return "general"


# Auto-init on import
init()
