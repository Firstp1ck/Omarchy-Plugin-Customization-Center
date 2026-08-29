from __future__ import annotations

from typing import Any

TEMPLATE_SHA256 = "bdc8e76a5a9a700adaca0d2fa44a2a340584892fd507e3fcbd4f9a4843765242"
ROLES = {"foreground", "text", "accent", "urgent", "muted", "background", "transparent"}
CONTROL_ROLES = ROLES - {"muted"}
BORDER_REFS = {"hyprland.active-border", "hyprland.active-border-foreground"}


def _surface(alpha: float = 1.0, border: str = "hyprland.active-border") -> list[tuple[str, str, Any, bool]]:
    return [
        ("background", "color", "background", True), ("background-alpha", "alpha", alpha, True),
        ("text", "color", "foreground", True), ("border", "border", border, True),
        ("border-alpha", "alpha", 1.0, True), ("border-width", "width", None, False),
    ]

SECTIONS: dict[str, list[tuple[str, str, Any, bool]]] = {
    "bar": [
        ("background", "color", "background", True), ("background-alpha", "alpha", 1.0, True),
        ("text", "color", "foreground", True), ("active", "color", "red", True),
        ("scale-with-font", "bool", True, True), ("size-horizontal", "bar-size", 26, True),
        ("size-vertical", "bar-size", 28, True),
    ],
    "controls": sum(([ (f"{state}-color", "control-color", "foreground", True),
                         (f"{state}-fill-alpha", "alpha", alpha, True),
                         (f"{state}-border", "border", "foreground", True),
                         (f"{state}-border-width", "width", "0" if state == "selected" else "1", True),
                         (f"{state}-border-alpha", "alpha", border_alpha, True) ]
                       for state, alpha, border_alpha in (("normal", .04, .4), ("hover-cursor", .08, .25),
                                                         ("focus", .08, .25), ("selected", .18, 1.0))), []) +
                [("pressed-fill-alpha", "alpha", .22, True), ("selection-fill-alpha", "alpha", .35, True)],
    "spacing": [("scale", "scale", 1.0, True), ("scale-with-font", "bool", True, True)] +
               [(key, "spacing", None, False) for key in (
                   "xxs xs sm md lg xl xxl xxxl huge control-gap control-padding-x control-padding-y input-padding-y "
                   "control-height popup-row-height row-gap row-padding-x label-gap panel-gap panel-padding popup-padding "
                   "dropdown-width searchable-dropdown-width number-field-width searchable-popup-min-height").split()],
    "font": [("base-size", "base-size", 12, True)] +
            [(key, "font-size", None, False) for key in
             "caption body-small body subtitle title heading display display-large icon-small icon icon-large".split()],
    "popups": _surface(),
    "tooltip": [item for item in _surface(.97, "hyprland.active-border-foreground") if item[0] != "border-width"],
    "notifications": _surface() + [("countdown", "color", "accent", True)],
}

for name, alpha in (("launcher", .95), ("menu", 1.0)):
    SECTIONS[name] = _surface(alpha, "hyprland.active-border-foreground") + [
        ("scrim", "color", "background", True), ("scrim-alpha", "alpha", .5, True),
        ("selected-background", "color", "foreground", True), ("selected-background-alpha", "alpha", .08, True),
        ("selected-text", "color", "accent", True), ("selected-border", "border", "hyprland.active-border-foreground", True),
        ("selected-border-alpha", "alpha", .25, True), ("selected-border-width", "width", None, False),
    ]
SECTIONS["polkit"] = _surface() + [
    ("text-error", "color", "red", True), ("border-error", "border", "red", True),
    ("scrim", "color", "background", True), ("scrim-alpha", "alpha", .5, True),
    ("accent", "color", "accent", True),
]
SECTIONS["lock"] = [
    ("background", "color", "background", True), ("background-alpha", "alpha", .8, True),
    ("text", "color", "foreground", True), ("placeholder", "color", None, True),
    ("text-error", "color", "red", True), ("border", "border", "hyprland.active-border", True),
    ("border-active", "border", "hyprland.active-border", True), ("border-error", "border", "red", True),
    ("border-alpha", "alpha", 1.0, True), ("selection", "color", "accent", True),
    ("selection-alpha", "alpha", .45, True), ("border-width", "width", None, False),
    ("border-active-width", "width", None, False), ("border-error-width", "width", None, False),
]
SECTIONS["image-picker"] = [
    ("scrim", "color", "background", True), ("scrim-alpha", "alpha", .5, True),
    ("text", "color", "foreground", True), ("selected-border", "border", "accent", True),
    ("selected-border-alpha", "alpha", 1.0, True), ("unselected-border", "border", "foreground", True),
    ("unselected-border-alpha", "alpha", .28, True), ("selected-border-width", "width", None, False),
    ("unselected-border-width", "width", None, False),
]


def defaults(name: str, palette: dict[str, Any]) -> dict[str, Any]:
    values = {key: (palette[default] if isinstance(default, str) and default in palette and default not in ROLES else default)
              for key, _, default, _ in SECTIONS[name]}
    if name == "lock":
        from .palette import mix
        values["placeholder"] = mix(palette["foreground"], palette["background"], .34)
    return values
