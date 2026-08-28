from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .atomic import write_bytes_atomic
from .errors import CcError
from .types import Capability, Capabilities

STANDARD_CAPABILITIES = ("shell_ipc", "hyprctl", "luac", "bash_syntax", "timed_confirmation", "terminal_launcher")


def probe_command(commands: Any, name: str, *, readonly_check: bool = False,
                  argv_prefix: tuple[str, ...] | None = None) -> Capability:
    path = commands.which(name)
    prefix = argv_prefix or ((name,) if readonly_check else ())
    return Capability(name, path is not None, "" if path else f"{name} is not on PATH", readonly_check, tuple(prefix))


def probe_shell(shell: Any) -> Capability:
    try:
        shell.ping()
        return Capability("shell_ipc", True, "")
    except CcError as error:
        return Capability("shell_ipc", False, error.message)


class CapabilityCache:
    def __init__(self, cache_or_paths: str | Path | Any, ttl_s: float = 60) -> None:
        base = Path(cache_or_paths.cache if hasattr(cache_or_paths, "cache") else cache_or_paths)
        self.path = base / "capabilities.json"
        self.ttl_s = ttl_s

    def load(self, module_id: str, now: datetime | None = None) -> Capabilities | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        item = data.get(module_id) if isinstance(data, dict) else None
        if not isinstance(item, dict):
            return None
        try:
            probed = datetime.fromisoformat(str(item["probedAt"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            return None
        current = now or datetime.now(timezone.utc)
        if (current - probed).total_seconds() > self.ttl_s:
            return None
        return Capabilities.from_json(item)

    def save(self, capabilities: Capabilities) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        data[capabilities.module_id] = capabilities.to_json()
        write_bytes_atomic(self.path, json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + b"\n", 0o600)


def standard_capabilities(module_id: str, commands: Any, shell: Any,
                          now_iso: str | None = None) -> Capabilities:
    items = [probe_shell(shell), probe_command(commands, "hyprctl"),
             probe_command(commands, "luac", readonly_check=True, argv_prefix=("luac", "-p")),
             probe_command(commands, "bash", readonly_check=True, argv_prefix=("bash", "-n")),
             probe_command(commands, "systemd-run"),
             probe_command(commands, "omarchy-launch-floating-terminal-with-presentation")]
    renamed = [items[0], Capability("hyprctl", items[1].available, items[1].reason),
               Capability("luac", items[2].available, items[2].reason, True, items[2].argv_prefix),
               Capability("bash_syntax", items[3].available, items[3].reason, True, items[3].argv_prefix),
               Capability("timed_confirmation", items[4].available, items[4].reason),
               Capability("terminal_launcher", items[5].available, items[5].reason)]
    timestamp = now_iso or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return Capabilities(module_id, tuple(renamed), timestamp)
