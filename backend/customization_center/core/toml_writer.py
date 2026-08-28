from __future__ import annotations

import math
import re
import tomllib
from typing import Any

_BARE = re.compile(r"^[A-Za-z0-9_-]+$")


def _escape_basic(value: str) -> str:
    named = {8: "\\b", 9: "\\t", 10: "\\n", 12: "\\f", 13: "\\r"}
    output: list[str] = []
    for char in value:
        code = ord(char)
        if char == "\\":
            output.append("\\\\")
        elif char == '"':
            output.append('\\"')
        elif code in named:
            output.append(named[code])
        elif code <= 0x1F or code == 0x7F:
            output.append(f"\\u{code:04X}")
        else:
            output.append(char)
    return "".join(output)


def _key(value: str) -> str:
    if _BARE.match(value):
        return value
    return '"' + _escape_basic(value) + '"'


def _scalar(value: Any) -> str:
    if isinstance(value, str):
        return '"' + _escape_basic(value) + '"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not supported")
        return repr(value)
    if isinstance(value, (list, tuple)):
        if any(isinstance(item, (dict, list, tuple)) for item in value):
            raise TypeError("only arrays of scalars are supported")
        return "[" + ", ".join(_scalar(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value: {type(value).__name__}")


def dumps(table: dict[str, Any]) -> str:
    if not isinstance(table, dict):
        raise TypeError("TOML root must be a dict")
    lines: list[str] = []

    def write(current: dict[str, Any], path: tuple[str, ...]) -> None:
        if path:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append("[" + ".".join(_key(part) for part in path) + "]")
        for key, value in current.items():
            if not isinstance(key, str):
                raise TypeError("TOML keys must be strings")
            if not isinstance(value, dict):
                lines.append(f"{_key(key)} = {_scalar(value)}")
        for key, value in current.items():
            if isinstance(value, dict):
                write(value, path + (key,))

    write(table, ())
    return "\n".join(lines) + "\n"


def reparse(text: str, expected: dict[str, Any] | None = None) -> dict[str, Any]:
    value = tomllib.loads(text)
    if expected is not None and value != expected:
        raise AssertionError(f"TOML round trip changed data: {value!r} != {expected!r}")
    return value
