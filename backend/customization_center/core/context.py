from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .capabilities import standard_capabilities
from .commands import CommandRunner
from .hyprctl import Hyprctl
from .journal import Journal, JournalReader
from .paths import Paths
from .shell_ipc import ShellIpc
from .types import Context


class Clock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def now_iso(self) -> str:
        return self.now().isoformat().replace("+00:00", "Z")

    def monotonic(self) -> float:
        return time.monotonic()


class Logger:
    def __init__(self, module_id: str) -> None:
        self.module_id = module_id

    def _write(self, level: str, message: str, **data: Any) -> None:
        record = {"level": level, "module": self.module_id, "message": message, **data}
        print(json.dumps(record, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)

    def info(self, message: str, **data: Any) -> None:
        self._write("info", message, **data)

    def warning(self, message: str, **data: Any) -> None:
        self._write("warning", message, **data)

    def error(self, message: str, **data: Any) -> None:
        self._write("error", message, **data)


class RuntimeContext:
    """Context implementation with the pure helpers used by modules."""

    def __init__(self, value: Context, builder: Any) -> None:
        self.__dict__.update(value.__dict__)
        self._builder = builder

    def revision_of(self, data: Any) -> str:
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                             allow_nan=False).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def ctx_for(self, module_id: str, mode: str | None = None) -> "RuntimeContext":
        return self._builder(module_id, mode or self.mode)


def build_context(module_id: str, mode: str = "read", *, paths: Paths | None = None,
                  registry: Any = None, plugin_dir: str | Path | None = None,
                  environ: dict[str, str] | None = None, cache: dict[str, Any] | None = None) -> RuntimeContext:
    runtime_paths = paths or Paths.from_env(environ)
    commands = CommandRunner(mode, environ)
    shell = ShellIpc(commands)
    hyprctl = Hyprctl(commands)
    clock = Clock()
    shared_cache = {} if cache is None else cache
    if registry is None:
        if plugin_dir is None:
            plugin_dir = Path(__file__).resolve().parents[3]
        from .registry import load_registry
        registry = load_registry(plugin_dir, paths=runtime_paths).view

    def builder(other_id: str, other_mode: str) -> RuntimeContext:
        return build_context(other_id, other_mode, paths=runtime_paths, registry=registry,
                             plugin_dir=plugin_dir, environ=environ, cache=shared_cache)

    capabilities = standard_capabilities(module_id, commands, shell, clock.now_iso())
    base = Context(runtime_paths, capabilities, commands, shared_cache, shell, hyprctl,
                   JournalReader(Journal(runtime_paths)), registry, clock, Logger(module_id), mode, module_id)
    ctx = RuntimeContext(base, builder)
    # Read-only command declarations are available before a module probes or reads status.
    for capability in capabilities.items:
        if capability.readonly_check and capability.argv_prefix:
            commands.allow_readonly(capability.argv_prefix)
    try:
        module_caps = registry.module(module_id).capabilities(ctx)
    except Exception:
        module_caps = capabilities
    ctx.capabilities = module_caps
    for capability in module_caps.items:
        if capability.readonly_check and capability.argv_prefix:
            commands.allow_readonly(capability.argv_prefix)
    return ctx
