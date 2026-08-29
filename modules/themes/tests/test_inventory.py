from __future__ import annotations

import hashlib
import json
import sys


def test_inventory_classification(themes_backend, isolated_home):
    inventory = sys.modules[themes_backend.__name__ + ".inventory"]
    theme = isolated_home / ".config/omarchy/themes/mine"
    theme.mkdir(parents=True)
    colors = b'mode = "dark"\n'
    (theme / "colors.toml").write_bytes(colors)
    assert inventory.classify(theme, None)[0] == "plain"
    sidecar = {"files": {"colors.toml": hashlib.sha256(colors).hexdigest()}}
    assert inventory.classify(theme, sidecar)[0] == "managed"
    (theme / "hyprland.lua").write_text("return {}\n")
    classification, unsupported = inventory.classify(theme, sidecar)
    assert classification == "managed-modified"
    assert unsupported == ["hyprland.lua"]
