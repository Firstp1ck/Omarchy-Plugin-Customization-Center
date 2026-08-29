from __future__ import annotations

from typing import Any


def _rgba(value: str) -> tuple[float, float, float, float]:
    if not isinstance(value, str) or not value.startswith("#") or len(value) not in {7, 9}:
        raise ValueError(f"not a resolved color: {value!r}")
    channels = tuple(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))
    alpha = int(value[7:9], 16) / 255 if len(value) == 9 else 1.0
    return channels[0], channels[1], channels[2], alpha


def composite(foreground: str, alpha: float, background: str) -> str:
    fr, fg, fb, embedded = _rgba(foreground)
    br, bg, bb, _ = _rgba(background)
    effective = max(0.0, min(1.0, alpha * embedded))
    values = [round((component * effective + base * (1 - effective)) * 255)
              for component, base in zip((fr, fg, fb), (br, bg, bb))]
    return "#" + "".join(f"{value:02x}" for value in values)


def luminance(value: str) -> float:
    def channel(component: float) -> float:
        return component / 12.92 if component <= .04045 else ((component + .055) / 1.055) ** 2.4
    red, green, blue, _ = _rgba(value)
    return .2126 * channel(red) + .7152 * channel(green) + .0722 * channel(blue)


def ratio(first: str, second: str) -> float:
    a, b = luminance(first), luminance(second)
    return (max(a, b) + .05) / (min(a, b) + .05)


def _nearest(tokens: dict[str, Any], background: str, threshold: float) -> str | None:
    palette = tokens["palette"]
    candidates = ((key, value) for key, value in palette.items()
                  if isinstance(value, str) and len(value) == 7 and value.startswith("#"))
    passing = [(abs(luminance(value) - luminance(background)), key) for key, value in candidates
               if ratio(value, background) >= threshold]
    return min(passing)[1] if passing else None


def _entry(tokens: dict[str, Any], pair_id: str, foreground: str, background: str,
           warn: float, block: float | None, scenario: str, *, effective_alpha: float = 1.0,
           stop_index: int | None = None) -> dict[str, Any]:
    measured = ratio(foreground, background)
    invisible = (block is not None and measured < block) or effective_alpha <= .05
    passes = measured >= warn
    return {"pairId": pair_id, "warningId": f"themes_contrast_low:{pair_id}",
            "code": "themes_contrast_invisible" if invisible else f"themes_contrast_low:{pair_id}",
            "foreground": foreground, "background": background, "compositedBackdrop": background,
            "ratio": round(measured, 2), "threshold": warn, "blockThreshold": block,
            "effectiveAlpha": round(effective_alpha, 3), "passes": passes and not invisible,
            "blocked": invisible, "scenario": scenario, "stopIndex": stop_index,
            "nearestPaletteKey": _nearest(tokens, background, warn)}


def diagnostics(tokens_or_palette: dict[str, Any]) -> list[dict[str, Any]]:
    if "sections" not in tokens_or_palette:
        from .resolver import resolve_tokens
        tokens = resolve_tokens({"palette": tokens_or_palette, "sections": {}})
    else:
        tokens = tokens_or_palette
    palette = tokens["palette"]
    output = [
        _entry(tokens, "foreground/background", palette["foreground"], palette["background"], 4.5, 1.1, "palette"),
        _entry(tokens, "muted/background", palette["muted"], palette["background"], 3.0, None, "palette"),
        _entry(tokens, "accent/background", palette["accent"], palette["background"], 3.0, None, "palette"),
        _entry(tokens, "red/background", palette["red"], palette["background"], 3.0, None, "palette"),
    ]

    def surfaces(name: str, text_keys: tuple[tuple[str, float, float | None], ...]) -> None:
        section = tokens["sections"][name]
        alpha = float(section.get("background-alpha", 1.0))
        backdrops = [palette["background"]] + (["#000000", "#ffffff"] if alpha < .9 else [])
        for backdrop in backdrops:
            surface = composite(section["background"], alpha, backdrop)
            suffix = "" if backdrop == palette["background"] else "/" + ("black" if backdrop == "#000000" else "white")
            for key, warn, block in text_keys:
                output.append(_entry(tokens, f"{name}.{key}" + suffix, section[key], surface, warn, block, name))

    bar = tokens["sections"]["bar"]
    bar_surface = composite(bar["background"], float(bar["background-alpha"]), palette["background"])
    output.extend((
        _entry(tokens, "bar.text/bar.background", bar["text"], bar_surface, 4.5, 1.1, "bar"),
        _entry(tokens, "bar.active/bar.background", bar["active"], bar_surface, 3.0, None, "bar"),
    ))
    for name in ("popups", "tooltip"):
        surfaces(name, (("text", 4.5, 1.1),))
    surfaces("notifications", (("text", 4.5, 1.1), ("countdown", 3.0, None)))
    for name in ("launcher", "menu"):
        surfaces(name, (("text", 4.5, 1.1),))
        section = tokens["sections"][name]
        card = composite(section["background"], float(section["background-alpha"]), palette["background"])
        selected = composite(section["selected-background"], float(section["selected-background-alpha"]), card)
        output.append(_entry(tokens, f"{name}.selected-text/{name}.selected-background",
                             section["selected-text"], selected, 4.5, 1.1, name))
    surfaces("polkit", (("text", 4.5, 1.1), ("text-error", 3.0, None)))
    surfaces("lock", (("text", 4.5, 1.1), ("placeholder", 3.0, None), ("text-error", 3.0, None)))

    picker = tokens["sections"]["image-picker"]
    for backdrop in ("#000000", "#ffffff"):
        surface = composite(picker["scrim"], float(picker["scrim-alpha"]), backdrop)
        output.append(_entry(tokens, "image-picker.text/" + ("black" if backdrop == "#000000" else "white"),
                             picker["text"], surface, 4.5, None, "image-picker"))
    for state in ("normal", "hover-cursor", "focus", "selected"):
        item = tokens["controls"][state]
        fill = composite(item["color"], item["fillAlpha"], palette["background"])
        output.append(_entry(tokens, f"controls.{state}.foreground/fill", palette["foreground"], fill,
                             4.5, None, "controls"))

    for section_name, section_borders in tokens["borders"].items():
        surface_values = tokens["sections"][section_name]
        surface = surface_values.get("background", palette["background"])
        if not isinstance(surface, str) or not surface.startswith("#"):
            surface = palette["background"]
        for key, spec in section_borders.items():
            measured: list[dict[str, Any]] = []
            for index, stop in enumerate(spec.get("stops", [])):
                visible = composite(stop["color"], stop["alpha"], surface)
                measured.append(_entry(tokens, f"{section_name}.{key}/surface", visible, surface,
                                       3.0, None, section_name, effective_alpha=stop["alpha"], stop_index=index))
            if measured:
                output.append(min(measured, key=lambda item: item["ratio"]))
    return output
