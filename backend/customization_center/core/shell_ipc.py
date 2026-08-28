from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .commands import CommandRunner
from .errors import CcError


@dataclass(frozen=True)
class IpcResult:
    body: str
    parsed: Any
    ok: bool


_METHOD_EXPECT: dict[str, tuple[str, ...] | None] = {
    "ping": ("ok",), "reloadConfig": ("ok",), "enablePlugin": ("ok",),
    "setPluginEnabled": ("ok",), "putBarWidget": ("ok",), "moveBarWidget": ("ok",),
    "setBarWidget": ("ok",), "applyTheme": ("ok",), "rescanPlugins": ("",),
    "listPlugins": None, "listShellConfig": None, "summon": ("ok",), "hide": ("",),
}


class ShellIpc:
    def __init__(self, commands: CommandRunner) -> None:
        self.commands = commands
        if hasattr(commands, "allow_readonly"):
            for method in ("ping", "listPlugins", "listShellConfig"):
                commands.allow_readonly(("omarchy-shell", "shell", method))

    def call(self, method: str, *args: Any, expect: tuple[str, ...] = ("ok",),
             expect_json: bool = False, timeout_s: float = 5) -> IpcResult:
        if method not in _METHOD_EXPECT:
            raise CcError("unsupported_config", f"Shell IPC method is not allowlisted: {method}")
        serialized = [json.dumps(arg, separators=(",", ":"), ensure_ascii=False)
                      if isinstance(arg, (dict, list, tuple, bool)) or arg is None else str(arg) for arg in args]
        result = self.commands.run(["omarchy-shell", "shell", method, *serialized], timeout_s=timeout_s,
                                   env_extra={"OMARCHY_SHELL_IPC_TIMEOUT": f"{timeout_s:g}s"})
        combined = (result.stderr + "\n" + result.stdout).strip()
        lowered = combined.lower()
        if result.timed_out:
            raise CcError("timeout", f"Shell IPC {method} exceeded {timeout_s:g} seconds")
        if result.exit_code != 0:
            if "function not found." in lowered or "target not found." in lowered:
                raise CcError("unsupported_config", combined or "Shell IPC target is unsupported")
            if any(value in lowered for value in ("not running", "not responding", "not ready")):
                raise CcError("runtime_unavailable", combined or "Omarchy shell is unavailable")
            raise CcError("ipc_rejected", combined or f"omarchy-shell exited {result.exit_code}")
        body = result.stdout.rstrip("\r\n")
        parsed = None
        wants_json = expect_json or _METHOD_EXPECT[method] is None
        if wants_json:
            try:
                parsed = json.loads(body)
            except (json.JSONDecodeError, TypeError) as error:
                raise CcError("malformed_output", f"Invalid JSON from {method}: {body[:512]}") from error
            expected_type = list if method == "listPlugins" else dict if method == "listShellConfig" else None
            if expected_type is not None and not isinstance(parsed, expected_type):
                raise CcError("malformed_output", f"Unexpected JSON shape from {method}")
        else:
            allowed = _METHOD_EXPECT[method] if expect == ("ok",) else tuple(expect)
            if body not in (allowed or ()):
                raise CcError("ipc_rejected", f"Shell IPC {method} rejected: {body}", {"body": body})
        return IpcResult(body, parsed, True)

    def ping(self) -> bool:
        return self.call("ping").ok

    def list_plugins(self) -> list[dict[str, Any]]:
        value = self.call("listPlugins", expect_json=True).parsed
        if not isinstance(value, list):
            raise CcError("malformed_output", "listPlugins did not return an array")
        return value

    def list_shell_config(self) -> dict[str, Any]:
        value = self.call("listShellConfig", expect_json=True).parsed
        if not isinstance(value, dict):
            raise CcError("malformed_output", "listShellConfig did not return an object")
        return value
