from pathlib import Path

from modules.menu.backend.jsonc_menu import parse_safe
from modules.menu.backend.model import build_effective, resolve_route

FIXTURES = Path(__file__).parent / "fixtures"


def _document(name):
    return parse_safe((FIXTURES / name).read_bytes())[0]


def test_custom_entries_append_and_label_shadow_is_full_entry():
    default = _document("default-71b0887c.jsonc")
    custom = build_effective(default, _document("user-basic-custom.jsonc"), "full-shadow")
    assert custom["order"][-2:] == ["personal", "personal.notes"]
    assert custom["rows"]["personal.notes"]["origin"] == "custom"
    shadow = build_effective(default, _document("user-label-only-override.jsonc"), "full-shadow")
    assert shadow["rows"]["about"]["fields"]["action"] == ""
    assert shadow["rows"]["about"]["provenance"]["action"] == "cleared"


def test_sparse_shadow_keeps_action_and_route_is_static():
    effective = build_effective(_document("default-71b0887c.jsonc"), _document("user-label-only-override.jsonc"), "sparse")
    assert effective["rows"]["about"]["fields"]["action"] == "omarchy-launch-about"
    route = resolve_route(effective, "menu")
    assert route["resolved"] == "root" and not route["wouldRunAction"]
