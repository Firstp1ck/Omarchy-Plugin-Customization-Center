from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

from .commands import CommandRunner
from .errors import CcError


class Hyprctl:
    def __init__(self, commands: CommandRunner) -> None:
        self.commands = commands

    def json(self, *args: str) -> Any:
        result = self.commands.run(["hyprctl", "-j", *args], timeout_s=5)
        if result.timed_out or result.exit_code != 0:
            raise CcError("runtime_unavailable", result.stderr.strip() or "hyprctl failed")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise CcError("malformed_output", "hyprctl returned invalid JSON") from error

    def plain(self, *args: str) -> str:
        result = self.commands.run(["hyprctl", *args], timeout_s=5)
        if result.timed_out or result.exit_code != 0:
            raise CcError("runtime_unavailable", result.stderr.strip() or "hyprctl failed")
        return result.stdout

    def reload_guard_paused(self) -> bool:
        if self.commands.which("omarchy-hyprland-reload-guard") is None:
            return False
        result = self.commands.run(["omarchy-hyprland-reload-guard", "paused"], timeout_s=3)
        return result.exit_code == 0

    def reload(self, config_only: bool = False) -> str:
        if self.reload_guard_paused():
            raise CcError("runtime_unavailable", "Hyprland reload guard is paused")
        return self.plain("reload", *(("config-only",) if config_only else ()))

    def configerrors(self) -> Any:
        return self.json("configerrors")

    @staticmethod
    def configerrors_diff(baseline: Any, after: Any) -> list[Any]:
        before = {json.dumps(item, sort_keys=True) for item in (baseline or [])}
        return [item for item in (after or []) if json.dumps(item, sort_keys=True) not in before]
