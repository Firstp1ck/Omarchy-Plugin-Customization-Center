from __future__ import annotations

from typing import Any


def _rgb(value: str) -> tuple[float, float, float]:
    return tuple(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))  # type: ignore[return-value]


def composite(foreground: str, alpha: float, background: str) -> str:
    fg = _rgb(foreground); bg = _rgb(background)
    values = [round((fg[index] * alpha + bg[index] * (1 - alpha)) * 255) for index in range(3)]
    return "#" + "".join(f"{value:02x}" for value in values)


def luminance(value: str) -> float:
    def channel(component: float) -> float:
        return component / 12.92 if component <= .04045 else ((component + .055) / 1.055) ** 2.4
    red, green, blue = (channel(item) for item in _rgb(value))
    return .2126 * red + .7152 * green + .0722 * blue


def ratio(first: str, second: str) -> float:
    a, b = luminance(first), luminance(second)
    return (max(a, b) + .05) / (min(a, b) + .05)


def diagnostics(palette: dict[str, Any]) -> list[dict[str, Any]]:
    pairs = (("foreground/background", "foreground", 4.5), ("muted/background", "muted", 3.0),
             ("accent/background", "accent", 3.0), ("red/background", "red", 3.0))
    output = []
    for pair_id, key, threshold in pairs:
        measured = ratio(palette[key], palette["background"])
        output.append({"pairId": pair_id, "foreground": palette[key], "background": palette["background"],
                       "ratio": round(measured, 2), "threshold": threshold, "passes": measured >= threshold})
    return output
