from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from customization_center.core import Capabilities, Capability, OperationResult, Plan, Status, ops
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = json.loads((Path(__file__).parent / "fixtures/sample-draft.json").read_text())
INVENTORY_TEXT = (Path(__file__).parent / "fixtures/hyprctl/laptop-only.json").read_text()


class Clock:
    def __init__(self): self.ticks = 0.0; self.sleeps = []
    def now(self): return datetime(2026, 1, 1, tzinfo=timezone.utc)
    def now_iso(self): return "2026-01-01T00:00:00Z"
    def monotonic(self): return self.ticks
    def sleep(self, seconds): self.sleeps.append(seconds); self.ticks += seconds


class Commands:
    def __init__(self, *, luac=True, luac_code=0): self.luac = luac; self.luac_code = luac_code; self.calls = []; self.environ = {"HYPRLAND_INSTANCE_SIGNATURE":"test", "XDG_RUNTIME_DIR":"/tmp/run"}
    def allow_readonly(self, prefix): pass
    def which(self, name): return "/usr/bin/" + name if name != "luac" or self.luac else None
    def run(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return SimpleNamespace(exit_code=self.luac_code, timed_out=False, stdout="", stderr="syntax error" if self.luac_code else "")


class Journal:
    def __init__(self, records=()): self.records = list(records)
    def history(self, module=None, limit=50, state=None): return self.records


@pytest.fixture
def backend():
    load_registry(ROOT, paths=Paths.from_env())
    return {name: importlib.import_module(f"cc_modules.monitors.{name}") for name in ("planner", "inventory", "lua_render", "ownership", "profile")}


def context(tmp_path, monkeypatch, commands=None, journal=None):
    home = tmp_path / "home"; xdg = tmp_path / "xdg"; state = tmp_path / "state"; cache = tmp_path / "cache"; runtime = tmp_path / "runtime"
    for item in (home, xdg, state, cache, runtime): item.mkdir(parents=True, exist_ok=True)
    env = {"HOME":str(home), "XDG_CONFIG_HOME":str(xdg), "XDG_STATE_HOME":str(state), "XDG_CACHE_HOME":str(cache), "XDG_RUNTIME_DIR":str(runtime)}
    paths = Paths.from_env(env)
    caps = Capabilities("monitors", (Capability("hyprctl", True, ""), Capability("timed_confirmation", True, ""), Capability("monitor_inventory", True, ""), Capability("hyprland_session", True, ""), Capability("luac", bool(commands.luac) if commands else True, "")), "now")
    return SimpleNamespace(paths=paths, capabilities=caps, commands=commands or Commands(), cache={}, module_id="monitors", clock=Clock(), journal=journal or Journal(), revision_of=lambda data: __import__("hashlib").sha256(json.dumps(data,sort_keys=True,separators=(",",":")).encode()).hexdigest())


def status_for(backend, ctx, profile_value=None):
    outputs, _ = backend["inventory"].parse_inventory(INVENTORY_TEXT)
    value = profile_value or SAMPLE["profile"]
    return Status("monitors", "revision", {"schemaVersion":1, "inventory":{"outputs":outputs,"error":None},
        "profiles":[{"id":value["id"],"profile":value}], "active":{"profileId":None,"state":"none"},
        "loader":{"state":"absent"}, "handwritten":{"conflicts":[]},
        "toggles":{"internal-monitor-disable":None,"internal-monitor-mirror":None,"internal-monitor-clamshell":None}}, (), 1)


def test_home_and_xdg_paths_are_distinct(backend, tmp_path, monkeypatch):
    ctx = context(tmp_path, monkeypatch)
    paths = backend["planner"]._paths(ctx)
    assert paths["host"] == ctx.paths.home / ".config/hypr/monitors.lua"
    assert paths["profiles"] == ctx.paths.module_config("monitors") / "monitor-profiles"
    assert paths["active"] == ctx.paths.module_state("monitors") / "active.json"


def test_fresh_activation_exact_sequence_and_rule_bytes(backend, tmp_path, monkeypatch):
    ctx = context(tmp_path, monkeypatch); module = backend["planner"].MODULE; status = status_for(backend, ctx)
    draft = {"schemaVersion":1,"action":"activate","profileId":"laptop","profile":None,"assignments":{"laptop":"eDP-1"},"acknowledgedWarnings":[]}
    plan = module.plan(ctx, draft, status)
    assert [item.kind for item in plan.operations] == ["EnsureDirectory","WriteFileAtomic","ReplaceManagedBlock","WriteFileAtomic","RunCommand","HyprctlReload","TimedConfirmation","WriteFileAtomic","WriteFileAtomic"]
    fixture_root = Path(__file__).parent / "fixtures"
    assert plan.operations[3].params["content"].encode() == (fixture_root / "rules-guarded.lua").read_bytes()
    assert plan.operations[7].params["content"].encode() == (fixture_root / "rules-unguarded.lua").read_bytes()
    assert plan.operations[4].params["argv"] == ["hyprctl","dispatch",'hl.dsp.dpms({ action = "enable" })']
    assert plan.operations[5].kind == "HyprctlReload" and plan.operations[6].params["seconds"] == 30


def test_every_action_operation_sequence(backend, tmp_path, monkeypatch):
    module = backend["planner"].MODULE
    cases = [
        ({"schemaVersion":1,"action":"save-profile","profile":SAMPLE["profile"]}, ["WriteFileAtomic"]),
        ({"schemaVersion":1,"action":"delete-profile","profileId":"laptop"}, ["RemoveFile"]),
        ({"schemaVersion":1,"action":"clear-override","override":"internal-monitor-disable"}, ["RunCommand"]),
        ({"schemaVersion":1,"action":"install-loader"}, ["EnsureDirectory","WriteFileAtomic","ReplaceManagedBlock","HyprctlReload"]),
    ]
    for index, (draft, expected) in enumerate(cases):
        ctx = context(tmp_path / str(index), monkeypatch); status = status_for(backend, ctx)
        plan = module.plan(ctx, draft, status)
        assert [item.kind for item in plan.operations] == expected


def test_inline_profile_is_saved_before_loader(backend, tmp_path, monkeypatch):
    ctx = context(tmp_path, monkeypatch); status = status_for(backend, ctx)
    draft = {"schemaVersion":1,"action":"activate","profileId":"laptop","profile":SAMPLE["profile"],"assignments":{"laptop":"eDP-1"}}
    plan = backend["planner"].MODULE.plan(ctx, draft, status)
    kinds = [item.kind for item in plan.operations]
    assert kinds[:5] == ["EnsureDirectory","WriteFileAtomic","EnsureDirectory","WriteFileAtomic","ReplaceManagedBlock"]
    assert plan.operations[3].params["content"] == backend["profile"].canonical(SAMPLE["profile"])


def test_validate_luac_and_missing_warning(backend, tmp_path, monkeypatch):
    draft = {"schemaVersion":1,"action":"activate","profileId":"laptop","profile":SAMPLE["profile"],"assignments":{"laptop":"eDP-1"}}
    commands = Commands(luac=True); ctx = context(tmp_path, monkeypatch, commands); status = status_for(backend, ctx)
    result = backend["planner"].MODULE.validate(ctx, draft, status)
    assert result.ok and commands.calls[0][0] == ["luac","-p","-"] and "stdin" in commands.calls[0][1]
    missing = Commands(luac=False); missing_ctx = context(tmp_path / "other", monkeypatch, missing)
    result = backend["planner"].MODULE.validate(missing_ctx, draft, status_for(backend, missing_ctx))
    assert result.ok and any(item.code == "monitors_no_lua_check" and item.severity == "warning" for item in result.issues)


def test_activation_plan_reuses_bounded_normalized_time_context(backend, tmp_path, monkeypatch):
    module = backend["planner"].MODULE
    draft = {"schemaVersion":1,"action":"activate","profileId":"laptop","profile":SAMPLE["profile"],"assignments":{"laptop":"eDP-1"}}
    validate_ctx = context(tmp_path / "validate", monkeypatch)
    validate_ctx.clock = SimpleNamespace(
        now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        now_iso=lambda: pytest.fail("activation context must use the same clock reading"))
    status = status_for(backend, validate_ctx)
    validation = module.validate(validate_ctx, draft, status)
    assert validation.ok
    normalized = validation.normalized_draft
    assert normalized["_planContext"] == {"confirmBy": 1767225780, "appliedAt": "2026-01-01T00:00:00Z"}

    first_ctx = context(tmp_path / "plan", monkeypatch)
    later_ctx = context(tmp_path / "plan", monkeypatch)
    later_ctx.clock = SimpleNamespace(
        now=lambda: datetime(2036, 1, 1, tzinfo=timezone.utc),
        now_iso=lambda: "2036-01-01T00:00:00Z")
    first = module.plan(first_ctx, normalized, status_for(backend, first_ctx))
    second = module.plan(later_ctx, normalized, status_for(backend, later_ctx))
    assert first == second
    active = json.loads(first.operations[-1].params["content"])
    assert active["appliedAt"] == normalized["_planContext"]["appliedAt"]

    invalid_contexts = [
        {**normalized["_planContext"], "confirmBy": normalized["_planContext"]["confirmBy"] + 1},
        {"confirmBy": 1767225659, "appliedAt": "2025-12-31T23:57:59Z"},
        {"confirmBy": 1767225780, "appliedAt": "not-an-iso-timestamp"},
    ]
    for plan_context in invalid_contexts:
        malformed = json.loads(json.dumps(normalized)); malformed["_planContext"] = plan_context
        rejected = module.validate(validate_ctx, malformed, status)
        assert not rejected.ok and any(item.pointer == "/_planContext" for item in rejected.issues)


def test_status_persists_live_modes_and_exposes_cached_modes_only_when_disconnected(backend, tmp_path, monkeypatch):
    ctx = context(tmp_path, monkeypatch); module = backend["planner"].MODULE
    profile_path = backend["planner"]._paths(ctx)["profiles"] / "laptop.json"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(backend["profile"].canonical(SAMPLE["profile"]))
    outputs, _ = backend["inventory"].parse_inventory(INVENTORY_TEXT)
    monkeypatch.setattr(backend["planner"].inventory, "read", lambda unused, timeout_s=3: (outputs, ()))

    live = module.status(ctx)
    cache_path = ctx.paths.cache / "monitor-inventory.json"
    cached = json.loads(cache_path.read_text())
    assert set(cached) == {"observedAt", "outputs"}
    assert cached["outputs"] == [{"identity": backend["planner"]._cache_identity(outputs[0]),
                                   "modes": outputs[0]["modes"]}]
    assert live.data["cachedModes"] == []
    assert not any(item.code == "monitors_stale_modes" for item in live.warnings)

    monkeypatch.setattr(backend["planner"].inventory, "read", lambda unused, timeout_s=3: ([], ()))
    disconnected = module.status(ctx)
    assert disconnected.data["cachedModes"] == [{"profileId": "laptop", "outputId": "laptop",
        "identity": cached["outputs"][0]["identity"], "modes": outputs[0]["modes"],
        "observedAt": cached["observedAt"], "stale": True}]
    assert any(item.code == "monitors_stale_modes" for item in disconnected.warnings)
    draft = {"schemaVersion":1,"action":"activate","profileId":"laptop","profile":None,"assignments":{}}
    assert module._render_for_validation(draft, disconnected) is None
    with pytest.raises(Exception) as caught:
        module.plan(ctx, draft, disconnected)
    assert caught.value.code == "monitors_output_missing"


def test_revision_changes_for_every_identity_mode_geometry_and_toggle_field(backend, tmp_path, monkeypatch):
    ctx = context(tmp_path, monkeypatch); module = backend["planner"].MODULE
    outputs, _ = backend["inventory"].parse_inventory(INVENTORY_TEXT)
    monkeypatch.setattr(backend["planner"].inventory, "read", lambda unused, timeout_s=3: (outputs, ()))
    baseline = module.status(ctx).revision
    mutations = []
    for field in ("make", "model", "serial", "description"):
        sample = json.loads(json.dumps(outputs)); sample[0][field] += " changed"; mutations.append(sample)
    sample = json.loads(json.dumps(outputs)); sample[0]["modes"].append({"width":1280,"height":720,"refreshMilliHz":60000}); mutations.append(sample)
    for field in ("x", "y", "width", "height", "scale120", "transform"):
        sample = json.loads(json.dumps(outputs)); sample[0][field] += 1; mutations.append(sample)
    for sample in mutations:
        monkeypatch.setattr(backend["planner"].inventory, "read", lambda unused, timeout_s=3, sample=sample: (sample, ()))
        assert module.status(ctx).revision != baseline, field

    monkeypatch.setattr(backend["planner"].inventory, "read", lambda unused, timeout_s=3: (outputs, ()))
    toggle_dir = ctx.paths.home / ".local/state/omarchy/toggles/hypr"; toggle_dir.mkdir(parents=True)
    disable = toggle_dir / "internal-monitor-disable.lua"; disable.write_text('hl.monitor({ output = "eDP-1", disabled = true })\n')
    first = module.status(ctx).revision
    disable.rename(toggle_dir / "internal-monitor-clamshell.lua")
    renamed = module.status(ctx).revision
    assert renamed != first
    (toggle_dir / "internal-monitor-clamshell.lua").write_text('hl.monitor({ output = "eDP-2", disabled = true })\n')
    assert module.status(ctx).revision != renamed


def test_profile_warning_and_required_reference_matrix(backend):
    profile_module = backend["profile"]; planner = backend["planner"]
    missing = json.loads(json.dumps(SAMPLE["profile"])); missing["match"]["required"] = ["missing"]
    assert any(item.pointer.endswith("/match/required/0") for item in profile_module.validate_profile(missing))
    gap = json.loads(json.dumps(SAMPLE["profile"])); second = json.loads(json.dumps(gap["outputs"][0])); second["id"]="second"; second["position"]={"x":2000,"y":0}; gap["outputs"].append(second)
    assert any(item.code == "monitors_layout_gap" for item in planner._profile_warnings(gap))
    mirror = json.loads(json.dumps(SAMPLE["profile"])); second=json.loads(json.dumps(mirror["outputs"][0])); second["id"]="mirror"; second["mirrorOf"]="laptop"; second["mode"]={"width":1920,"height":1080,"refreshMilliHz":60000}; mirror["outputs"].append(second)
    codes={item.code for item in planner._profile_warnings(mirror)}
    assert {"monitors_mirror_aspect","monitors_mirror_mode_differs"} <= codes


def test_validation_code_matrix_static_rules(backend):
    validator = backend["profile"].validate_profile
    cases = []
    no_root = json.loads(json.dumps(SAMPLE["profile"])); no_root["outputs"][0]["enabled"] = False; cases.append((no_root, "monitors_no_root"))
    overlap = json.loads(json.dumps(SAMPLE["profile"])); second=json.loads(json.dumps(overlap["outputs"][0])); second["id"]="second"; overlap["outputs"].append(second); cases.append((overlap,"monitors_overlap"))
    invalid_scale = json.loads(json.dumps(SAMPLE["profile"])); invalid_scale["outputs"][0]["scale120"] = 168; cases.append((invalid_scale,"monitors_invalid_scale"))
    mirror = json.loads(json.dumps(SAMPLE["profile"])); mirror["outputs"][0]["mirrorOf"] = "laptop"; cases.append((mirror,"monitors_mirror_invalid"))
    hostile = json.loads(json.dumps(SAMPLE["profile"])); hostile["outputs"][0]["identity"]["connector"] = 'DP-1"bad'; cases.append((hostile,"monitors_unsupported_output_name"))
    unknown = json.loads(json.dumps(SAMPLE["profile"])); unknown["unknown"] = True; cases.append((unknown,"validation_failed"))
    for value, code in cases:
        assert code in {item.code for item in validator(value)}, code


def test_validation_code_matrix_runtime_rules(backend, tmp_path, monkeypatch):
    module = backend["planner"].MODULE
    def activate(ctx, status, value, assignments=None):
        return module.plan(ctx, {"schemaVersion":1,"action":"activate","profileId":value["id"],"profile":value,"assignments":assignments or {}}, status)
    ctx = context(tmp_path, monkeypatch); status = status_for(backend, ctx)
    unavailable = json.loads(json.dumps(SAMPLE["profile"])); unavailable["outputs"][0]["mode"]["width"] = 1000
    with pytest.raises(Exception) as caught: activate(ctx,status,unavailable,{"laptop":"eDP-1"})
    assert caught.value.code == "monitors_mode_unavailable"
    missing_status = status_for(backend,ctx); missing_status.data["inventory"]["outputs"] = []
    with pytest.raises(Exception) as caught: activate(ctx,missing_status,SAMPLE["profile"])
    assert caught.value.code == "monitors_output_missing"
    extra_status = status_for(backend,ctx); extra=json.loads(json.dumps(extra_status.data["inventory"]["outputs"][0])); extra["connector"]="DP-2"; extra["serial"]="2"; extra_status.data["inventory"]["outputs"].append(extra)
    with pytest.raises(Exception) as caught: activate(ctx,extra_status,SAMPLE["profile"],{"laptop":"eDP-1"})
    assert caught.value.code == "monitors_unexpected_output"
    toggle_status = status_for(backend,ctx); toggle_status.data["toggles"]["internal-monitor-disable"]={"state":"known","path":"toggle.lua","connectors":["eDP-1"]}
    with pytest.raises(Exception) as caught: activate(ctx,toggle_status,SAMPLE["profile"],{"laptop":"eDP-1"})
    assert caught.value.code == "monitors_toggle_override"

    duplicate, _ = backend["inventory"].parse_inventory((Path(__file__).parent / "fixtures/hyprctl/duplicate-description.json").read_text())
    ambiguous_profile = json.loads(json.dumps(SAMPLE["profile"])); ambiguous_profile["outputs"] = []
    for output_id in ("left", "right"):
        rule = json.loads(json.dumps(SAMPLE["profile"]["outputs"][0])); rule["id"] = output_id
        rule["identity"] = {"description":"Same Panel SAME","make":"Acme","model":"Panel","serial":"SAME","connector":"HDMI-A-9"}
        ambiguous_profile["outputs"].append(rule)
    ambiguous_profile["match"]["required"] = ["left", "right"]
    ambiguous_status = status_for(backend,ctx,ambiguous_profile); ambiguous_status.data["inventory"]["outputs"] = duplicate
    with pytest.raises(Exception) as caught: activate(ctx,ambiguous_status,ambiguous_profile)
    assert caught.value.code == "monitors_ambiguous_identity"

    hostile_status = status_for(backend,ctx); hostile = json.loads(json.dumps(hostile_status.data["inventory"]["outputs"][0])); hostile["connector"] = 'DP-1"bad'; hostile_status.data["inventory"]["outputs"] = [hostile]
    with pytest.raises(Exception) as caught: activate(ctx,hostile_status,SAMPLE["profile"],{"laptop":hostile["connector"]})
    assert caught.value.code == "monitors_unsupported_output_name"

    host = backend["planner"]._paths(ctx)["host"]; host.parent.mkdir(parents=True); host.write_text('hl.monitor({ output = "eDP-1", mode = "preferred", position = "auto", scale = 1 })\n')
    with pytest.raises(Exception) as caught: activate(ctx,status,SAMPLE["profile"],{"laptop":"eDP-1"})
    assert caught.value.code == "monitors_handwritten_rule_conflict"
    host.write_text('-- BEGIN OMARCHY CUSTOMIZATION CENTER MONITORS v1\n')
    with pytest.raises(Exception) as caught: activate(ctx,status,SAMPLE["profile"],{"laptop":"eDP-1"})
    assert caught.value.code == "monitors_managed_block_collision"

    cap_ctx = context(tmp_path / "cap", monkeypatch); cap_status = status_for(backend, cap_ctx)
    cap_ctx.capabilities = Capabilities("monitors", tuple(Capability(item.name, False if item.name == "timed_confirmation" else item.available, "missing" if item.name == "timed_confirmation" else item.reason, item.readonly_check, item.argv_prefix) for item in cap_ctx.capabilities.items), "now")
    with pytest.raises(Exception) as caught: activate(cap_ctx,cap_status,SAMPLE["profile"],{"laptop":"eDP-1"})
    assert caught.value.code == "capability_missing"


def test_scanner_uncertain_shapes_fail_closed(backend):
    scanner = backend["ownership"].scan
    for text in ("local m = hl.monitor\nm({ output = \"DP-1\" })", "function f() hl.monitor({ output = \"DP-1\" }) end", "dofile(\"x.lua\")", "hl.monitor({ output = name })", "--[[ unterminated"):
        with pytest.raises(Exception) as caught: scanner(text.encode(), [])
        assert getattr(caught.value, "code", None) == "unsupported_config"
    assert scanner(b'local x = [=[hl.monitor({ output = "DP-1" })]=]\nhl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })', [])["catchAll"]
    for field in (b"transform = 0", b'mirror = "DP-1"', b"vrr = 1"):
        with pytest.raises(Exception) as caught:
            scanner(b'hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1, ' + field + b" })", [])
        assert getattr(caught.value, "code", None) == "unsupported_config"


def test_active_state_machine(backend, tmp_path, monkeypatch):
    module = backend["planner"].MODULE
    base_ctx = context(tmp_path, monkeypatch)
    outputs, _ = backend["inventory"].parse_inventory(INVENTORY_TEXT)
    monkeypatch.setattr(backend["planner"].inventory, "read", lambda unused, timeout_s=3: (outputs, ()))
    assert module.status(base_ctx).data["active"]["state"] == "none"
    paths = backend["planner"]._paths(base_ctx); paths["active"].parent.mkdir(parents=True)
    pointer = {"schemaVersion":1,"profileId":"laptop","planDigest":"digest","appliedAt":"now","rulesSha256":"sha256:x","assignments":{"laptop":"eDP-1"}}
    paths["active"].write_text(json.dumps(pointer))
    assert module.status(base_ctx).data["active"]["state"] == "drifted"
    expected = backend["planner"]._topology(outputs)
    reload = ops.HyprctlReload(base_ctx); reload = __import__("dataclasses").replace(reload, detail={"expectedTopology":expected,"profileId":"laptop","clamshellApplied":False})
    owner_plan = Plan("monitors","revision",(reload,),(),"",(),(),plan_digest="digest")
    owner = SimpleNamespace(id="tx1", state="committed", plan=owner_plan)
    base_ctx.journal = Journal([owner])
    active = module.status(base_ctx).data["active"]
    assert active["state"] == "verified" and active["transactionId"] == "tx1"
    waiting = SimpleNamespace(id="tx2", state="awaiting_confirmation", plan=owner_plan)
    base_ctx.journal = Journal([waiting, owner])
    assert module.status(base_ctx).data["active"]["state"] == "awaiting-confirmation"

    toggle_dir = base_ctx.paths.home / ".local/state/omarchy/toggles/hypr"; toggle_dir.mkdir(parents=True)
    (toggle_dir / "internal-monitor-clamshell.lua").write_text('hl.monitor({ output = "eDP-1", disabled = true })\n')
    disabled = json.loads(json.dumps(outputs)); disabled[0].update({"disabled":True,"width":0,"height":0,"refreshMilliHz":0})
    monkeypatch.setattr(backend["planner"].inventory, "read", lambda unused, timeout_s=3: (disabled, ()))
    expected_disabled = backend["planner"]._topology(disabled)
    reload2 = __import__("dataclasses").replace(reload, detail={"expectedTopology":expected_disabled,"untoggledExpectedTopology":expected,"profileId":"laptop","clamshellApplied":True})
    owner2 = SimpleNamespace(id="tx3", state="committed", plan=Plan("monitors","revision",(reload2,),(),"",(),(),plan_digest="digest"))
    base_ctx.journal = Journal([owner2])
    assert module.status(base_ctx).data["active"]["state"] == "overridden"
    unrelated = json.loads(json.dumps(disabled)); unrelated[0]["transform"] = 3
    monkeypatch.setattr(backend["planner"].inventory, "read", lambda unused, timeout_s=3: (unrelated, ()))
    assert module.status(base_ctx).data["active"]["state"] == "drifted"


def test_active_owner_uses_pointer_operation_fallback(backend, tmp_path, monkeypatch):
    ctx = context(tmp_path, monkeypatch); module = backend["planner"].MODULE
    outputs, _ = backend["inventory"].parse_inventory(INVENTORY_TEXT)
    monkeypatch.setattr(backend["planner"].inventory, "read", lambda unused, timeout_s=3: (outputs, ()))
    paths = backend["planner"]._paths(ctx); paths["active"].parent.mkdir(parents=True)
    pointer = {"schemaVersion":1,"profileId":"laptop","planDigest":"pointer-digest","appliedAt":"now","rulesSha256":"sha256:x","assignments":{"laptop":"eDP-1"}}
    paths["active"].write_text(json.dumps(pointer))
    reload = __import__("dataclasses").replace(ops.HyprctlReload(ctx), detail={"expectedTopology":backend["planner"]._topology(outputs),"untoggledExpectedTopology":backend["planner"]._topology(outputs),"profileId":"laptop"})
    pointer_op = ops.WriteFileAtomic(ctx, paths["active"], json.dumps(pointer), "0600", "Record active monitor profile")
    plan = Plan("monitors","revision",(reload,pointer_op),(),"",(),(),plan_digest="executor-digest-differs")
    ctx.journal = Journal([SimpleNamespace(id="fallback-tx", state="committed", plan=plan)])
    active = module.status(ctx).data["active"]
    assert active["state"] == "verified" and active["transactionId"] == "fallback-tx"


def test_monitors_profile_active_code(backend, tmp_path, monkeypatch):
    ctx=context(tmp_path,monkeypatch); status=status_for(backend,ctx); status.data["active"]={"profileId":"laptop","state":"verified"}
    with pytest.raises(Exception) as caught:
        backend["planner"].MODULE.plan(ctx,{"schemaVersion":1,"action":"delete-profile","profileId":"laptop"},status)
    assert caught.value.code == "monitors_profile_active"


def test_monitors_verification_failed_code_for_final_file_mismatch(backend, tmp_path, monkeypatch):
    ctx=context(tmp_path,monkeypatch); module=backend["planner"].MODULE; status=status_for(backend,ctx)
    expected=backend["planner"]._topology(status.data["inventory"]["outputs"])
    detail={"expectedTopology":expected,"profileId":"laptop","unguardedSha256":"sha256:missing"}
    reload=__import__("dataclasses").replace(ops.HyprctlReload(ctx),detail=detail)
    pointer=ops.WriteFileAtomic(ctx,ctx.paths.module_state("monitors") / "active.json","{}","0600","Record active monitor profile")
    plan=Plan("monitors","revision",(reload,pointer),(),"",(),())
    monkeypatch.setattr(backend["planner"].inventory,"read",lambda unused,timeout_s=3:(status.data["inventory"]["outputs"],()))
    result=module.verify(ctx,plan,status,{pointer.id:OperationResult(pointer.id,0,"","",False,0,None)})
    assert result.code == "monitors_verification_failed"


def test_verify_requires_two_stable_samples(backend, tmp_path, monkeypatch):
    ctx = context(tmp_path, monkeypatch); module = backend["planner"].MODULE; status = status_for(backend, ctx)
    expected = backend["planner"]._topology(status.data["inventory"]["outputs"])
    reload = ops.HyprctlReload(ctx); reload = __import__("dataclasses").replace(reload, detail={"expectedTopology":expected,"profileId":"laptop","unguardedSha256":"sha256:x"})
    plan = Plan("monitors","revision",(reload,),(),"verify",(),())
    good = status.data["inventory"]["outputs"]
    changing = json.loads(json.dumps(good)); changing[0]["x"] = 8
    sequence = iter([(changing,()),(good,()),(good,())])
    monkeypatch.setattr(backend["planner"].inventory, "read", lambda unused, timeout_s=3: next(sequence))
    assert module.verify(ctx, plan, status, {}).state == "pass"
    assert ctx.clock.sleeps == [0.5, 0.5]
    timeouts = []
    def never_stable(unused, timeout_s=3):
        timeouts.append(timeout_s)
        return changing, ()
    monkeypatch.setattr(backend["planner"].inventory, "read", never_stable)
    exhausted = context(tmp_path / "unstable", monkeypatch)
    assert module.verify(exhausted, plan, status, {}).code == "monitors_topology_unstable"
    assert exhausted.clock.monotonic() == 3.0
    assert sum(exhausted.clock.sleeps) == 3.0
    assert timeouts == [3.0, 2.5, 2.0, 1.5, 1.0, 0.5]

    final_ctx = context(tmp_path / "final-unstable", monkeypatch)
    pointer = ops.WriteFileAtomic(final_ctx, final_ctx.paths.module_state("monitors") / "active.json", "{}", "0600", "Record active monitor profile")
    final_plan = Plan("monitors", "revision", (reload, pointer), (), "verify", (), ())
    final_timeouts = []
    def final_never_stable(unused, timeout_s=3):
        final_timeouts.append(timeout_s)
        return changing, ()
    monkeypatch.setattr(backend["planner"].inventory, "read", final_never_stable)
    result = module.verify(final_ctx, final_plan, status, {pointer.id: OperationResult(pointer.id, 0, "", "", False, 0, None)})
    assert result.code == "monitors_topology_unstable"
    assert final_ctx.clock.monotonic() == 8.0
    assert final_timeouts == [8.0, 7.5, 7.0, 6.5, 6.0, 5.5, 5.0, 4.5, 4.0, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5]
