from __future__ import annotations

from typing import Any

from customization_center.core import CcError, remove_file, write_bytes_atomic


def capability(ctx: Any) -> dict[str, Any]:
    available = ctx.commands.which("luac") is not None
    return {"available": available, "argv": ["luac", "-p"] if available else [], "version": "",
            "reason": "" if available else "luac_missing"}


def check_candidate(ctx: Any, candidate: bytes) -> tuple[bool, str]:
    if ctx.commands.which("luac") is None:
        return True, "keybindings_no_lua_check"
    temporary = ctx.paths.private_tmpfile(".lua")
    try:
        write_bytes_atomic(temporary, candidate, 0o600)
        result = ctx.commands.run(["luac", "-p", "--", str(temporary)], timeout_s=5,
                                  env_extra={"LC_ALL": "C"}, capture_limit=65536)
        if result.timed_out:
            raise CcError("timeout", "luac syntax check timed out")
        if result.exit_code != 0:
            message = (result.stderr or result.stdout or "Lua syntax check failed").replace(str(temporary), "bindings.lua").strip()
            raise CcError("keybindings_lua_syntax", message)
        return True, ""
    finally:
        remove_file(temporary)
