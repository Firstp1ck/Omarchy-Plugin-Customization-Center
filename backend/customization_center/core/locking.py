from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any

from .atomic import mkdir_durable
from .errors import CcError


class Locked(CcError):
    def __init__(self, holder: dict[str, Any] | None = None) -> None:
        data = holder or {}
        label = data.get("transactionId") or data.get("pid") or "unknown"
        super().__init__("locked", f"Another apply holds the lock ({label})", data)


class ApplyLock:
    def __init__(self, runtime: str | Path | Any, transaction_id: str = "", module: str = "") -> None:
        base = Path(runtime.runtime if hasattr(runtime, "runtime") else runtime)
        self.path = base / "apply.lock"
        self.transaction_id = transaction_id
        self.module = module
        self._file: Any = None

    @staticmethod
    def _holder(handle: Any) -> dict[str, Any]:
        try:
            handle.seek(0)
            value = json.load(handle)
            return value if isinstance(value, dict) else {}
        except (ValueError, OSError):
            return {}

    def acquire(self) -> "ApplyLock":
        mkdir_durable(self.path.parent, 0o700)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            holder = self._holder(handle)
            handle.close()
            raise Locked(holder)
        holder = {"transactionId": self.transaction_id, "module": self.module, "pid": os.getpid()}
        handle.seek(0)
        handle.truncate()
        json.dump(holder, handle, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
        self._file = handle
        return self

    def release(self) -> None:
        if self._file is not None:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            self._file.close()
            self._file = None

    def __enter__(self) -> "ApplyLock":
        return self.acquire()

    def __exit__(self, *_: Any) -> None:
        self.release()


def lock(runtime: str | Path | Any, transaction_id: str = "", module: str = "") -> ApplyLock:
    return ApplyLock(runtime, transaction_id, module)


def flock(runtime: str | Path | Any, transaction_id: str = "", module: str = "") -> ApplyLock:
    return lock(runtime, transaction_id, module)
