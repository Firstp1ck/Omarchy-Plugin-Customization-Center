from __future__ import annotations

import json
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = json.loads((FIXTURES / "sample-draft.json").read_text())


def helper(themes_backend, name):
    return sys.modules[themes_backend.__name__ + "." + name]


def test_resolver_covers_sections_roles_metrics_borders_controls_and_masks(themes_backend):
    resolver = helper(themes_backend, "resolver")
    draft = json.loads(json.dumps(SAMPLE))
    sections = helper(themes_backend, "sections")
    draft["sections"]["controls"] = sections.defaults("controls", draft["palette"])
    draft["sections"]["controls"]["focus-border"] = "rgba(7aa2f7ee) rgba(bb9af7ee) 45deg"
    draft["sections"]["font"] = sections.defaults("font", draft["palette"])
    draft["sections"]["font"]["base-size"] = 16
    draft["sections"]["spacing"] = sections.defaults("spacing", draft["palette"])
    tokens = resolver.resolve_tokens(draft, {"font.base-size": 18, "menu.selected-text": "foreground"})
    assert set(tokens["sections"]) == set(sections.SECTIONS)
    assert tokens["sections"]["bar"]["active"] == draft["palette"]["red"]
    assert tokens["sections"]["menu"]["selected-text"] == draft["palette"]["foreground"]
    assert tokens["metrics"]["font"]["baseSize"] == 18
    assert tokens["metrics"]["spacing"]["md"] > 0
    assert len(tokens["borders"]["controls"]["focus-border"]["stops"]) == 2
    assert set(tokens["controls"]) >= {"normal", "hover-cursor", "focus", "selected"}
    assert {(item["section"], item["key"]) for item in tokens["masked"]} == {
        ("font", "base-size"), ("menu", "selected-text")
    }


def test_contrast_matrix_has_surface_control_border_bounds_and_blockers(themes_backend):
    resolver = helper(themes_backend, "resolver")
    contrast = helper(themes_backend, "contrast")
    tokens = resolver.resolve_tokens(SAMPLE)
    rows = contrast.diagnostics(tokens)
    ids = {row["pairId"] for row in rows}
    assert {"foreground/background", "bar.text/bar.background", "menu.selected-text/menu.selected-background",
            "image-picker.text/black", "image-picker.text/white", "controls.focus.foreground/fill",
            "controls.focus-border/surface"} <= ids
    invisible = json.loads(json.dumps(SAMPLE))
    invisible["palette"]["foreground"] = invisible["palette"]["background"]
    blocked = contrast.diagnostics(resolver.resolve_tokens(invisible))
    assert any(row["pairId"] == "foreground/background" and row["blocked"] for row in blocked)
    assert all(row["warningId"].startswith("themes_contrast_low:") for row in rows)
