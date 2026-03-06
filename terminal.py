"""Tmux-based multi-session terminal manager.

Manages multiple named Claude Code (or any CLI) sessions via tmux.
Each agent gets its own tmux session, visible on screen and controllable from Telegram.
"""

import logging
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Callable, Optional

log = logging.getLogger(__name__)

TMUX_PREFIX = "agent-"

# Telegram shorthand -> tmux send-keys
KEY_MAP: dict[str, list[str]] = {
    "/up": ["Up"], "/down": ["Down"], "/right": ["Right"], "/left": ["Left"],
    "/cc": ["C-c"], "/cd": ["C-d"], "/cz": ["C-z"], "/cl": ["C-l"],
    "/ca": ["C-a"], "/ce": ["C-e"], "/cu": ["C-u"], "/cw": ["C-w"],
    "/cr": ["C-r"],
    "/tab": ["Tab"], "/esc": ["Escape"], "/enter": ["Enter"],
    "/space": ["Space"], "/bs": ["BSpace"], "/del": ["DC"],
    "/home": ["Home"], "/end": ["End"],
    "/pgup": ["PageUp"], "/pgdn": ["PageDown"],
    "/y": ["y", "Enter"], "/n": ["n", "Enter"],
    "/1": ["1"], "/2": ["2"], "/3": ["3"], "/4": ["4"], "/5": ["5"],
}

_ANSI_RE = re.compile(
    r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[()][AB012]|[ -/]*[@-~])"
)
_CTRL_RE = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")


def strip_ansi(text: str) -> str:
    return _CTRL_RE.sub("", _ANSI_RE.sub("", text))


def _detect_terminal() -> list[str]:
    for cmd, binary in [
        (["kitty", "--title"], "kitty"),
        (["gnome-terminal", "--title"], "gnome-terminal"),
        (["alacritty", "--title"], "alacritty"),
        (["xfce4-terminal", "--title"], "xfce4-terminal"),
        (["konsole", "--title"], "konsole"),
        (["xterm", "-title"], "xterm"),
    ]:
        if shutil.which(binary):
            return cmd
    return ["xterm", "-title"]


