from __future__ import annotations

import json
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def helper(themes_backend, name):
    return sys.modules[themes_backend.__name__ + "." + name]


def test_colors_writer_order_and_trailing_lf(themes_backend):
    writer = helper(themes_backend, "writer")
    palette = json.loads((FIXTURES / "sample-draft.json").read_text())["palette"]
    rendered = writer.colors_toml(palette)
    assert rendered.startswith('mode = "dark"\n\naccent = "#7aa2f7"')
    assert rendered.endswith('\nhyprland_active_border = "rgba(7aa2f7ee) rgba(bb9af7ee) 45deg"\n')
    assert "hyprland_inactive_border" not in rendered


def test_section_writer_round_trip(themes_backend):
    sections = helper(themes_backend, "sections")
    writer = helper(themes_backend, "writer")
    value = {key: default for key, _, default, required in sections.SECTIONS["controls"] if required}
    rendered = writer.section_toml("controls", value)
    parsed = writer.parse_shell(rendered)
    assert parsed["controls"]["normal-border-width"] == 1
    assert parsed["controls"]["pressed-fill-alpha"] == .22
