from __future__ import annotations

import math
from typing import Any


def nearest_valid(width: int, height: int, scale120: int) -> tuple[int | None, int | None]:
    divisor = math.gcd(width * 120, height * 120)
    lower = next((value for value in range(scale120 - 1, 29, -1) if divisor % value == 0), None)
    upper = next((value for value in range(scale120 + 1, 961) if divisor % value == 0), None)
    return lower, upper


def logical(rule: dict[str, Any]) -> dict[str, int]:
    width, height = int(rule["mode"]["width"]), int(rule["mode"]["height"])
    if int(rule.get("transform", 0)) in {1, 3, 5, 7}:
        width, height = height, width
    scale = int(rule["scale120"])
    if (width * 120) % scale or (height * 120) % scale:
        lower, upper = nearest_valid(width, height, scale)
        raise ValueError(f"invalid scale120 {scale}; nearest values are {lower} and {upper}")
    position = rule.get("position") or {"x": 0, "y": 0}
    return {"id": rule["id"], "x": int(position["x"]), "y": int(position["y"]),
            "width": width * 120 // scale, "height": height * 120 // scale}


def overlaps(first: dict[str, int], second: dict[str, int]) -> bool:
    return max(first["x"], second["x"]) < min(first["x"] + first["width"], second["x"] + second["width"]) and max(first["y"], second["y"]) < min(first["y"] + first["height"], second["y"] + second["height"])


def adjacent(first: dict[str, int], second: dict[str, int]) -> bool:
    vertical = (first["x"] + first["width"] == second["x"] or second["x"] + second["width"] == first["x"]) and min(first["y"] + first["height"], second["y"] + second["height"]) > max(first["y"], second["y"])
    horizontal = (first["y"] + first["height"] == second["y"] or second["y"] + second["height"] == first["y"]) and min(first["x"] + first["width"], second["x"] + second["width"]) > max(first["x"], second["x"])
    return vertical or horizontal


def islands(rectangles: list[dict[str, int]]) -> list[list[str]]:
    remaining = set(range(len(rectangles))); groups: list[list[str]] = []
    while remaining:
        pending = [remaining.pop()]; group: list[str] = []
        while pending:
            index = pending.pop(); group.append(str(rectangles[index]["id"]))
            joined = {other for other in remaining if adjacent(rectangles[index], rectangles[other])}
            remaining -= joined; pending.extend(joined)
        groups.append(sorted(group))
    return groups


def preview(profile: dict[str, Any]) -> dict[str, Any]:
    rectangles = [logical(rule) for rule in profile.get("outputs", []) if rule.get("enabled") and not rule.get("mirrorOf")]
    if not rectangles:
        return {"schemaVersion": 1, "rectangles": [], "bounds": {"x": 0, "y": 0, "width": 0, "height": 0}}
    left = min(item["x"] for item in rectangles); top = min(item["y"] for item in rectangles)
    right = max(item["x"] + item["width"] for item in rectangles); bottom = max(item["y"] + item["height"] for item in rectangles)
    return {"schemaVersion": 1, "rectangles": rectangles, "bounds": {"x": left, "y": top, "width": right - left, "height": bottom - top}}