class TmuxSession:
    """A single tmux-backed terminal session."""

    def __init__(self, name: str):
        self.name = name
        self.tmux_name = f"{TMUX_PREFIX}{name}"
        self._alive = False
        self._last_capture = ""
        self._output_buf: list[str] = []
        self._buf_lock = threading.Lock()
        self._reader: Optional[threading.Thread] = None
        self._window_proc: Optional[subprocess.Popen] = None

    def spawn(self, cmd: list[str], cwd: str = None, open_window: bool = True):
        cwd = cwd or os.path.expanduser("~")
        shell_cmd = " ".join(cmd)

        # Kill stale session
        subprocess.run(["tmux", "kill-session", "-t", self.tmux_name], capture_output=True)

        # Clean env for nested Claude Code
        clean_env = os.environ.copy()
        for var in ("CLAUDECODE", "CLAUDE_CODE", "CLAUDE_SESSION"):
            clean_env.pop(var, None)

        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", self.tmux_name, "-x", "120", "-y", "30", shell_cmd],
            cwd=cwd, env=clean_env, capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"tmux new-session failed: {result.stderr}")

        self._alive = True
        log.info("Session '%s' created: %s", self.tmux_name, shell_cmd)

        if open_window:
            self._open_window()

        self._reader = threading.Thread(target=self._capture_loop, daemon=True, name=f"reader-{self.name}")
        self._reader.start()

    def _open_window(self):
        term_cmd = _detect_terminal()
        title = f"Agent: {self.name}"
        full_cmd = term_cmd + [title, "-e", "tmux", "attach-session", "-t", self.tmux_name]
        try:
            env = os.environ.copy()
            if "DISPLAY" not in env:
                env["DISPLAY"] = ":0"
            self._window_proc = subprocess.Popen(
                full_cmd, env=env, start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            log.warning("Could not open terminal window: %s", e)

    def _capture_loop(self):
        while self._alive:
            try:
                check = subprocess.run(["tmux", "has-session", "-t", self.tmux_name], capture_output=True)
                if check.returncode != 0:
                    self._alive = False
                    with self._buf_lock:
                        self._output_buf.append("\n[Process exited]")
                    break

                result = subprocess.run(
                    ["tmux", "capture-pane", "-t", self.tmux_name, "-p", "-J", "-S", "-50"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    current = result.stdout.rstrip()
                    if current and current != self._last_capture:
                        new_text = self._diff_output(self._last_capture, current)
                        self._last_capture = current
                        if new_text.strip():
                            cleaned = strip_ansi(new_text)
                            if cleaned.strip():
                                with self._buf_lock:
                                    self._output_buf.append(cleaned)
            except subprocess.TimeoutExpired:
                pass
            except Exception as e:
                log.debug("Capture error: %s", e)
            time.sleep(1.5)
        self._alive = False

    def _diff_output(self, old: str, new: str) -> str:
        old_lines = old.splitlines()
        new_lines = new.splitlines()
        if not old_lines:
            return new
        overlap_size = min(5, len(old_lines))
        tail = old_lines[-overlap_size:]
        for i in range(len(new_lines) - overlap_size + 1):
            if new_lines[i:i + overlap_size] == tail:
                diff = new_lines[i + overlap_size:]
                return "\n".join(diff) if diff else ""
        return new

    def write(self, text: str):
        if not self._alive:
            return
        key = text.strip().lower()
        if key in KEY_MAP:
            for k in KEY_MAP[key]:
                subprocess.run(["tmux", "send-keys", "-t", self.tmux_name, k], capture_output=True, timeout=5)
        else:
            subprocess.run(["tmux", "send-keys", "-t", self.tmux_name, "-l", text], capture_output=True, timeout=5)
            subprocess.run(["tmux", "send-keys", "-t", self.tmux_name, "Enter"], capture_output=True, timeout=5)

    def read(self) -> str:
        with self._buf_lock:
            if not self._output_buf:
                return ""
            text = "\n".join(self._output_buf)
            self._output_buf.clear()
        return text

    def is_alive(self) -> bool:
        if not self._alive:
            return False
        check = subprocess.run(["tmux", "has-session", "-t", self.tmux_name], capture_output=True)
        if check.returncode != 0:
            self._alive = False
        return self._alive

    def kill(self):
        self._alive = False
        subprocess.run(["tmux", "kill-session", "-t", self.tmux_name], capture_output=True)
        if self._window_proc:
            try:
                self._window_proc.terminate()
            except Exception:
                pass
            self._window_proc = None
        log.info("Session '%s' killed", self.tmux_name)


class SessionManager:
    """Manages multiple named terminal sessions."""

    def __init__(self):
        self._sessions: dict[str, TmuxSession] = {}
        self._lock = threading.Lock()
        self._streamers: dict[str, threading.Thread] = {}

    def create(self, name: str, cmd: list[str], cwd: str = None,
               on_output: Callable[[str, str], None] = None) -> TmuxSession:
        with self._lock:
            if name in self._sessions:
                self._sessions[name].kill()
            session = TmuxSession(name)
            session.spawn(cmd, cwd=cwd)
            self._sessions[name] = session

        if on_output:
            t = threading.Thread(target=self._stream, args=(name, on_output), daemon=True)
            self._streamers[name] = t
            t.start()
        return session

    def _stream(self, name: str, on_output: Callable[[str, str], None]):
        while True:
            session = self.get(name)
            if not session:
                break
            text = session.read()
            if text:
                on_output(name, text)
            if not session.is_alive():
                remaining = session.read()
                if remaining:
                    on_output(name, remaining)
                break
            time.sleep(1.5)

    def get(self, name: str) -> Optional[TmuxSession]:
        with self._lock:
            return self._sessions.get(name)

    def has(self, name: str) -> bool:
        s = self.get(name)
        return s is not None and s.is_alive()

    def destroy(self, name: str) -> bool:
        with self._lock:
            session = self._sessions.pop(name, None)
            self._streamers.pop(name, None)
        if session:
            session.kill()
            return True
        return False

    def list_active(self) -> list[str]:
        with self._lock:
            return [n for n, s in self._sessions.items() if s.is_alive()]

    def destroy_all(self):
        with self._lock:
            for s in self._sessions.values():
                s.kill()
            self._sessions.clear()
            self._streamers.clear()
