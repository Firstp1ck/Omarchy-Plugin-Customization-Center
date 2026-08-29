from __future__ import annotations

import pytest


def binding(binding_id="b51ebad9-3854-4fd6-8904-d2986d9bd24c", kind="keysym", value="a", source="SUPER + A"):
    return {"id":binding_id,"enabled":True,"chord":{"sourceKeys":source,"modifiers":["SUPER"],"key":{"kind":kind,"value":value}},"flags":{"release":False}}


def record(**values):
    base = {"index":0,"domain":"keyboard","submap":"","identity":"64:keysym:a","modmask":64,"phase":"press","flags":{},"keyToken":"A","headerFlags":[]}
    base.update(values); return base


def categories(keybindings_backend, model, records, keymap=None):
    conflicts = __import__("cc_modules.keybindings.conflicts", fromlist=["conflicts"])
    return {item["category"]: item for item in conflicts.classify_conflicts(model, records, keymap or {})}


def test_exact_runtime_conflict_is_blocking(keybindings_backend):
    found = categories(keybindings_backend, {"bindings":[binding()],"disabled":[]}, [record()])
    assert found["exact_conflict"]["severity"] == "blocker"
    scoped = categories(keybindings_backend, {"bindings":[binding()],"disabled":[]},
                        [record(flags={"unknownLetters":["v"]})])
    assert scoped["device_scope_unknown"]["severity"] == "blocker"


def test_managed_runtime_row_is_not_an_external_conflict(keybindings_backend):
    item = binding()
    found = categories(keybindings_backend, {"bindings":[item],"disabled":[]}, [record(managedId=item["id"])])
    assert "exact_conflict" not in found


def test_exact_keycode_alias_is_blocking(keybindings_backend):
    item = binding(kind="code", value=10, source="SUPER + code:10")
    found = categories(keybindings_backend, {"bindings":[item],"disabled":[]},
                       [record(identity="64:keysym:1", keyToken="1")],
                       {"codeToKeysym":{"10":"1"},"layouts":[["us","",""]]})
    assert found["alias_conflict"]["severity"] == "blocker"


@pytest.mark.parametrize("branch", ["runtime", "draft"])
@pytest.mark.parametrize("difference", ["modifier", "phase"])
def test_alias_requires_equal_modifiers_and_phase(keybindings_backend, branch, difference):
    item = binding(kind="code", value=10, source="SUPER + code:10")
    other = binding("2f3b6d7c-0f4e-4a4d-9d1a-6f0a4d8f3c21", value="1", source="SUPER + 1")
    runtime = record(identity="64:keysym:1", keyToken="1")
    if difference == "modifier":
        other["chord"]["sourceKeys"] = "ALT + 1"
        other["chord"]["modifiers"] = ["ALT"]
        runtime.update(identity="8:keysym:1", modmask=8)
    else:
        other["flags"]["release"] = True
        runtime["phase"] = "release"
    model = {"bindings": [item, other] if branch == "draft" else [item], "disabled": []}
    records = [runtime] if branch == "runtime" else []
    found = categories(keybindings_backend, model, records,
                       {"codeToKeysym":{"10":"1"},"layouts":[["us","",""]]})
    assert "alias_conflict" not in found
    assert "possible_alias" not in found


def test_missing_keymap_alias_is_warning(keybindings_backend):
    item = binding(kind="code", value=10, source="SUPER + code:10")
    found = categories(keybindings_backend, {"bindings":[item],"disabled":[]}, [record(identity="64:keysym:1", keyToken="1")])
    assert found["possible_alias"]["severity"] == "warning"


def test_stack_phase_submap_wildcard_layout_and_missing_classes(keybindings_backend):
    item = binding(value="comma", source="SUPER + comma")
    records = [record(index=0, identity="64:keysym:comma", phase="release"),
               record(index=1, identity="64:keysym:comma", submap="resize"),
               record(index=2, identity="1:keysym:x", catchall=True)]
    model = {"bindings":[item],"disabled":[{"id":"d","target":{"identity":"missing","kind":"managed"}}]}
    found = categories(keybindings_backend, model, records, {"layouts":[["us","",""],["ch","",""]]})
    assert {"phase_pair", "submap_shadow", "wildcard_overlap", "layout_dependent", "unbind_target_missing"} <= set(found)


def test_draft_duplicate_shifted_digit_and_stack_collateral(keybindings_backend):
    one = binding(); two = binding("2f3b6d7c-0f4e-4a4d-9d1a-6f0a4d8f3c21")
    shifted = binding("8b56c5e2-2dce-4d27-9681-7d47d6a3f6ee", value="1", source="SUPER + SHIFT + 1"); shifted["chord"]["modifiers"]=["SUPER","SHIFT"]
    model={"bindings":[one,two,shifted],"disabled":[{"id":"d","target":{"identity":"64:keysym:z","kind":"omarchy_default"}}]}
    rows=[record(index=4,identity="64:keysym:z"),record(index=5,identity="64:keysym:z")]
    found=categories(keybindings_backend,model,rows)
    assert {"draft_duplicate","shifted_digit","stack_collateral"} <= set(found)
