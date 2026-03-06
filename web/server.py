"""WebSocket terminal server for AgentStack.

Single-owner: only authenticated owner can connect.
Opens real PTY sessions — bash, claude, anything.
"""

import asyncio
import json
import logging
import os
import platform
import pty
import re
import select
import signal
import struct
import sys
import fcntl
import termios
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import users

log = logging.getLogger("agentstack.web")

AGENTS_FILE = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "agents.json"
START_TIME = time.time()

# Cached agents.json with mtime check
_agents_cache = {}
_agents_mtime = 0.0


def load_agents() -> dict:
    global _agents_cache, _agents_mtime
    try:
        mt = AGENTS_FILE.stat().st_mtime
        if mt != _agents_mtime:
            with open(AGENTS_FILE) as f:
                _agents_cache = json.load(f).get("agents", {})
            _agents_mtime = mt
    except FileNotFoundError:
        _agents_cache = {}
    return _agents_cache


# Env vars to strip from spawned PTY sessions
_STRIP_ENV = ("CLAUDECODE", "CLAUDE_CODE", "CLAUDE_SESSION")

# Session name sanitizer
_NAME_RE = re.compile(r'[^a-z0-9_-]')


def _sanitize_name(name: str) -> str:
    return _NAME_RE.sub('', name.lower().strip())[:32]


app = FastAPI(title="AgentStack Terminal")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")


class PtySession:
    def __init__(self, name: str, cmd: list[str], cwd: str = None, env_extra: dict = None):
        self.name = name
        self.pid = -1
        self.fd = -1
        self._alive = False

        cwd = cwd or os.path.expanduser("~")
        os.makedirs(cwd, exist_ok=True)

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        for var in _STRIP_ENV:
            env.pop(var, None)
        if env_extra:
            env.update(env_extra)

        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.chdir(cwd)
            os.execvpe(cmd[0], cmd, env)
        else:
            self._alive = True
            flags = fcntl.fcntl(self.fd, fcntl.F_GETFL)
            fcntl.fcntl(self.fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            log.info("PTY '%s' started (pid=%d)", name, self.pid)

    def resize(self, cols: int, rows: int):
        if self.fd >= 0:
            try:
                fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
            except OSError:
                pass

    def write(self, data: bytes):
        if self.fd >= 0 and self._alive:
            try:
                os.write(self.fd, data)
            except OSError:
                self._alive = False

    def is_alive(self) -> bool:
        if not self._alive:
            return False
        try:
            pid, _ = os.waitpid(self.pid, os.WNOHANG)
            if pid != 0:
                self._alive = False
        except ChildProcessError:
            self._alive = False
        return self._alive

    def kill(self):
        self._alive = False
        if self.fd >= 0:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = -1
        if self.pid > 0:
            try:
                os.kill(self.pid, signal.SIGTERM)
                os.waitpid(self.pid, os.WNOHANG)
            except (OSError, ChildProcessError):
                pass
        log.info("PTY '%s' killed", self.name)


class SessionPool:
    def __init__(self):
        self.sessions: dict[str, PtySession] = {}

    def spawn(self, key: str, cmd: list[str], cwd: str = None, env_extra: dict = None) -> PtySession:
        if key in self.sessions:
            self.sessions[key].kill()
        session = PtySession(key, cmd, cwd, env_extra)
        self.sessions[key] = session
        return session

    def get(self, key: str) -> PtySession | None:
        s = self.sessions.get(key)
        if s and not s.is_alive():
            del self.sessions[key]
            return None
        return s

    def kill(self, key: str) -> bool:
        s = self.sessions.pop(key, None)
        if s:
            s.kill()
            return True
        return False

    def list_names(self) -> list[str]:
        dead = [k for k, s in self.sessions.items() if not s.is_alive()]
        for k in dead:
            del self.sessions[k]
        return list(self.sessions.keys())

    def kill_all(self):
        for s in self.sessions.values():
            s.kill()
        self.sessions.clear()


pool = SessionPool()


def build_session_cmd(name: str, agents: dict) -> tuple[list[str], str]:
    cfg = agents.get(name)
    if cfg:
        cmd = ["claude"]
        if cfg.get("prompt"):
            cmd.extend(["--system-prompt", cfg["prompt"]])
        cwd = cfg.get("cwd", os.path.expanduser("~"))
    else:
        default_shell = "/bin/zsh" if platform.system() == "Darwin" else "/bin/bash"
        cmd = [os.environ.get("SHELL", default_shell)]
        cwd = os.path.expanduser("~")
    return cmd, cwd


def _blocking_read(fd: int) -> bytes:
    """Read from PTY fd with batching — collect available data up to 64KB."""
    if fd < 0:
        return b""
    try:
        r, _, _ = select.select([fd], [], [], 0.1)
        if not r:
            return b""
        chunks = []
        total = 0
        while total < 65536:
            try:
                chunk = os.read(fd, 65536 - total)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                # Check if more data is immediately available
                r, _, _ = select.select([fd], [], [], 0)
                if not r:
                    break
            except (OSError, BlockingIOError):
                break
        return b"".join(chunks)
    except (OSError, ValueError):
        pass
    return b""


# ── Lifecycle events ──────────────────────────────────

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_reap_loop())


