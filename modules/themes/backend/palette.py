from __future__ import annotations

import re
from typing import Any

PALETTE_ORDER = (
    "mode", "accent", "selection", "muted", "background", "dark_background",
    "darker_background", "lighter_background", "foreground", "dark_foreground",
    "light_foreground", "bright_foreground", "red", "yellow", "orange", "green",
    "cyan", "blue", "magenta", "brown", "bright_red", "bright_yellow",
    "bright_green", "bright_cyan", "bright_blue", "bright_magenta",
)
HEX_KEYS = PALETTE_ORDER[1:]
REQUIRED_INPUT = ("background", "foreground", "accent", "red", "yellow", "green", "cyan", "blue", "magenta")
OPTIONAL_BORDERS = ("hyprland_active_border", "hyprland_inactive_border")
HEX_RE = re.compile(r"^#[0-9a-f]{6}$")
STOP_RE = re.compile(r"^(?:rgba\([0-9a-f]{8}\)|rgb\([0-9a-f]{6}\))$")
ANGLE_RE = re.compile(r"^-?[0-9]{1,3}(?:\.[0-9]{1,2})?deg$")
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


def normalize_hex(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if HEX_RE.fullmatch(normalized) else None


def mix(first: str, second: str, amount: float) -> str:
    left = normalize_hex(first)
    right = normalize_hex(second)
    if left is None or right is None or not 0 <= amount <= 1:
        raise ValueError("mix requires two six-digit colors and an amount from zero to one")
    values = []
    for offset in (1, 3, 5):
        a = int(left[offset:offset + 2], 16)
        b = int(right[offset:offset + 2], 16)
        values.append(int(a * (1 - amount) + b * amount + 0.5))
    return "#" + "".join(f"{value:02x}" for value in values)


def valid_gradient(value: Any) -> bool:
    if not isinstance(value, str) or value != value.strip() or any(char in value for char in "'\"\\|&="):
        return False
    tokens = value.split(" ")
    if not tokens or any(not token for token in tokens):
        return False
    if ANGLE_RE.fullmatch(tokens[-1]):
        angle = float(tokens.pop()[:-3])
        if not -360 <= angle <= 360:
            return False
    return 1 <= len(tokens) <= 8 and all(STOP_RE.fullmatch(token) for token in tokens)


def _light(background: str) -> bool:
    return sum(int(background[index:index + 2], 16) for index in (1, 3, 5)) > 382


def normalize_palette(value: Any) -> tuple[dict[str, Any] | None, list[tuple[str, str]]]:
    if not isinstance(value, dict):
        return None, [("", "palette must be an object")]
    errors: list[tuple[str, str]] = []
    palette: dict[str, Any] = {}
    mode = value.get("mode")
    background = normalize_hex(value.get("background"))
    if mode not in {"dark", "light"}:
        mode = "light" if background and _light(background) else "dark"
    palette["mode"] = mode
    for key in REQUIRED_INPUT:
        normalized = normalize_hex(value.get(key))
        if normalized is None:
            errors.append((key, f"{key} must be #rrggbb"))
        else:
            palette[key] = normalized
    if errors:
        return None, errors
    foreground = palette["foreground"]
    background = palette["background"]
    seeds = {
        "selection": mix(background, foreground, 0.15),
        "muted": mix(foreground, background, 0.50),
        "dark_background": mix(background, "#000000", 0.25),
        "darker_background": mix(background, "#000000", 0.50),
        "lighter_background": mix(background, foreground, 0.08),
        "dark_foreground": mix(foreground, background, 0.40),
        "light_foreground": mix(foreground, "#000000" if mode == "light" else "#ffffff", 0.20 if mode == "light" else 0.08),
        "bright_foreground": foreground if mode == "light" else mix(foreground, "#ffffff", 0.15),
        "orange": mix(palette["yellow"], palette["red"], 0.40),
    }
    seeds["brown"] = mix(seeds["orange"], "#000000", 0.50)
    for base in ("red", "yellow", "green", "cyan", "blue", "magenta"):
        seeds["bright_" + base] = mix(palette[base], "#ffffff", 0.20)
    for key in HEX_KEYS:
        if key in palette:
            continue
        candidate = normalize_hex(value.get(key))
        palette[key] = candidate or seeds[key]
        if value.get(key) is not None and candidate is None:
            errors.append((key, f"{key} must be #rrggbb"))
    for key in OPTIONAL_BORDERS:
        candidate = value.get(key)
        if candidate is None:
            palette[key] = None
        elif valid_gradient(candidate.lower()):
            palette[key] = candidate.lower()
        else:
            errors.append((key, f"{key} must be one to eight rgb()/rgba() stops and an optional angle"))
    return (palette if not errors else None), errors


def valid_slug(value: Any) -> bool:
    return isinstance(value, str) and bool(SLUG_RE.fullmatch(value)) and "--" not in value
