import copy
import json
from pathlib import Path

from customization_center.core import managed_block


def binding():
    return {"id":"b51ebad9-3854-4fd6-8904-d2986d9bd24c","enabled":True,"chord":{"sourceKeys":"SUPER + SHIFT + R","modifiers":["SUPER","SHIFT"],"key":{"kind":"keysym","value":"r"}},"description":"Open project terminal","action":{"type":"exec","command":"xdg-terminal-exec","catalogId":None},"flags":{"locked":False,"release":False,"repeating":False,"nonConsuming":False,"autoConsuming":False,"bypass":False}}


def test_model_validation_and_render(keybindings_backend):
    model = __import__("cc_modules.keybindings.model", fromlist=["model"])
    render = __import__("cc_modules.keybindings.render", fromlist=["render"])
    draft = {"schemaVersion":1,"expectedRevision":"x","model":{"schemaVersion":1,"bindings":[binding()],"disabled":[]}}
    issues, normalized, body = model.validate_draft(draft)
    assert not issues and normalized
    assert 'o.bind("SUPER + SHIFT + R"' in body
    assert render.lua_string('a"\\é') == '"a\\"\\\\\\195\\169"'


def test_distinct_add_replace_disable_and_empty_goldens(keybindings_backend):
    render = __import__("cc_modules.keybindings.render", fromlist=["render"])
    fixtures = Path(__file__).parent / "fixtures"
    add_item = binding(); add_item["description"] = "Open terminal"
    add_model = {"schemaVersion":1,"bindings":[add_item],"disabled":[]}
    disable = {"id":"2f3b6d7c-0f4e-4a4d-9d1a-6f0a4d8f3c21","sourceKeys":"SUPER + SPACE","target":{"kind":"omarchy_default","module":"utilities","description":"Omarchy menu","identity":"64:keysym:space"},"reason":"disabled","replacedBy":None}
    disable_model = {"schemaVersion":1,"bindings":[],"disabled":[disable]}
    replace_model = json.loads((fixtures / "model/v1-full.json").read_text())
    assert (render.render_body(add_model) + "\n").encode() == (fixtures / "render/add.lua").read_bytes()
    assert (render.render_body(disable_model) + "\n").encode() == (fixtures / "render/disable.lua").read_bytes()
    assert (render.render_body(replace_model) + "\n").encode() == (fixtures / "render/replace.lua").read_bytes()
    assert render.render_body({"schemaVersion":1,"bindings":[],"disabled":[]}) is None
    assert (fixtures / "render/empty.lua").read_bytes() == b""


def test_empty_model_removes_whole_block_byte_identically(keybindings_backend):
    render = __import__("cc_modules.keybindings.render", fromlist=["render"])
    fixtures = Path(__file__).parent / "fixtures"
    original = (fixtures / "bindings/stock.lua").read_bytes()
    with_block = managed_block.replace(original, "BINDINGS", 1, render.render_body({"schemaVersion":1,"bindings":[binding()],"disabled":[]}), "--")
    assert managed_block.replace(with_block, "BINDINGS", 1, None, "--") == original


def test_bad_flags(keybindings_backend):
    model = __import__("cc_modules.keybindings.model", fromlist=["model"])
    item = binding(); item["flags"]["nonConsuming"] = True; item["flags"]["autoConsuming"] = True
    draft = {"schemaVersion":1,"expectedRevision":"x","model":{"schemaVersion":1,"bindings":[item],"disabled":[]}}
    issues, _, _ = model.validate_draft(draft)
    assert any(issue.code == "keybindings_flag_combination" for issue in issues)
