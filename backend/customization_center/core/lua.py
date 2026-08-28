from __future__ import annotations

from pathlib import Path
from typing import Any


def lua_string(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("Lua strings require str")
    out: list[str] = ['"']
    for byte in value.encode("utf-8"):
        if byte == 34:
            out.append('\\"')
        elif byte == 92:
            out.append("\\\\")
        elif byte == 10:
            out.append("\\n")
        elif byte == 13:
            out.append("\\r")
        elif byte == 9:
            out.append("\\t")
        elif 32 <= byte <= 126:
            out.append(chr(byte))
        else:
            out.append(f"\\{byte:03d}")
    out.append('"')
    return "".join(out)


def luac_check(commands: Any, path: str | Path) -> Any:
    return commands.run(["luac", "-p", str(path)], timeout_s=5)
