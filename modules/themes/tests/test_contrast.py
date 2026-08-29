from __future__ import annotations

import sys


def test_wcag_vectors(themes_backend):
    contrast = sys.modules[themes_backend.__name__ + ".contrast"]
    assert contrast.ratio("#000000", "#ffffff") == 21.0
    assert round(contrast.ratio("#777777", "#ffffff"), 2) == 4.48
    assert contrast.composite("#ffffff", .5, "#000000") == "#808080"
