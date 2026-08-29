from __future__ import annotations

import json
import re
from typing import Any

from customization_center.core import CcError, Warning

_MODE = re.compile(r"^(\d+)x(\d+)@(\d+(?:\.\d+)?)(?:Hz)?$")
_INTERNAL = re.compile(r"^(?:eDP|LVDS|DSI)-")


def parse_mode(value: str) -> dict[str, int] | None:
    match = _MODE.fullmatch(value)
    if not match:
        return None
    return {"width": int(match.group(1)), "height": int(match.group(2)),
            "refreshMilliHz": round(float(match.group(3)) * 1000)}


def parse_inventory(text: str) -> tuple[list[dict[str, Any]], tuple[Warning, ...]]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        code = "runtime_unavailable" if "connect" in text.lower() or "socket" in text.lower() else "malformed_output"
        raise CcError(code, "hyprctl monitors all did not return JSON", {"output": text[:8192]}) from error
    if not isinstance(raw, list):
        raise CcError("malformed_output", "hyprctl monitors all must return an array", {"output": text[:8192]})
    outputs: list[dict[str, Any]] = []
    warnings: list[Warning] = []
    required = {"name": str, "description": str, "make": str, "model": str, "serial": str,
                "width": int, "height": int, "x": int, "y": int, "scale": (int, float),
                "transform": int, "disabled": bool, "availableModes": list}
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or any(key not in item or not isinstance(item[key], kind) for key, kind in required.items()):
            raise CcError("malformed_output", f"Monitor {index} has missing or mistyped fields", {"output": text[:8192]})
        seen: set[tuple[int, int, int]] = set()
        modes: list[dict[str, int]] = []
        unparsed: list[str] = []
        for token in item["availableModes"]:
            mode = parse_mode(token) if isinstance(token, str) else None
            if mode is None:
                unparsed.append(str(token))
                continue
            key = (mode["width"], mode["height"], mode["refreshMilliHz"])
            if key not in seen:
                seen.add(key); modes.append(mode)
        if unparsed:
            warnings.append(Warning("monitors_unparsed_mode", f"Ignored unrecognized modes for {item['name']}: {', '.join(unparsed)}", item["name"], "Choose a mode reported by Hyprland"))
        mirror = item.get("mirrorOf")
        outputs.append({
            "connector": item["name"], "description": item["description"], "make": item["make"],
            "model": item["model"], "serial": item["serial"], "internal": bool(_INTERNAL.match(item["name"])),
            "disabled": item["disabled"], "focused": bool(item.get("focused", False)),
            "dpms": bool(item.get("dpmsStatus", True)), "mirrorOf": None if mirror in {None, "none"} else str(mirror),
            "width": item["width"], "height": item["height"],
            "refreshMilliHz": round(float(item.get("refreshRate", 0)) * 1000), "x": item["x"], "y": item["y"],
            "scale120": round(float(item["scale"]) * 120), "transform": item["transform"],
            "modes": modes, "rawModes": list(item["availableModes"]), "vrrActive": bool(item.get("vrr", False))
        })
    return outputs, tuple(warnings)


def read(ctx: Any, timeout_s: float = 3) -> tuple[list[dict[str, Any]], tuple[Warning, ...]]:
    result = ctx.commands.run(["hyprctl", "-j", "monitors", "all"], timeout_s=max(0.001, timeout_s), capture_limit=1024 * 1024)
    if result.timed_out or result.exit_code != 0:
        raise CcError("runtime_unavailable", result.stderr.strip() or "hyprctl monitors all failed")
    return parse_inventory(result.stdout)
