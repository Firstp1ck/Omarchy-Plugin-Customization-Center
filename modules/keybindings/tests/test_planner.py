from pathlib import Path
from types import SimpleNamespace

from customization_center.core import Operation, Plan, Status


def binding():
    return {"id":"b51ebad9-3854-4fd6-8904-d2986d9bd24c","enabled":True,"chord":{"sourceKeys":"SUPER + A","modifiers":["SUPER"],"key":{"kind":"keysym","value":"a"}},"description":"Alpha","action":{"type":"exec","command":"true","catalogId":None},"flags":{"locked":False,"release":False,"repeating":False,"nonConsuming":False,"autoConsuming":False,"bypass":False}}


class Commands:
    def which(self, name): return "/stub/" + name


def context(tmp_path):
    home=tmp_path/"home"; config=home/".config"; (config/"hypr").mkdir(parents=True); (config/"hypr/bindings.lua").write_text("-- user\n")
    paths=SimpleNamespace(home=home,xdg_config_home=config)
    return SimpleNamespace(paths=paths,commands=Commands(),cache={},module_id="keybindings")


def status(model=None, drift=False):
    value=model or {"schemaVersion":1,"bindings":[],"disabled":[]}
    return Status("keybindings","r",{"model":value,"records":[],"catalogEntries":[],"keymapContext":{},"managedBlock":{"state":"absent","drift":drift}},(),1)


def test_query_normalizes_with_active_keymap(keybindings_backend):
    planner = __import__("cc_modules.keybindings.planner", fromlist=["planner"])
    result=planner.normalize_query("SUPER + code:10",{"codeToKeysym":{"10":"1"},"layouts":[["us","",""]]})
    assert result["findings"] == [{"category":"keycode_alias","keysym":"1","confidence":"exact_current_keymap"}]


def test_plan_operation_order_inverses_and_backups(keybindings_backend,tmp_path):
    planner=__import__("cc_modules.keybindings.planner",fromlist=["planner"]); ctx=context(tmp_path)
    draft={"schemaVersion":1,"expectedRevision":"r","model":{"schemaVersion":1,"bindings":[binding()],"disabled":[]}}
    plan=planner.build_plan(ctx,draft,status())
    assert [operation.kind for operation in plan.operations] == ["WriteFileAtomic","ReplaceManagedBlock","HyprctlReload"]
    assert all(operation.inverse is not None for operation in plan.operations)
    assert plan.operations[0].backup_paths == (str((ctx.paths.xdg_config_home/"omarchy/customization-center/keybindings.json").absolute()),)
    assert plan.operations[1].backup_paths == (str((ctx.paths.home/".config/hypr/bindings.lua").absolute()),)


def test_forget_recovery_only_removes_model_record(keybindings_backend,tmp_path):
    planner=__import__("cc_modules.keybindings.planner",fromlist=["planner"]); ctx=context(tmp_path)
    draft={"schemaVersion":1,"expectedRevision":"r","model":{"schemaVersion":1,"bindings":[],"disabled":[]},"recoveryAction":"forget"}
    plan=planner.build_plan(ctx,draft,status(drift=True))
    assert [operation.kind for operation in plan.operations] == ["RemoveFile"]
    assert plan.operations[0].params["path"].endswith("keybindings.json")


def test_empty_model_removes_managed_block(keybindings_backend,tmp_path):
    planner=__import__("cc_modules.keybindings.planner",fromlist=["planner"]); ctx=context(tmp_path)
    old={"schemaVersion":1,"bindings":[binding()],"disabled":[]}
    draft={"schemaVersion":1,"expectedRevision":"r","model":{"schemaVersion":1,"bindings":[],"disabled":[]}}
    plan=planner.build_plan(ctx,draft,status(old,True))
    assert plan.operations[1].params["body"] is None


def test_verify_selects_keybinding_detail_in_composed_plan(keybindings_backend, tmp_path):
    planner=__import__("cc_modules.keybindings.planner",fromlist=["planner"]); ctx=context(tmp_path)
    monitor = Operation("monitors.0001", "monitors", "WriteFileAtomic", {}, "Monitor first", (), (), detail={"profileId": "desk"})
    keybinding = Operation("keybindings.0001", "keybindings", "WriteFileAtomic", {}, "Keybindings", (), (),
                           detail={"blockState": "absent", "expectedPresent": [], "expectedAbsent": []})
    plan = Plan("modes", "modes-r", (monitor, keybinding), (), "Composed", (), ())
    result = planner.verify(ctx, plan, status(), {})
    assert result.state == "pass"


def test_verify_accepts_empty_keybindings_segment_in_composed_plan(keybindings_backend, tmp_path):
    planner=__import__("cc_modules.keybindings.planner",fromlist=["planner"]); ctx=context(tmp_path)
    monitor = Operation("monitors.0001", "monitors", "WriteFileAtomic", {}, "Monitor first", (), (), detail={"profileId": "desk"})
    plan = Plan("modes", "modes-r", (monitor,), (), "Composed", (), ())
    result = planner.verify(ctx, plan, status(), {})
    assert result.state == "pass"
