from __future__ import annotations

import re
from typing import Any

from .palette import mix, normalize_palette
from .sections import SECTIONS, defaults

_SPACING_DEFAULTS = dict(zip(
    "xxs xs sm md lg xl xxl xxxl huge control-gap control-padding-x control-padding-y input-padding-y control-height popup-row-height row-gap row-padding-x label-gap panel-gap panel-padding popup-padding dropdown-width searchable-dropdown-width number-field-width searchable-popup-min-height".split(),
    (2, 3, 4, 6, 8, 10, 12, 14, 18, 8, 10, 6, 7, 28, 28, 8, 12, 4, 14, 18, 14, 240, 260, 120, 220),
))
_FONT_MULTIPLIERS = {
    "caption": .833, "body-small": .917, "body": 1.0, "subtitle": 1.083,
    "title": 1.167, "heading": 1.333, "display": 2.0, "display-large": 2.333,
    "icon-small": .917, "icon": 1.167, "icon-large": 1.5,
}
_STOP = re.compile(r"(?:rgb\(([0-9a-f]{6})\)|rgba\(([0-9a-f]{8})\))")


def _role(value: Any, palette: dict[str, Any], hyprland: dict[str, str]) -> Any:
    roles = {
        "foreground": palette["foreground"], "text": palette["foreground"],
        "accent": palette["accent"], "urgent": palette["red"], "muted": palette["muted"],
        "background": palette["background"], "transparent": "#00000000",
        "hyprland.active-border": hyprland["active-border"],
        "hyprland.active-border-foreground": hyprland["active-border-foreground"],
    }
    if value in palette and isinstance(palette[value], str):
        return palette[value]
    return roles.get(value, value)


def _resolved_border(value: Any, palette: dict[str, Any], hyprland: dict[str, str]) -> str:
    raw = str(_role(value, palette, hyprland))
    words = raw.split()
    output: list[str] = []
    for word in words:
        resolved = str(_role(word, palette, hyprland))
        output.append(resolved)
    return " ".join(output)


def _hex_with_alpha(value: str, alpha: float) -> str:
    if value == "#00000000":
        return value
    if re.fullmatch(r"#[0-9a-f]{6}", value):
        return value + f"{max(0, min(255, round(alpha * 255))):02x}"
    return value


def border_stops(value: str) -> list[tuple[str, float]]:
    if re.fullmatch(r"#[0-9a-f]{6}", value):
        return [(value, 1.0)]
    if re.fullmatch(r"#[0-9a-f]{8}", value):
        return [(value[:7], int(value[7:9], 16) / 255)]
    stops: list[tuple[str, float]] = []
    for match in _STOP.finditer(value):
        raw = match.group(1) or match.group(2)
        stops.append(("#" + raw[:6], int(raw[6:8], 16) / 255 if len(raw) == 8 else 1.0))
    return stops


