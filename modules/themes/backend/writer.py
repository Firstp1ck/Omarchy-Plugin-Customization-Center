from __future__ import annotations

import tomllib
from typing import Any

from .palette import HEX_RE, PALETTE_ORDER, valid_gradient
from .sections import BORDER_REFS, CONTROL_ROLES, ROLES, SECTIONS

_GROUP_BREAKS = {"accent", "background", "foreground", "red", "bright_red", "hyprland_active_border"}


def colors_toml(palette: dict[str, Any]) -> str:
    lines: list[str] = []
    for key in PALETTE_ORDER:
        if key in _GROUP_BREAKS and lines:
            lines.append("")
        lines.append(f'{key} = "{palette[key]}"')
    borders = [(key, palette.get(key)) for key in ("hyprland_active_border", "hyprland_inactive_border") if palette.get(key)]
    if borders:
        lines.append("")
        lines.extend(f'{key} = "{value}"' for key, value in borders)
    return "\n".join(lines) + "\n"


def _decimal(value: Any) -> str:
    number = float(value)
    text = f"{number:.3f}".rstrip("0").rstrip(".")
    return text + ".0" if "." not in text else text


def _valid_color(value: Any, controls: bool = False) -> bool:
    roles = CONTROL_ROLES if controls else ROLES
    return isinstance(value, str) and (bool(HEX_RE.fullmatch(value)) or value in roles)


def validate_section(name: str, value: Any) -> list[tuple[str, str]]:
    if name not in SECTIONS:
        return [(name, "unknown section")]
    if value is None:
        return []
    if not isinstance(value, dict):
        return [(name, "section must be an object or null")]
    table = {key: (form, required) for key, form, _, required in SECTIONS[name]}
    errors: list[tuple[str, str]] = []
    for key in value:
        if key not in table:
            errors.append((key, "unknown section key"))
    for key, (form, required) in table.items():
        candidate = value.get(key)
        if candidate is None:
            if required:
                errors.append((key, "required section key is missing"))
            continue
        valid = False
        if form in {"color", "control-color"}:
            valid = _valid_color(candidate, form == "control-color")
        elif form == "border":
            valid = _valid_color(candidate, name == "controls") or candidate in BORDER_REFS or valid_gradient(candidate)
        elif form == "alpha":
            valid = isinstance(candidate, (int, float)) and not isinstance(candidate, bool) and 0 <= candidate <= 1
        elif form == "bool":
            valid = isinstance(candidate, bool)
        elif form == "width":
            valid = isinstance(candidate, str) and 1 <= len(candidate.split()) <= 4 and all(
                token.isdigit() and 0 <= int(token) <= 64 for token in candidate.split())
        elif form == "scale":
            valid = isinstance(candidate, (int, float)) and not isinstance(candidate, bool) and .25 <= candidate <= 4
        elif form == "bar-size":
            valid = isinstance(candidate, int) and not isinstance(candidate, bool) and 1 <= candidate <= 512
        elif form == "base-size":
            valid = isinstance(candidate, int) and not isinstance(candidate, bool) and 1 <= candidate <= 128
        elif form == "font-size":
            valid = isinstance(candidate, int) and not isinstance(candidate, bool) and 1 <= candidate <= 256
        elif form == "spacing":
            valid = isinstance(candidate, int) and not isinstance(candidate, bool) and 0 <= candidate <= 4096
        if not valid:
            errors.append((key, f"invalid {form} value"))
    return errors


def _serialize(form: str, value: Any) -> str:
    if form in {"color", "control-color", "border"}:
        return f'"{value}"'
    if form in {"alpha", "scale"}:
        return _decimal(value)
    if form == "width":
        return value if " " not in value else f'"{value}"'
    if form == "bool":
        return "true" if value else "false"
    return str(value)


def section_toml(name: str, value: dict[str, Any]) -> str:
    errors = validate_section(name, value)
    if errors:
        raise ValueError("; ".join(f"{key}: {message}" for key, message in errors))
    lines = [f"[{name}]"]
    for key, form, _, _ in SECTIONS[name]:
        if value.get(key) is not None:
            lines.append(f"{key} = {_serialize(form, value[key])}")
    result = "\n".join(lines) + "\n"
    parsed = tomllib.loads(result)
    if name not in parsed or set(parsed[name]) != {key for key, item in value.items() if item is not None}:
        raise ValueError("section did not round trip")
    return result


def parse_shell(text: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    section: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1]
            section = result.setdefault(name, {})
            continue
        if section is None or "=" not in line:
            continue
        key, raw_value = (part.strip() for part in line.split("=", 1))
        if raw_value.startswith('"') and raw_value.endswith('"'):
            value: Any = raw_value[1:-1]
        elif raw_value in {"true", "false"}:
            value = raw_value == "true"
        else:
            try:
                value = float(raw_value) if "." in raw_value else int(raw_value)
            except ValueError:
                continue
        section[key] = value
    return result
