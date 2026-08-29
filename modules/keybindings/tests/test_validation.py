import copy
from types import SimpleNamespace

import pytest

from customization_center.core import CommandResult, Paths, Status


def base_binding():
    return {"id":"b51ebad9-3854-4fd6-8904-d2986d9bd24c","enabled":True,"chord":{"sourceKeys":"SUPER + A","modifiers":["SUPER"],"key":{"kind":"keysym","value":"a"}},"description":"Alpha","action":{"type":"exec","command":"true","catalogId":None},"flags":{"locked":False,"release":False,"repeating":False,"nonConsuming":False,"autoConsuming":False,"bypass":False}}


def disable(source="SUPER + A", description="Alpha", module="", identity="64:keysym:a", kind="managed"):
    return {"id":"2f3b6d7c-0f4e-4a4d-9d1a-6f0a4d8f3c21","sourceKeys":source,"target":{"kind":kind,"module":module,"description":description,"identity":identity},"reason":"disabled","replacedBy":None}


def status(model=None, catalog=None, records=None, keymap=None):
    return Status("keybindings","r",{"model":model or {"schemaVersion":1,"bindings":[],"disabled":[]},"catalogEntries":catalog or [],"records":records or [],"keymapContext":keymap or {},"managedBlock":{"state":"absent","drift":False}},(),1)


@pytest.mark.parametrize("case, expected", [
    ("grammar", "keybindings_chord_grammar"),
    ("modifier", "keybindings_unsupported_modifier"),
    ("key", "keybindings_unsupported_key"),
    ("keysym", "keybindings_unknown_keysym"),
    ("duplicate", "keybindings_draft_duplicate"),
    ("control", "keybindings_control_character"),
    ("flags", "keybindings_flag_combination"),
    ("replacement", "keybindings_unbind_target_missing"),
    ("unicode", "keybindings_invalid_unicode"),
])
def test_model_validation_codes_are_emitted(keybindings_backend, case, expected):
    model_module=__import__("cc_modules.keybindings.model",fromlist=["model"])
    item=base_binding(); bindings=[item]; disabled=[]
    if case == "grammar": item["chord"]["sourceKeys"]="SUPER + B"
    elif case == "modifier": item["chord"]["modifiers"]=["CAPS"]
    elif case == "key": item["chord"]["key"]={"kind":"keysym","value":"mouse:272"}
    elif case == "keysym": item["chord"]["key"]={"kind":"keysym","value":"DefinitelyNotAKeysym"}
    elif case == "duplicate": bindings.append(copy.deepcopy(item)); bindings[1]["id"]="2f3b6d7c-0f4e-4a4d-9d1a-6f0a4d8f3c21"
    elif case == "control": item["description"]="bad\x01description"
    elif case == "flags": item["flags"]["nonConsuming"]=True; item["flags"]["autoConsuming"]=True
    elif case == "replacement": disabled.append(disable()); disabled[0]["replacedBy"]="8b56c5e2-2dce-4d27-9681-7d47d6a3f6ee"
    elif case == "unicode": item["action"]["command"]="bad\ud800"
    draft={"schemaVersion":1,"expectedRevision":"r","model":{"schemaVersion":1,"bindings":bindings,"disabled":disabled}}
    issues, _, _=model_module.validate_draft(draft)
    assert expected in {issue.code for issue in issues}