def resolve_tokens(draft: dict[str, Any], machine_override: dict[str, Any] | None = None,
                   effective: bool = True) -> dict[str, Any]:
    palette, errors = normalize_palette(draft.get("palette"))
    if palette is None or errors:
        raise ValueError("invalid palette")
    palette = {**palette, "urgent": palette["red"]}
    hyprland = {
        "active-border": palette.get("hyprland_active_border") or palette["accent"],
        "active-border-foreground": palette.get("hyprland_active_border") or palette["foreground"],
        "inactive-border": palette.get("hyprland_inactive_border") or "rgba(595959aa)",
    }
    source_sections = draft.get("sections") if isinstance(draft.get("sections"), dict) else {}
    sections: dict[str, dict[str, Any]] = {}
    for name in SECTIONS:
        values = defaults(name, palette)
        custom = source_sections.get(name)
        if isinstance(custom, dict):
            values.update(custom)
        sections[name] = values

    masked: list[dict[str, Any]] = []
    machine = machine_override or {}
    if effective:
        for flat_key, override in machine.items():
            if not isinstance(flat_key, str) or "." not in flat_key:
                continue
            section, key = flat_key.split(".", 1)
            if section in sections and key in {item[0] for item in SECTIONS[section]}:
                masked.append({"section": section, "key": key, "draftValue": sections[section].get(key),
                               "overrideValue": override})
                sections[section][key] = override

    resolved: dict[str, dict[str, Any]] = {}
    borders: dict[str, dict[str, dict[str, Any]]] = {}
    for name, values in sections.items():
        section: dict[str, Any] = {}
        section_borders: dict[str, dict[str, Any]] = {}
        forms = {key: form for key, form, _, _ in SECTIONS[name]}
        for key, value in values.items():
            form = forms.get(key)
            if value is None:
                section[key] = None
            elif form in {"color", "control-color"}:
                section[key] = _role(value, palette, hyprland)
            elif form == "border":
                raw = _resolved_border(value, palette, hyprland)
                section[key] = raw
                width = values.get(key + "-width") or values.get("border-width") or "1"
                alpha = float(values.get(key + "-alpha", values.get("border-alpha", 1.0)))
                section_borders[key] = {"raw": raw, "width": str(width), "alpha": alpha,
                                        "stops": [{"color": color, "alpha": stop_alpha * alpha}
                                                  for color, stop_alpha in border_stops(raw)]}
            else:
                section[key] = value
        for key, value in tuple(section.items()):
            if key.endswith("-alpha") or value is None:
                continue
            alpha_key = key + "-alpha"
            if alpha_key in section and isinstance(value, str) and value.startswith("#"):
                section[key + "-composed"] = _hex_with_alpha(value, float(section[alpha_key]))
        resolved[name] = section
        borders[name] = section_borders

    font_values = sections["font"]
    base_size = max(1, int(font_values.get("base-size") or 12))
    font = {"baseSize": base_size, "scale": max(1 / 12, base_size / 12)}
    for key, multiplier in _FONT_MULTIPLIERS.items():
        value = font_values.get(key)
        font[key] = max(1, round(float(value) if value is not None else base_size * multiplier))

    spacing_values = sections["spacing"]
    spacing_scale = float(spacing_values.get("scale") or 1.0)
    effective_scale = spacing_scale * (font["scale"] if spacing_values.get("scale-with-font", True) else 1)
    spacing: dict[str, Any] = {"scale": spacing_scale, "scaleWithFont": bool(spacing_values.get("scale-with-font", True)),
                               "effective": effective_scale}
    for key, fallback in _SPACING_DEFAULTS.items():
        override = spacing_values.get(key)
        spacing[key] = round(float(override)) if override is not None else max(1, round(fallback * effective_scale))

    bar_values = sections["bar"]
    bar_scale = font["scale"] if bar_values.get("scale-with-font", True) else 1
    bar = {"sizeHorizontal": max(1, round(float(bar_values.get("size-horizontal") or 26) * bar_scale)),
           "sizeVertical": max(1, round(float(bar_values.get("size-vertical") or 28) * bar_scale)),
           "scaleWithFont": bool(bar_values.get("scale-with-font", True))}

    controls: dict[str, Any] = {}
    control_values = resolved["controls"]
    for state in ("normal", "hover-cursor", "focus", "selected"):
        color = control_values[f"{state}-color"]
        fill_alpha = float(control_values[f"{state}-fill-alpha"])
        controls[state] = {"color": color, "fill": _hex_with_alpha(color, fill_alpha), "fillAlpha": fill_alpha,
                           "border": borders["controls"].get(f"{state}-border", {})}
    controls["pressedFillAlpha"] = float(control_values["pressed-fill-alpha"])
    controls["selectionFillAlpha"] = float(control_values["selection-fill-alpha"])

    return {"palette": palette, "roles": {key: _role(key, palette, hyprland) for key in
            ("foreground", "text", "accent", "urgent", "muted", "background", "transparent")},
            "hyprland": hyprland, "sections": resolved, "borders": borders, "metrics": {
                "font": font, "spacing": spacing, "bar": bar}, "controls": controls,
            "masked": masked, "machineOverride": machine, "effective": effective}
