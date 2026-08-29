from pathlib import Path

import pytest

from modules.menu.backend.jsonc_menu import js_key_order, parse_runtime, parse_safe, parse_with_parity

FIXTURES = Path(__file__).parent / "fixtures"


def test_template_and_default_parse():
    template, state, diagnostics = parse_with_parity((FIXTURES / "template.jsonc").read_bytes())
    assert state == "empty" and template["entries"] == [] and diagnostics == []
    default, state, diagnostics = parse_with_parity((FIXTURES / "default-71b0887c.jsonc").read_bytes())
    assert state == "ok" and len(default["entries"]) == 328 and diagnostics == []


@pytest.mark.parametrize("name,state", [
    ("user-comments-indented.jsonc", "ok"),
    ("user-inline-comment.jsonc", "failed"),
    ("user-block-comment.jsonc", "failed"),
    ("user-trailing-commas.jsonc", "ok"),
    ("user-url.jsonc", "ok"),
])
def test_parser_parity_matrix(name, state):
    _, actual, _ = parse_with_parity((FIXTURES / name).read_bytes())
    assert actual == state


def test_invalid_utf8_is_rejected():
    document, diagnostics = parse_safe((FIXTURES / "user-invalid-utf8.bin").read_bytes())
    assert document is None and diagnostics[0]["code"] == "menu_unparseable"


def test_runtime_parser_hazard_and_duplicate_paths():
    _, state, diagnostics = parse_with_parity((FIXTURES / "user-comma-in-string.jsonc").read_bytes())
    assert state == "hazard" and diagnostics[0]["code"] == "menu_runtime_parser_hazard"
    document, diagnostics = parse_safe((FIXTURES / "user-duplicate-keys.jsonc").read_bytes())
    assert diagnostics == []
    assert [row["jsonPath"] for row in document["duplicates"]] == ["$.x.label", "$.x"]


def test_bom_is_a_runtime_parser_hazard():
    document, state, diagnostics = parse_with_parity((FIXTURES / "user-bom.jsonc").read_bytes())
    assert document is not None and document["bom"] is True
    runtime, _ = parse_runtime((FIXTURES / "user-bom.jsonc").read_bytes())
    assert runtime is None
    assert state == "hazard"
    assert diagnostics[-1]["code"] == "menu_runtime_parser_hazard"


def test_wrapper_and_javascript_key_order():
    document, diagnostics = parse_safe((FIXTURES / "user-items-wrapper.jsonc").read_bytes())
    assert diagnostics == [] and document["shape"] == "wrapper"
    assert document["wrapperSiblings"] == [{"key": "future", "value": {"keep": True}}]
    assert js_key_order(["zeta", "10", "alpha"]) == ["10", "zeta", "alpha"]
