from __future__ import annotations

import re
from typing import Any

from customization_center.core import toml_writer

from .palette import HEX_RE, PALETTE_ORDER, valid_gradient
from .sections import BORDER_REFS, CONTROL_ROLES, ROLES, SECTIONS

_GROUP_BREAKS = {"accent", "background", "foreground", "red", "bright_red", "hyprland_active_border"}


def _scalar(value: Any) -> str:
    rendered = toml_writer.dumps({"value": value}).strip()
    toml_writer.reparse(rendered + "\n", {"value": value})
    return rendered.split("=", 1)[1].strip()


def colors_toml(palette: dict[str, Any]) -> str:
    lines: list[str] = []
    expected: dict[str, Any] = {}
    for key in PALETTE_ORDER:
        if key in _GROUP_BREAKS and lines:
            lines.append("")
        value = palette[key]
        expected[key] = value
        lines.append(f"{key} = {_scalar(value)}")
    borders = [(key, palette.get(key)) for key in ("hyprland_active_border", "hyprland_inactive_border") if palette.get(key)]
    if borders:
        lines.append("")
        for key, value in borders:
            expected[key] = value
            lines.append(f"{key} = {_scalar(value)}")
    result = "\n".join(lines) + "\n"
    toml_writer.reparse(result, expected)
    return result


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
            if name == "polkit" and key == "border" and candidate not in BORDER_REFS:
                valid = False
        elif form == "alpha":
            valid = isinstance(candidate, (int, float)) and not isinstance(candidate, bool) and 0 <= candidate <= 1
        elif form == "bool":
            valid = isinstance(candidate, bool)
        elif form == "width":
            valid = isinstance(candidate, str) and bool(re.fullmatch(r"(?:[0-9]|[1-5][0-9]|6[0-4])(?: (?:[0-9]|[1-5][0-9]|6[0-4])){0,3}", candidate))
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
    if form in {"alpha", "scale"}:
        return _decimal(value)
    if form == "width" and " " not in value:
        return value
    return _scalar(value)


def section_toml(name: str, value: dict[str, Any]) -> str:
    errors = validate_section(name, value)
    if errors:
        raise ValueError("; ".join(f"{key}: {message}" for key, message in errors))
    lines = [f"[{name}]"]
    expected: dict[str, Any] = {}
    for key, form, _, _ in SECTIONS[name]:
        if value.get(key) is not None:
            serialized = _serialize(form, value[key])
            lines.append(f"{key} = {serialized}")
            expected[key] = int(value[key]) if form == "width" and " " not in value[key] else value[key]
    result = "\n".join(lines) + "\n"
    toml_writer.reparse(result, {name: expected})
    parsed = parse_shell(result)
    if name not in parsed or set(parsed[name]) != set(expected):
        raise ValueError("section did not round trip through the shell parser")
    return result


def parse_shell(text: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    section: dict[str, Any] | None = None
    section_re = re.compile(r"^\[([A-Za-z0-9_-]+)\]\s*(?:#.*)?$")
    quoted_re = re.compile(r'^([A-Za-z0-9_-]+)\s*=\s*"([^"\']*)"$')
    number_re = re.compile(r"^([A-Za-z0-9_-]+)\s*=\s*(-?\d+(?:\.\d+)?)$")
    width_re = re.compile(r"^([A-Za-z0-9_-]+)\s*=\s*((?:-?\d+(?:\.\d+)?\s+){1,3}-?\d+(?:\.\d+)?)$")
    word_re = re.compile(r"^([A-Za-z0-9_-]+)\s*=\s*([A-Za-z][A-Za-z0-9_-]*)$")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = section_re.fullmatch(line)
        if match:
            section = result.setdefault(match.group(1), {})
            continue
        if section is None:
            continue
        match = quoted_re.fullmatch(line)
        if match:
            section[match.group(1)] = match.group(2); continue
        match = width_re.fullmatch(line)
        if match:
            section[match.group(1)] = match.group(2); continue
        match = number_re.fullmatch(line)
        if match:
            raw_value = match.group(2)
            section[match.group(1)] = float(raw_value) if "." in raw_value else int(raw_value); continue
        match = word_re.fullmatch(line)
        if match:
            value: Any = match.group(2)
            if value in {"true", "false"}:
                value = value == "true"
            section[match.group(1)] = value
    return result
