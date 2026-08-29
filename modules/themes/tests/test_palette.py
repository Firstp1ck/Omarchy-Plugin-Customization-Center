from __future__ import annotations

import sys


def helper(themes_backend, name):
    return sys.modules[themes_backend.__name__ + "." + name]


def test_hex_normalization_and_seed_palette(themes_backend):
    palette = helper(themes_backend, "palette")
    normalized, errors = palette.normalize_palette({
        "mode": "dark", "background": "#101010", "foreground": "#F0F0F0", "accent": "#3366FF",
        "red": "#ff0000", "yellow": "#ffff00", "green": "#00ff00", "cyan": "#00ffff",
        "blue": "#0000ff", "magenta": "#ff00ff",
    })
    assert errors == []
    assert normalized["foreground"] == "#f0f0f0"
    assert set(palette.PALETTE_ORDER) <= set(normalized)
    assert normalized["orange"] == palette.mix("#ffff00", "#ff0000", .4)


def test_gradient_grammar(themes_backend):
    palette = helper(themes_backend, "palette")
    assert palette.valid_gradient("rgba(3366ffee) rgba(ff00ffee) 45.5deg")
    assert palette.valid_gradient("rgb(3366ff)")
    assert not palette.valid_gradient("rgba(3366ffee) rgba(ff00ffee) 361deg")
    assert not palette.valid_gradient("rgba(3366ffee) {{ accent }}")
