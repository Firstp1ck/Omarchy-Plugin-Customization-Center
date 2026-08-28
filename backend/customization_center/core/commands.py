from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .errors import CcError

_BASE_ENV = {"PATH", "HOME", "OMARCHY_PATH", "WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE", "DISPLAY",
             "LANG", "LC_ALL", "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR"}


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int
    truncated: bool


class CommandRunner:
    def __init__(self, mode: str = "apply", environ: Mapping[str, str] | None = None) -> None:
        self.mode = mode
        self.environ = dict(os.environ if environ is None else environ)
        self._readonly: set[tuple[str, ...]] = set()

    def allow_readonly(self, argv_prefix: Sequence[str]) -> None:
        prefix = self._validate_argv(argv_prefix)
        if not prefix:
            raise ValueError("argv prefix cannot be empty")
        self._readonly.add(prefix)

    @staticmethod
    def _validate_argv(argv: Sequence[str]) -> tuple[str, ...]:
        if isinstance(argv, (str, bytes)) or not isinstance(argv, (list, tuple)):
            raise TypeError("argv must be a list or tuple of strings")
        if not argv or any(not isinstance(item, str) for item in argv):
            raise TypeError("argv must be a non-empty list or tuple of strings")
        return tuple(argv)

    def _check_mode(self, argv: tuple[str, ...]) -> None:
        if self.mode == "plan":
            raise CcError("permission_required", "Commands are disabled while planning")
        if self.mode in {"validate", "query", "read"} and not any(argv[:len(p)] == p for p in self._readonly):
            raise CcError("permission_required", f"Command is not registered read-only: {argv[0]}")

    def _env(self, extra: Mapping[str, str | None] | None) -> dict[str, str]:
        env = {key: value for key, value in self.environ.items() if key in _BASE_ENV or key.startswith("XDG_")}
        for key, value in (extra or {}).items():
            if not isinstance(key, str) or (value is not None and not isinstance(value, str)):
                raise TypeError("env_extra must map strings to strings or None")
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return env

    def run(self, argv: Sequence[str], timeout_s: float, env_extra: Mapping[str, str | None] | None = None,
            stdin: str | bytes | None = None, capture_limit: int = 65536,
            cwd: str | Path | None = None) -> CommandResult:
        args = self._validate_argv(argv)
        self._check_mode(args)
        if timeout_s <= 0 or capture_limit < 0:
            raise ValueError("timeout and capture limit must be positive")
        input_bytes = stdin.encode() if isinstance(stdin, str) else stdin
        started = time.monotonic()
        process = subprocess.Popen(args, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self._env(env_extra),
                                   cwd=cwd, start_new_session=True)
        captured = {"stdout": bytearray(), "stderr": bytearray()}
        truncated = {"stdout": False, "stderr": False}

        def drain(name: str, stream: object) -> None:
            while True:
                chunk = stream.read(65536)  # type: ignore[attr-defined]
                if not chunk:
                    break
                remaining = capture_limit - len(captured[name])
                if remaining > 0:
                    captured[name].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    truncated[name] = True
            stream.close()  # type: ignore[attr-defined]

        readers = [threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
                   threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True)]
        for reader in readers:
            reader.start()

        def feed_stdin() -> None:
            if process.stdin is None:
                return
            try:
                process.stdin.write(input_bytes or b"")
                process.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            finally:
                process.stdin.close()

        writer = threading.Thread(target=feed_stdin, daemon=True) if stdin is not None else None
        if writer is not None:
            writer.start()
        timed_out = False
        try:
            process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        if writer is not None:
            writer.join(timeout=1)
        for reader in readers:
            reader.join()
        elapsed = int((time.monotonic() - started) * 1000)
        stdout = bytes(captured["stdout"])
        stderr = bytes(captured["stderr"])
        was_truncated = truncated["stdout"] or truncated["stderr"]
        return CommandResult(args, int(process.returncode), stdout.decode("utf-8", "replace"),
                             stderr.decode("utf-8", "replace"), timed_out, elapsed, was_truncated)

    def which(self, name: str) -> str | None:
        if not isinstance(name, str) or "/" in name:
            return None
        return shutil.which(name, path=self._env(None).get("PATH"))


_SECRET_ASSIGNMENT = re.compile(
    r'''(?ix)(?P<prefix>["']?\b(?:token|password|secret)\b["']?(?:\s*[:=]\s*|\s+))'''
    r'''(?P<value>"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;]+)''')
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_URL_USERINFO = re.compile(r"(?P<scheme>\b[a-z][a-z0-9+.-]*://)[^/@\s]+@", re.I)


def redact(text: str) -> str:
    value = _SECRET_ASSIGNMENT.sub(lambda m: m.group("prefix") + "<redacted>", text)
    value = _BEARER.sub("Bearer <redacted>", value)
    return _URL_USERINFO.sub(lambda m: m.group("scheme"), value)
