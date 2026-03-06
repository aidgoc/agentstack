"""WebSocket terminal server for AgentStack Mini App.

Multi-user: each WebSocket connection is authenticated via token.
Sessions are namespaced per user (user_id:agent_name).
Each user's Claude Code processes run with their own API key.
"""

import asyncio
import json
import logging
import os
import pty
import select
import signal
import struct
import sys
import fcntl
import termios
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import users

log = logging.getLogger("agentstack.web")

AGENTS_FILE = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "agents.json"

app = FastAPI(title="AgentStack Terminal")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")


def load_agents() -> dict:
    if AGENTS_FILE.exists():
        with open(AGENTS_FILE) as f:
            return json.load(f).get("agents", {})
    return {}


class PtySession:
    """A PTY-backed terminal session for real-time I/O."""

    def __init__(self, name: str, cmd: list[str], cwd: str = None, env_extra: dict = None):
        self.name = name
        self.pid = -1
        self.fd = -1
        self._alive = False

        cwd = cwd or os.path.expanduser("~")
        os.makedirs(cwd, exist_ok=True)

        env = os.environ.copy()
        for var in ("CLAUDECODE", "CLAUDE_CODE", "CLAUDE_SESSION"):
            env.pop(var, None)
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
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
    """Manages PTY sessions across all users."""

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

    def list_for_user(self, user_id: str) -> list[str]:
        """Return agent names for a user."""
        dead = [k for k, s in self.sessions.items() if not s.is_alive()]
        for k in dead:
            del self.sessions[k]
        return users.user_sessions(user_id, list(self.sessions.keys()))

    def kill_all(self):
        for s in self.sessions.values():
            s.kill()
        self.sessions.clear()


pool = SessionPool()


def build_claude_cmd(name: str, agents: dict) -> tuple[list[str], str]:
    cfg = agents.get(name, {})
    cmd = ["claude"]
    if cfg.get("prompt"):
        cmd.extend(["--system-prompt", cfg["prompt"]])
    cwd = cfg.get("cwd", os.path.expanduser("~"))
    return cmd, cwd


def _blocking_read(session: PtySession) -> bytes:
    if session.fd < 0:
        return b""
    try:
        r, _, _ = select.select([session.fd], [], [], 0.1)
        if r:
            return os.read(session.fd, 65536)
    except (OSError, ValueError):
        pass
    return b""


@app.get("/")
async def index():
    return RedirectResponse("/static/terminal.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query("")):
    # Authenticate user via token
    user_id = users.verify_web_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    user = users.get_user(user_id)
    if not user or not user.get("api_key"):
        await websocket.close(code=4002, reason="No API key configured")
        return

    api_key = user["api_key"]

    await websocket.accept()
    agents = load_agents()
    attached_session: str | None = None
    reader_task: asyncio.Task | None = None

    async def read_pty(session_key: str, agent_name: str):
        loop = asyncio.get_event_loop()
        while True:
            session = pool.get(session_key)
            if not session:
                try:
                    await websocket.send_json({
                        "type": "killed",
                        "session": agent_name,
                        "sessions": pool.list_for_user(user_id),
                    })
                except Exception:
                    pass
                break
            try:
                data = await loop.run_in_executor(None, _blocking_read, session)
                if data:
                    await websocket.send_json({
                        "type": "output",
                        "session": agent_name,
                        "data": data.decode("utf-8", errors="replace"),
                    })
            except Exception:
                break
            await asyncio.sleep(0.02)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "list_sessions":
                await websocket.send_json({
                    "type": "sessions",
                    "sessions": pool.list_for_user(user_id),
                })

            elif msg_type == "list_agents":
                agents = load_agents()
                await websocket.send_json({
                    "type": "agents",
                    "agents": {n: {"description": c.get("description", "")} for n, c in agents.items()},
                })

            elif msg_type == "spawn":
                name = msg.get("session", "").lower().strip()
                if not name:
                    await websocket.send_json({"type": "error", "message": "No session name"})
                    continue

                skey = users.session_key(user_id, name)
                agents = load_agents()
                cmd, cwd = build_claude_cmd(name, agents)

                try:
                    pool.spawn(skey, cmd, cwd, env_extra={"ANTHROPIC_API_KEY": api_key})
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
                    continue

                attached_session = skey
                if reader_task:
                    reader_task.cancel()
                reader_task = asyncio.create_task(read_pty(skey, name))

                await websocket.send_json({
                    "type": "spawned",
                    "session": name,
                    "sessions": pool.list_for_user(user_id),
                })

            elif msg_type == "attach":
                name = msg.get("session", "")
                skey = users.session_key(user_id, name)
                if not pool.get(skey):
                    await websocket.send_json({"type": "error", "message": f"Session '{name}' not found"})
                    continue

                attached_session = skey
                if reader_task:
                    reader_task.cancel()
                reader_task = asyncio.create_task(read_pty(skey, name))

            elif msg_type == "input":
                name = msg.get("session", "")
                skey = users.session_key(user_id, name) if name else attached_session
                session = pool.get(skey) if skey else None
                if session:
                    session.write(msg.get("data", "").encode("utf-8"))

            elif msg_type == "resize":
                name = msg.get("session", "")
                skey = users.session_key(user_id, name) if name else attached_session
                session = pool.get(skey) if skey else None
                if session:
                    session.resize(msg.get("cols", 80), msg.get("rows", 24))

            elif msg_type == "kill":
                name = msg.get("session", "")
                skey = users.session_key(user_id, name)
                pool.kill(skey)
                if attached_session == skey:
                    attached_session = None
                    if reader_task:
                        reader_task.cancel()
                        reader_task = None
                await websocket.send_json({
                    "type": "killed",
                    "session": name,
                    "sessions": pool.list_for_user(user_id),
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
    print("=" * 50)
    print("  AgentStack Terminal Server")
    print("=" * 50)
    print(f"  http://{host}:{port}")
    print(f"  Agents: {len(load_agents())}")
    print()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