@app.on_event("shutdown")
async def shutdown_event():
    log.info("Shutting down — killing all PTY sessions")
    pool.kill_all()


async def _reap_loop():
    """Periodically reap dead sessions to avoid zombie processes."""
    while True:
        pool.list_names()
        await asyncio.sleep(30)


# ── Routes ────────────────────────────────────────────

@app.get("/")
async def index():
    return RedirectResponse("/static/terminal.html")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "sessions": len(pool.list_names()),
        "uptime": round(time.time() - START_TIME),
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # First message must be auth
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        msg = json.loads(raw)
        if msg.get("type") != "auth" or not users.verify_web_token(msg.get("token", "")):
            await websocket.close(code=4001, reason="Unauthorized")
            return
    except (asyncio.TimeoutError, Exception):
        await websocket.close(code=4001, reason="Auth timeout")
        return

    agents = load_agents()
    attached_session: str | None = None
    reader_task: asyncio.Task | None = None

    async def read_pty(session_key: str):
        loop = asyncio.get_event_loop()
        while True:
            session = pool.get(session_key)
            if not session:
                try:
                    await websocket.send_json({
                        "type": "killed",
                        "session": session_key,
                        "sessions": pool.list_names(),
                    })
                except Exception:
                    pass
                break
            try:
                data = await loop.run_in_executor(None, _blocking_read, session.fd)
                if data:
                    await websocket.send_json({
                        "type": "output",
                        "session": session_key,
                        "data": data.decode("utf-8", errors="replace"),
                    })
            except Exception:
                break

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "list_sessions":
                await websocket.send_json({"type": "sessions", "sessions": pool.list_names()})

            elif msg_type == "list_agents":
                agents = load_agents()
                await websocket.send_json({
                    "type": "agents",
                    "agents": {n: {"description": c.get("description", "")} for n, c in agents.items()},
                })

            elif msg_type == "spawn":
                name = _sanitize_name(msg.get("session", ""))
                if not name:
                    await websocket.send_json({"type": "error", "message": "No session name"})
                    continue

                agents = load_agents()
                cmd, cwd = build_session_cmd(name, agents)

                try:
                    pool.spawn(name, cmd, cwd)
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
                    continue

                attached_session = name
                if reader_task:
                    reader_task.cancel()
                reader_task = asyncio.create_task(read_pty(name))

                await websocket.send_json({
                    "type": "spawned",
                    "session": name,
                    "sessions": pool.list_names(),
                })

            elif msg_type == "attach":
                name = msg.get("session", "")
                if not pool.get(name):
                    await websocket.send_json({"type": "error", "message": f"Session '{name}' not found"})
                    continue
                attached_session = name
                if reader_task:
                    reader_task.cancel()
                reader_task = asyncio.create_task(read_pty(name))

            elif msg_type == "input":
                name = msg.get("session", "") or attached_session
                session = pool.get(name) if name else None
                if session:
                    session.write(msg.get("data", "").encode("utf-8"))

            elif msg_type == "resize":
                name = msg.get("session", "") or attached_session
                session = pool.get(name) if name else None
                if session:
                    session.resize(msg.get("cols", 80), msg.get("rows", 24))

            elif msg_type == "kill":
                name = msg.get("session", "")
                pool.kill(name)
                if attached_session == name:
                    attached_session = None
                    if reader_task:
                        reader_task.cancel()
                        reader_task = None
                await websocket.send_json({
                    "type": "killed",
                    "session": name,
                    "sessions": pool.list_names(),
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error("WebSocket error: %s", e)
    finally:
        if reader_task:
            reader_task.cancel()


def main():
    import uvicorn
    host = os.getenv("AGENTSTACK_HOST", "0.0.0.0")
    port = int(os.getenv("AGENTSTACK_PORT", "8765"))

    def _handle_signal(sig, frame):
        pool.kill_all()
        sys.exit(0)
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    print("=" * 40)
    print("  AgentStack Terminal Server")
    print("=" * 40)
    print(f"  http://{host}:{port}")
    print(f"  Owner: {users.OWNER_ID}")
    print()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
