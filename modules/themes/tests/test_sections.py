from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path


def test_section_table_matches_pinned_template(themes_backend, isolated_home):
    sections = sys.modules[themes_backend.__name__ + ".sections"]
    template = Path(os.environ["OMARCHY_PATH"]) / "default/themed/shell.toml.tpl"
    assert hashlib.sha256(template.read_bytes()).hexdigest() == sections.TEMPLATE_SHA256
    assert set(sections.SECTIONS) == {"bar", "controls", "spacing", "font", "popups", "tooltip", "notifications", "launcher", "menu", "polkit", "lock", "image-picker"}
