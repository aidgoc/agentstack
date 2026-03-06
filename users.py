"""User management for AgentStack.

Stores user data in SQLite: Telegram ID, API key, preferences.
Each user's sessions are namespaced by their Telegram user ID.
"""

import hashlib
import hmac
import json
import os
import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(os.path.dirname(os.path.abspath(__file__))) / "data" / "users.db"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

_lock = threading.Lock()


def _get_db() -> sqlite3.Connection:
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            api_key TEXT DEFAULT '',
            max_sessions INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


_db: sqlite3.Connection | None = None


def db() -> sqlite3.Connection:
    global _db
    if _db is None:
        _db = _get_db()
    return _db


def get_user(user_id: str) -> dict | None:
    with _lock:
        row = db().execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            return dict(row)
    return None


def create_user(user_id: str, username: str = "", first_name: str = "") -> dict:
    with _lock:
        db().execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            (user_id, username, first_name),
        )
        db().commit()
    return get_user(user_id)


def set_api_key(user_id: str, api_key: str):
    with _lock:
        db().execute("UPDATE users SET api_key = ? WHERE user_id = ?", (api_key, user_id))
        db().commit()


def get_api_key(user_id: str) -> str:
    user = get_user(user_id)
    return user["api_key"] if user else ""


def touch_user(user_id: str):
    with _lock:
        db().execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        db().commit()


def get_all_users() -> list[dict]:
    with _lock:
        rows = db().execute("SELECT * FROM users ORDER BY last_active DESC").fetchall()
        return [dict(r) for r in rows]


def delete_user(user_id: str):
    with _lock:
        db().execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        db().commit()


# -- Session namespacing --

def session_key(user_id: str, agent_name: str) -> str:
    """Unique session key: user_id:agent_name"""
    return f"{user_id}:{agent_name}"


def parse_session_key(key: str) -> tuple[str, str]:
    """Returns (user_id, agent_name)"""
    parts = key.split(":", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def user_sessions(user_id: str, all_sessions: list[str]) -> list[str]:
    """Filter session keys to only this user's, return agent names."""
    prefix = f"{user_id}:"
    return [k[len(prefix):] for k in all_sessions if k.startswith(prefix)]


# -- Auth tokens for Mini App --

def make_web_token(user_id: str) -> str:
    """Generate an HMAC token for Mini App authentication."""
    secret = BOT_TOKEN or "agentstack-default-secret"
    return hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()[:32]


def verify_web_token(token: str) -> str | None:
    """Verify a web token and return the user_id, or None if invalid.

    Since HMAC is one-way, we check against all known users.
    For small user counts this is fine. For scale, use JWT instead.
    """
    if not token:
        return None
    for user in get_all_users():
        if make_web_token(user["user_id"]) == token:
            return user["user_id"]
    return None
