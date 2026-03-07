"""Single-user auth for AgentStack.

1 computer, 1 bot, 1 owner. No database, no registration.
Only the OWNER_ID can use the bot or connect to terminals.
"""

import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OWNER_ID = os.getenv("OWNER_ID", "")
WEB_TOKEN_TTL = int(os.getenv("WEB_TOKEN_TTL", "14400"))  # 4 hours


def is_owner(user_id) -> bool:
    return str(user_id) == OWNER_ID


def _secret() -> bytes:
    return (BOT_TOKEN or secrets.token_hex(32)).encode()


# -- Session keys --

def session_key(name: str) -> str:
    return name


def list_session_names(all_keys: list[str]) -> list[str]:
    return all_keys


# -- Web tokens (time-limited HMAC) --

def make_web_token() -> str:
    """Signed token: sig|timestamp|nonce. Only the owner gets one."""
    ts = str(int(time.time()))
    nonce = secrets.token_hex(8)
    payload = f"{OWNER_ID}|{ts}|{nonce}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:40]
    return f"{sig}|{ts}|{nonce}"


def verify_init_data(init_data: str) -> bool:
    """Verify Telegram WebApp initData. Returns True only if signature is valid and sender is owner.

    Telegram signs initData with HMAC-SHA256 using a secret derived from the bot token.
    This ensures the data genuinely came from Telegram and cannot be forged in a browser.
    """
    if not init_data or not BOT_TOKEN or not OWNER_ID:
        return False
    try:
        params = {}
        for part in init_data.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[urllib.parse.unquote(k)] = urllib.parse.unquote_plus(v)

        received_hash = params.pop("hash", None)
        if not received_hash:
            return False

        # Telegram spec: data_check_string = sorted key=value pairs joined by \n
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))

        # secret_key = HMAC-SHA256(key="WebAppData", msg=bot_token)
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(received_hash, expected_hash):
            return False

        # Verify the user is the owner
        user = json.loads(params.get("user", "{}"))
        if str(user.get("id", "")) != OWNER_ID:
            return False

        # Reject stale initData (24h max, per Telegram recommendation)
        auth_date = int(params.get("auth_date", 0))
        if time.time() - auth_date > 86400:
            return False

        return True
    except Exception:
        return False


def verify_web_token(token: str) -> bool:
    """Returns True if the token is valid and not expired."""
    if not token or not OWNER_ID:
        return False

    parts = token.split("|")
    if len(parts) != 3:
        return False

    sig, ts_str, nonce = parts

    try:
        ts = int(ts_str)
    except ValueError:
        return False

    if time.time() - ts > WEB_TOKEN_TTL:
        return False

    payload = f"{OWNER_ID}|{ts_str}|{nonce}"
    expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:40]
    return hmac.compare_digest(sig, expected)
