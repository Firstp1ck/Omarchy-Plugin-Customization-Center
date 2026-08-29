from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from customization_center.core import CcError, managed_block

LOADER_BODY = '''-- Loads the monitor profile applied by the Customization Center. Change profiles there, not here.
do
  local config_home = os.getenv("XDG_CONFIG_HOME")
  if config_home == nil or config_home == "" then
    config_home = (os.getenv("HOME") or "") .. "/.config"
  end
  local chunk = loadfile(config_home .. "/omarchy/customization-center/generated/monitors.lua")
  if chunk then
    chunk()
  end
end'''


def loader(data: bytes) -> dict[str, Any]:
    state = managed_block.inspect(data, "MONITORS", 1)
    if state["state"] == "present":
        body = managed_block.extract(data, "MONITORS", 1)
        state["state"] = "present" if body == LOADER_BODY else "present-modified"
    return state


def _unsupported(message: str, text: str = "", position: int = 0) -> CcError:
    return CcError("unsupported_config", message, {"line": text.count("\n", 0, position) + 1})


def _mask(text: str) -> str:
    output = list(text)
    index = 0
    while index < len(text):
        if text.startswith("--", index):
            long_comment = re.match(r"--\[(=*)\[", text[index:])
            if long_comment:
                end = "]" + long_comment.group(1) + "]"
                finish = text.find(end, index + len(long_comment.group(0)))
                if finish < 0:
                    raise _unsupported("Unterminated Lua block comment", text, index)
                finish += len(end)
            else:
                finish = text.find("\n", index)
                finish = len(text) if finish < 0 else finish
            for position in range(index, finish):
                if output[position] != "\n":
                    output[position] = " "
            index = finish
            continue
        long_string = re.match(r"\[(=*)\[", text[index:])
        if long_string:
            end = "]" + long_string.group(1) + "]"
            finish = text.find(end, index + len(long_string.group(0)))
            if finish < 0:
                raise _unsupported("Unterminated Lua long-bracket string", text, index)
            finish += len(end)
            for position in range(index, finish):
                if output[position] != "\n":
                    output[position] = " "
            index = finish
            continue
        if text[index] in {'"', "'"}:
            quote = text[index]
            start = index
            output[index] = " "
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    output[index] = " "
                    if index + 1 < len(text):
                        output[index + 1] = " "
                    index += 2
                    continue
                if text[index] == quote:
                    output[index] = " "
                    index += 1
                    break
                if output[index] != "\n":
                    output[index] = " "
                index += 1
            else:
                raise _unsupported("Unterminated Lua string", text, start)
            continue
        index += 1
    return "".join(output)


def _literal_output(call: str) -> str | None:
    found = re.search(r"\boutput\s*=\s*([\"'])(.*?)\1", call, re.S)
    return found.group(2) if found else None


def scan(data: bytes, connected: list[dict[str, Any]], profile_outputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CcError("unsupported_config", "monitors.lua is not UTF-8") from error
    state = managed_block.inspect(data, "MONITORS", 1)
    if state["state"] == "present":
        begin, end = managed_block.markers("MONITORS", 1, "--")
        start, finish = text.index(begin), text.index(end) + len(end)
        text = text[:start] + "\n" * text[start:finish].count("\n") + text[finish:]
    masked = _mask(text)
    loader_call = re.search(r"\b(?:require|dofile|loadfile)\b", masked)
    if loader_call:
        raise _unsupported("monitors.lua loads code outside the managed block", text, loader_call.start())
    alias = re.search(r"\b(?:local[ \t]+)?[A-Za-z_]\w*[ \t]*=[ \t]*hl\.monitor\b", masked)
    if alias:
        raise _unsupported("Aliasing hl.monitor is unsupported", text, alias.start())
    wrapped = re.search(r"\bfunction\b[\s\S]*?hl\.monitor\s*\(", masked)
    if wrapped:
        raise _unsupported("Wrapping hl.monitor is unsupported", text, wrapped.start())

    selectors = {item["connector"] for item in connected}
    selectors.update("desc:" + item.get("description", "") for item in connected if item.get("description"))
    for item in profile_outputs or []:
        identity = item.get("identity", {})
        selectors.add(identity.get("connector", ""))
        if identity.get("description"):
            selectors.add("desc:" + identity["description"])

    catch_all = None
    conflicts: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    call_pattern = re.compile(r"hl\.monitor\s*\(\s*\{(.*?)\}\s*\)", re.S)
    spans: list[tuple[int, int]] = []
    for found in call_pattern.finditer(masked):
        spans.append(found.span())
        original = text[found.start():found.end()]
        selector = _literal_output(original)
        line = text.count("\n", 0, found.start()) + 1
        if selector is None:
            raise _unsupported("Unsupported hl.monitor output expression", text, found.start())
        row = {"line": line, "call": original.strip(), "output": selector}
        if selector == "":
            table = original[original.find("{") + 1:original.rfind("}")]
            for key, expression in re.findall(r"([A-Za-z_]\w*)\s*=\s*([^,}]+)", table):
                expression = expression.strip()
                if key not in {"output", "mode", "position", "scale"}:
                    raise _unsupported(f"Unsupported catch-all field: {key}", text, found.start())
                if key == "output":
                    continue
                if not (re.fullmatch(r"[\"'][^\"']*[\"']", expression) or re.fullmatch(r"-?\d+(?:\.\d+)?", expression) or expression == "omarchy_monitor_scale"):
                    raise _unsupported(f"Unsupported catch-all expression for {key}", text, found.start())
            catch_all = {"line": line, "scale": "omarchy_monitor_scale" if "omarchy_monitor_scale" in original else "literal"}
        elif selector in selectors:
            conflicts.append(row)
        else:
            others.append(row)
    for token in re.finditer(r"\bhl\.monitor\b", masked):
        if not any(start <= token.start() < end for start, end in spans):
            raise _unsupported("Unsupported hl.monitor call shape", text, token.start())
    return {"catchAll": catch_all, "conflicts": conflicts, "others": others}


def toggles(home: Path) -> dict[str, Any]:
    root = home / ".local/state/omarchy/toggles/hypr"
    patterns = {
        "internal-monitor-disable": re.compile(r'^hl\.monitor\(\{ output = "([A-Za-z0-9._-]+)", disabled = true \}\)\s*$'),
        "internal-monitor-mirror": re.compile(r'^hl\.monitor\(\{ output = "([A-Za-z0-9._-]+)", mode = "preferred", position = "auto", scale = 1, mirror = "([A-Za-z0-9._-]+)" \}\)\s*$'),
        "internal-monitor-clamshell": re.compile(r'^hl\.monitor\(\{ output = "([A-Za-z0-9._-]+)", disabled = true \}\)\s*$'),
    }
    result: dict[str, Any] = {}
    for name, pattern in patterns.items():
        path = root / f"{name}.lua"
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            result[name] = None
            continue
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = ""
        match = pattern.fullmatch(content)
        result[name] = {"state": "known" if match else "unknown", "path": str(path), "name": path.name,
                        "bytes": raw.hex(), "connectors": list(match.groups()) if match else []}
    return result
