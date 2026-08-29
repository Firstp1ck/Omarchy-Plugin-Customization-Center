from __future__ import annotations

import re
from typing import Any

_KEYCODE = re.compile(r"<([^>]+)>\s*=\s*(\d+)\s*;")
_SYMBOL = re.compile(r"key\s+<([^>]+)>\s*\{\s*\[\s*([^,\]\s]+)")
_HOW = re.compile(r"keysym:\s+([^\s]+)\s+\((0x[0-9a-fA-F]+)\)")


def parse_compiled_keymap(text: str) -> dict[int, str]:
    names = {name: int(number) for name, number in _KEYCODE.findall(text)}
    symbols = {name: symbol for name, symbol in _SYMBOL.findall(text)}
    return {number: symbols[name] for name, number in names.items() if name in symbols and symbols[name] != "NoSymbol"}


def parse_how_to_type(text: str) -> dict[str, Any] | None:
    match = _HOW.search(text)
    return {"canonicalName": match.group(1), "keysym": int(match.group(2), 16)} if match else None


def compile_argv(layout: str, variant: str = "", options: str = "") -> list[str]:
    argv = ["xkbcli", "compile-keymap", "--layout", layout or "us"]
    if variant:
        argv.extend(["--variant", variant])
    if options:
        argv.extend(["--options", options])
    return argv


def keymap_from_context(ctx: Any, keyboard: dict[str, Any] | None) -> dict[int, str]:
    if not keyboard or ctx.commands.which("xkbcli") is None:
        return {}
    argv = compile_argv(str(keyboard.get("layout", "us")), str(keyboard.get("variant", "")), str(keyboard.get("options", "")))
    result = ctx.commands.run(argv, timeout_s=5, env_extra={"LC_ALL": "C"}, stdin="", capture_limit=2 * 1024 * 1024)
    if result.exit_code != 0 or result.timed_out or result.truncated:
        return {}
    return parse_compiled_keymap(result.stdout)