@pytest.mark.parametrize("case, expected_code, expected_severity", [
    ("grammar", "keybindings_chord_grammar", "error"),
    ("modifier", "keybindings_unsupported_modifier", "error"),
    ("key", "keybindings_unsupported_key", "error"),
    ("keysym", "keybindings_unknown_keysym", "error"),
    ("duplicate", "keybindings_draft_duplicate", "error"),
    ("control", "keybindings_control_character", "error"),
    ("flags", "keybindings_flag_combination", "error"),
    ("replacement", "keybindings_unbind_target_missing", "error"),
    ("unicode", "keybindings_invalid_unicode", "error"),
    ("unknown_target", "keybindings_unknown_unbind_target", "error"),
    ("alias_blocker", "keybindings_alias_conflict", "error"),
    ("exact_blocker", "keybindings_exact_conflict", "error"),
    ("scope_blocker", "keybindings_device_scope_unknown", "error"),
    ("missing_blocker", "keybindings_unbind_target_missing", "error"),
    ("no_luac", "keybindings_no_lua_check", "warning"),
    ("lua_syntax", "keybindings_lua_syntax", "error"),
])
def test_public_validate_issue_codes_and_severities(keybindings_backend, tmp_path, case, expected_code, expected_severity):
    planner = __import__("cc_modules.keybindings.planner", fromlist=["planner"])
    item = base_binding(); bindings = [item]; disabled = []; current_status = status()
    if case == "grammar": item["chord"]["sourceKeys"] = "SUPER + B"
    elif case == "modifier": item["chord"]["modifiers"] = ["CAPS"]
    elif case == "key": item["chord"]["key"] = {"kind":"keysym","value":"mouse:272"}
    elif case == "keysym": item["chord"]["key"] = {"kind":"keysym","value":"DefinitelyNotAKeysym"}
    elif case == "duplicate":
        bindings.append(copy.deepcopy(item)); bindings[1]["id"] = "8b56c5e2-2dce-4d27-9681-7d47d6a3f6ee"
    elif case == "control": item["description"] = "bad\x01description"
    elif case == "flags": item["flags"]["nonConsuming"] = True; item["flags"]["autoConsuming"] = True
    elif case == "replacement":
        disabled.append(disable()); disabled[0]["replacedBy"] = "8b56c5e2-2dce-4d27-9681-7d47d6a3f6ee"
    elif case == "unicode": item["action"]["command"] = "bad\ud800"
    elif case in {"unknown_target", "missing_blocker"}:
        bindings = []; disabled = [disable()]
        if case == "missing_blocker": current_status = status({"schemaVersion":1,"bindings":[base_binding()],"disabled":[]})
    elif case == "alias_blocker":
        item["chord"] = {"sourceKeys":"SUPER + code:10","modifiers":["SUPER"],"key":{"kind":"code","value":10}}
        runtime = {"index":0,"domain":"keyboard","submap":"","identity":"64:keysym:1","modmask":64,"phase":"press","flags":{},"keyToken":"1"}
        current_status = status(records=[runtime], keymap={"codeToKeysym":{"10":"1"},"layouts":[["us","",""]]})
    elif case in {"exact_blocker", "scope_blocker"}:
        runtime_flags = {"unknownLetters":["v"]} if case == "scope_blocker" else {}
        runtime = {"index":0,"domain":"keyboard","submap":"","identity":"64:keysym:a","modmask":64,"phase":"press","flags":runtime_flags,"keyToken":"A"}
        current_status = status(records=[runtime])
    elif case in {"no_luac", "lua_syntax"}:
        bindings = []
    draft = {"schemaVersion":1,"expectedRevision":"r","model":{"schemaVersion":1,"bindings":bindings,"disabled":disabled}}

    home = tmp_path / "home"; config = home / ".config"; (config / "hypr").mkdir(parents=True)
    (config / "hypr/bindings.lua").write_text("-- user\n")
    paths = Paths(home, config, tmp_path / "state", tmp_path / "cache", tmp_path / "runtime", tmp_path / "omarchy")
    class Commands:
        def which(self, name): return "/stub/luac" if name == "luac" and case == "lua_syntax" else None
        def run(self, argv, **kwargs):
            return CommandResult(tuple(argv), 1, "", "bindings.lua:1: syntax error", False, 1, False)
    result = planner.validate(SimpleNamespace(paths=paths, commands=Commands()), draft, current_status)
    assert (expected_code, expected_severity) in {(issue.code, issue.severity) for issue in result.issues}
    assert result.ok is (expected_severity == "warning")


def test_validate_reports_no_lua_check_warning(keybindings_backend, tmp_path):
    planner=__import__("cc_modules.keybindings.planner",fromlist=["planner"])
    home=tmp_path/"home"; (home/".config/hypr").mkdir(parents=True)
    paths=SimpleNamespace(home=home,xdg_config_home=home/".config")
    commands=SimpleNamespace(which=lambda name: None)
    draft={"schemaVersion":1,"expectedRevision":"r","model":{"schemaVersion":1,"bindings":[],"disabled":[]}}
    result=planner.validate(SimpleNamespace(paths=paths,commands=commands),draft,status())
    assert result.ok
    assert any(issue.code=="keybindings_no_lua_check" and issue.severity=="warning" for issue in result.issues)


def test_exact_managed_unbind_target_is_valid(keybindings_backend):
    planner=__import__("cc_modules.keybindings.planner",fromlist=["planner"]); item=base_binding()
    draft={"schemaVersion":1,"expectedRevision":"r","model":{"schemaVersion":1,"bindings":[],"disabled":[disable()]}}
    result=planner._pure_validation(draft,status({"schemaVersion":1,"bindings":[item],"disabled":[]}, records=[{"index":0,"identity":"64:keysym:a"}]))
    assert result.ok


def test_forged_unbind_target_is_rejected(keybindings_backend):
    planner=__import__("cc_modules.keybindings.planner",fromlist=["planner"]); item=base_binding()
    draft={"schemaVersion":1,"expectedRevision":"r","model":{"schemaVersion":1,"bindings":[],"disabled":[disable(description="Forged")]}}
    result=planner._pure_validation(draft,status({"schemaVersion":1,"bindings":[item],"disabled":[]}))
    assert not result.ok
    assert any(issue.code=="keybindings_unknown_unbind_target" for issue in result.issues)


def test_exact_catalog_unbind_requires_source_module_description_and_identity(keybindings_backend):
    planner=__import__("cc_modules.keybindings.planner",fromlist=["planner"])
    catalog=[{"keys":"SUPER + SPACE","module":"utilities","description":"Omarchy menu","identity":"64:keysym:space"}]
    good=disable("SUPER + SPACE","Omarchy menu","utilities","64:keysym:space","omarchy_default")
    draft={"schemaVersion":1,"expectedRevision":"r","model":{"schemaVersion":1,"bindings":[],"disabled":[good]}}
    assert planner._pure_validation(draft,status(catalog=catalog)).ok
    good["sourceKeys"]="SUPER + space"
    assert any(issue.code=="keybindings_unknown_unbind_target" for issue in planner._pure_validation(draft,status(catalog=catalog)).issues)
