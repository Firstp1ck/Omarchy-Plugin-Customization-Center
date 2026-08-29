from __future__ import annotations

from typing import Any

GUARD_READERS = (
    "omarchy-channel-current", "omarchy-default-agent", "omarchy-default-browser",
    "omarchy-default-editor", "omarchy-default-terminal", "omarchy-dns",
)


def substitute_readers(expression: str) -> str:
    result = expression
    for index, reader in enumerate(GUARD_READERS):
        result = result.replace(f"$({reader})", "${__omarchy_read_" + str(index) + "}")
    return result


def _content_error(text: str) -> str | None:
    if len(text.encode("utf-8")) > 4096:
        return "expression exceeds 4096 bytes"
    for character in text:
        code = ord(character)
        if code == 0 or code < 32 and character not in "\t\n":
            return "expression contains a control character"
    return None


def check(ctx: Any, expression: str, kind: str = "guard") -> dict[str, Any]:
    error = _content_error(expression)
    if error:
        return {"ok": False, "code": "menu_field_content", "message": error, "script": ""}
    if kind == "action":
        script = expression + "\n"
        code = "menu_action_syntax_failed"
    else:
        script = "if { " + substitute_readers(expression) + "; } >/dev/null 2>&1; then :; else :; fi\n"
        code = "menu_guard_syntax_failed"
    result = ctx.commands.run(["bash", "--noprofile", "--norc", "-n"], stdin=script, timeout_s=5,
                              capture_limit=4096,
                              env_extra={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "BASH_ENV": None})
    if result.exit_code == 127:
        return {"ok": False, "code": "runtime_unavailable", "message": "bash_missing", "script": script}
    if result.exit_code == 0 and not result.timed_out:
        return {"ok": True, "code": "", "message": "", "script": script}
    line = (result.stderr.strip().splitlines() or ["bash syntax check failed"])[0]
    if ": line " in line and ":" in line:
        parts = line.split(":", 2)
        line = parts[-1].strip() if len(parts) == 3 else line
    return {"ok": False, "code": code, "message": line, "script": script}
