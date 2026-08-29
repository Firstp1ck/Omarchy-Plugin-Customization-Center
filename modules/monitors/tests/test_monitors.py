from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from customization_center.core import CcError
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def helpers():
    load_registry(ROOT, paths=Paths.from_env())
    return {name: importlib.import_module(f"cc_modules.monitors.{name}") for name in ("inventory", "identity", "geometry", "profile", "lua_render", "ownership")}


def test_inventory_rounding_dedup_and_warning(helpers):
    outputs, warnings = helpers["inventory"].parse_inventory((FIXTURES / "hyprctl/unparsed-mode.json").read_text())
    assert outputs[0]["refreshMilliHz"] == 60000
    assert outputs[0]["modes"] == [{"width": 1920, "height": 1080, "refreshMilliHz": 60000}]
    assert warnings[0].code == "monitors_unparsed_mode"


def test_inventory_connection_error(helpers):
    with pytest.raises(CcError, match="did not return JSON") as caught:
        helpers["inventory"].parse_inventory((FIXTURES / "hyprctl/not-json.txt").read_text())
    assert caught.value.code == "runtime_unavailable"


def test_duplicate_identity_requires_assignment(helpers):
    connected, _ = helpers["inventory"].parse_inventory((FIXTURES / "hyprctl/duplicate-description.json").read_text())
    template = json.loads((Path(__file__).parent / "fixtures/sample-draft.json").read_text())["profile"]["outputs"][0]
    first = {**template, "id": "left", "identity": {"description":"Same Panel SAME","make":"Acme","model":"Panel","serial":"SAME","connector":"HDMI-A-9"}}
    second = {**template, "id": "right", "identity": {"description":"Same Panel SAME","make":"Acme","model":"Panel","serial":"SAME","connector":"HDMI-A-9"}}
    ambiguous = helpers["identity"].match([first, second], connected)
    assert {item["outputId"] for item in ambiguous["ambiguous"]} == {"left", "right"}
    resolved = helpers["identity"].match([first, second], connected, {"left": "DP-1", "right": "DP-2"})
    assert resolved["matched"] == {"left": "DP-1", "right": "DP-2"}


def test_geometry_scale_overlap_and_gap(helpers):
    geometry = helpers["geometry"]
    assert geometry.nearest_valid(2560, 1440, 168) == (160, 192)
    a = {"id":"a","x":0,"y":0,"width":100,"height":100}
    assert not geometry.overlaps(a, {"id":"b","x":100,"y":0,"width":100,"height":100})
    assert geometry.overlaps(a, {"id":"b","x":99,"y":0,"width":100,"height":100})
    assert len(geometry.islands([a, {"id":"b","x":200,"y":0,"width":100,"height":100}])) == 2


def test_profile_unknown_field_and_renderer(helpers):
    draft = json.loads((Path(__file__).parent / "fixtures/sample-draft.json").read_text())
    value = draft["profile"]
    broken = {**value, "surprise": True}
    assert any(issue.pointer == "/profile/surprise" for issue in helpers["profile"].validate_profile(broken))
    connected, _ = helpers["inventory"].parse_inventory((FIXTURES / "hyprctl/laptop-only.json").read_text())
    rendered = helpers["lua_render"].render(value, {"laptop": "eDP-1"}, connected)
    assert 'output = "desc:Laptop Panel"' in rendered
    assert "scale = 2" in rendered


def test_loader_scanner_ignores_shipped_catchall(helpers):
    data = (FIXTURES / "monitors-lua/shipped-default.lua").read_bytes()
    result = helpers["ownership"].scan(data, [])
    assert result["catchAll"]["line"] == 3
    assert result["conflicts"] == []
