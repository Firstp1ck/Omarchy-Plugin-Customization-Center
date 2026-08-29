import json
from pathlib import Path

import pytest

from customization_center.core import CcError, Executor, Paths, build_context, load_registry

ROOT = Path(__file__).resolve().parents[3]


def _metadata():
    return {"ok": True, "commands": [
        {"route": "omarchy default browser", "args": "[chromium|chrome|brave|brave-origin|edge|firefox|zen]"},
        {"route": "omarchy default terminal", "args": "[alacritty|foot|ghostty|kitty]"},
        {"route": "omarchy default editor", "args": "[code|cursor|zed|sublime_text|helix|vim|emacs|nvim]"},
        {"route": "omarchy default agent", "args": "[pi|omp|opencode|ori|claude|codex|grok|agy|copilot|crush]"},
    ]}


def _executor_fixture(isolated_home, stub_command):
    state = {"browser": "chromium.desktop", "terminal": "foot.desktop", "terminal_set_exit": 0,
             "browser_inverse_fails": False}
    applications = isolated_home / ".local/share/applications"
    applications.mkdir(parents=True)
    for desktop_id, name in (("chromium.desktop", "Chromium"), ("firefox.desktop", "Firefox"),
                             ("foot.desktop", "Foot")):
        (applications / desktop_id).write_text(f"[Desktop Entry]\nName={name}\n", encoding="utf-8")
    preference = isolated_home / ".config/xdg-terminals.list"
    preference.write_text("# preferred terminal\nfoot.desktop\n", encoding="utf-8")
    mime = isolated_home / ".config/mimeapps.list"
    mime.write_text("[Default Applications]\nx-scheme-handler/http=chromium.desktop\n", encoding="utf-8")

    stub_command("omarchy", {"exit_code": 0, "stdout": json.dumps(_metadata())})
    stub_command("pacman", {"exit_code": 0, "stdout": ""})
    stub_command("mise", {"exit_code": 1, "stderr": "not installed"})
    for command in ("chromium", "firefox", "foot", "nvim"):
        stub_command(command, {"exit_code": 0})

    def browser(request):
        if len(request["argv"]) == 1:
            names = {"chromium.desktop": "chromium", "firefox.desktop": "firefox"}
            return {"exit_code": 0, "stdout": names.get(state["browser"], state["browser"]) + "\n"}
        target = request["argv"][1]
        if target == "chromium" and state["browser_inverse_fails"]:
            return {"exit_code": 8, "stderr": "inverse failed"}
        state["browser"] = target + ".desktop"
        mime.write_text("[Default Applications]\nx-scheme-handler/http=" + state["browser"] + "\n", encoding="utf-8")
        return {"exit_code": 0}

    def terminal(request):
        if len(request["argv"]) == 1:
            names = {"foot.desktop": "foot", "kitty.desktop": "kitty"}
            return {"exit_code": 0, "stdout": names.get(state["terminal"], state["terminal"]) + "\n"}
        return {"exit_code": state["terminal_set_exit"], "stderr": "terminal cancelled" if state["terminal_set_exit"] else ""}

    stub_command("omarchy-default-browser", browser)
    stub_command("omarchy-default-terminal", terminal)
    stub_command("omarchy-default-editor", {"exit_code": 0, "stdout": "nvim\n"})
    stub_command("omarchy-default-agent", {"exit_code": 0, "stdout": ""})
    stub_command("xdg-settings", lambda request: {"exit_code": 0, "stdout": state["browser"] + "\n"})
    stub_command("xdg-mime", lambda request: {"exit_code": 0, "stdout": state["browser"] + "\n"})
    stub_command("xdg-terminal-exec", lambda request: {"exit_code": 0, "stdout": state["terminal"] + "\n"})

    paths = Paths.from_env()
    registry = load_registry(ROOT, paths=paths)
    module = registry.view.module("defaults")
    context = lambda: build_context("defaults", "read", paths=paths, registry=registry.view, plugin_dir=ROOT)
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    return executor, module, context, state, applications, preference


def _apply_mixed(executor, module, context):
    status = module.status(context())
    draft = {"schemaVersion": 1, "changes": {
        "browser": {"choice": "firefox", "install": False},
        "terminal": {"choice": "kitty", "install": True},
    }}
    plan = module.plan(build_context("defaults", "plan", paths=executor.paths,
                                     registry=executor.registry, plugin_dir=ROOT), draft, status)
    return executor.apply("defaults", draft, status.revision, confirmations=plan.requires_confirmation)


def test_fault_after_selector_rolls_back_byte_identical(isolated_home, stub_command, fake_shell, fault_plan):
    state = {"browser": "custom.desktop"}
    mime = isolated_home / ".config/mimeapps.list"
    mime.parent.mkdir(parents=True, exist_ok=True)
    original = b"[Default Applications]\nx-scheme-handler/http=custom.desktop\n# exact bytes\n"
    mime.write_bytes(original)
    applications = isolated_home / ".local/share/applications"
    applications.mkdir(parents=True)
    (applications / "firefox.desktop").write_text("[Desktop Entry]\nName=Firefox\n", encoding="utf-8")

    commands = {"ok": True, "commands": [
        {"route": "omarchy default browser", "args": "[chromium|chrome|brave|brave-origin|edge|firefox|zen]"},
        {"route": "omarchy default terminal", "args": "[alacritty|foot|ghostty|kitty]"},
        {"route": "omarchy default editor", "args": "[code|cursor|zed|sublime_text|helix|vim|emacs|nvim]"},
        {"route": "omarchy default agent", "args": "[pi|omp|opencode|ori|claude|codex|grok|agy|copilot|crush]"},
    ]}
    stub_command("omarchy", {"exit_code": 0, "stdout": json.dumps(commands)})
    stub_command("pacman", {"exit_code": 0, "stdout": ""})
    stub_command("mise", {"exit_code": 1, "stderr": "not installed"})
    stub_command("firefox", {"exit_code": 0})
    stub_command("xdg-terminal-exec", {"exit_code": 0, "stdout": "foot.desktop\n"})
    stub_command("omarchy-default-terminal", {"exit_code": 0, "stdout": "foot\n"})
    stub_command("omarchy-default-editor", {"exit_code": 0, "stdout": "nvim\n"})
    stub_command("omarchy-default-agent", {"exit_code": 0, "stdout": ""})

    def browser(request):
        if len(request["argv"]) == 1:
            value = state["browser"]
            return {"exit_code": 0, "stdout": ("firefox" if value == "firefox.desktop" else value) + "\n"}
        state["browser"] = "firefox.desktop"
        mime.write_bytes(b"changed by selector\n")
        return {"exit_code": 0}

    stub_command("omarchy-default-browser", browser)
    stub_command("xdg-settings", lambda request: {"exit_code": 0, "stdout": state["browser"] + "\n"})
    stub_command("xdg-mime", lambda request: {"exit_code": 0, "stdout": state["browser"] + "\n"})

    paths = Paths.from_env()
    registry = load_registry(ROOT, paths=paths)
    status = registry.view.module("defaults").status(build_context("defaults", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    fault_plan(["after_op:defaults.0002"])
    executor = Executor(ROOT, registry, paths, ROOT / "backend/ccctl")
    draft = {"schemaVersion": 1, "changes": {"browser": {"choice": "firefox", "install": False}}}
    with pytest.raises(CcError):
        executor.apply("defaults", draft, status.revision, confirmations=("defaults_replaces_unknown",))
    transaction = executor.journal.history(module="defaults", limit=1)[0]
    assert transaction.state == "rolled_back"
    assert mime.read_bytes() == original


def test_mixed_set_plus_handoff_abandon_rolls_back_completed_set(isolated_home, stub_command):
    executor, module, context, state, _, _ = _executor_fixture(isolated_home, stub_command)
    pending = _apply_mixed(executor, module, context)
    assert pending.state == "pending_handoff"
    assert state["browser"] == "firefox.desktop"

    abandoned = executor.abandon(pending.id)
    assert abandoned.state == "rolled_back" and abandoned.reason == "user"
    assert state["browser"] == "chromium.desktop"
    assert any(item.get("inverseOf") for item in abandoned.command_log)
    assert any(item["operationId"] == pending.plan.operations[-1].id for item in abandoned.skipped_inverse_ids)


def test_unwrapped_handoff_cancellation_rolls_back_earlier_set(isolated_home, stub_command):
    executor, module, context, state, _, _ = _executor_fixture(isolated_home, stub_command)
    state["terminal_set_exit"] = 130
    status = module.status(context())
    draft = {"schemaVersion": 1, "changes": {
        "browser": {"choice": "firefox", "install": False},
        "terminal": {"choice": "kitty", "install": True},
    }}
    plan = module.plan(build_context("defaults", "plan", paths=executor.paths,
                                     registry=executor.registry, plugin_dir=ROOT), draft, status)
    with pytest.raises(CcError) as caught:
        executor.apply("defaults", draft, status.revision, confirmations=plan.requires_confirmation)
    assert caught.value.code == "rollback_failed"
    tx = executor.journal.history(module="defaults", limit=1)[0]
    assert tx.state == "rollback_failed" and tx.reason == "handoff_failed"
    assert state["browser"] == "chromium.desktop"


def test_installed_terminal_set_verification_failure_rolls_back(isolated_home, stub_command):
    executor, module, context, state, applications, _ = _executor_fixture(isolated_home, stub_command)
    stub_command("kitty", {"exit_code": 0})
    (applications / "kitty.desktop").write_text("[Desktop Entry]\nName=Kitty\n", encoding="utf-8")
    status = module.status(context())
    draft = {"schemaVersion": 1, "changes": {"terminal": {"choice": "kitty", "install": False}}}

    with pytest.raises(CcError) as caught:
        executor.apply("defaults", draft, status.revision)
    assert caught.value.code == "defaults_verification_failed"
    failed = executor.journal.history(module="defaults", limit=1)[0]
    assert failed.state == "rolled_back" and failed.reason == "operation"
    assert failed.errors[-1]["code"] == "defaults_verification_failed"
    assert any(item.get("inverseOf") for item in failed.command_log)
    assert state["terminal"] == "foot.desktop"


def test_reconcile_terminal_false_success_persists_verify_evidence(isolated_home, stub_command):
    executor, module, context, state, applications, _ = _executor_fixture(isolated_home, stub_command)
    status = module.status(context())
    draft = {"schemaVersion": 1, "changes": {"terminal": {"choice": "kitty", "install": True}}}
    plan = module.plan(build_context("defaults", "plan", paths=executor.paths,
                                     registry=executor.registry, plugin_dir=ROOT), draft, status)
    pending = executor.apply("defaults", draft, status.revision, confirmations=plan.requires_confirmation)
    stub_command("kitty", {"exit_code": 0})
    (applications / "kitty.desktop").write_text("[Desktop Entry]\nName=Kitty\n", encoding="utf-8")

    reconciled = executor.reconcile(pending.id)
    assert reconciled.state == "rolled_back" and reconciled.reason == "verification"
    assert reconciled.verify is not None
    assert reconciled.verify.code == "defaults_installed_not_set"
    assert reconciled.verify.evidence == {"category": "terminal", "choice": "kitty"}
    projected = module.status(context())
    terminal = next(item for item in projected.data["categories"] if item["id"] == "terminal")
    assert terminal["outcome"]["state"] == "installed_not_set"
    assert terminal["outcome"]["choice"] == "kitty"


def test_reconcile_commits_with_status_evidence(isolated_home, stub_command):
    executor, module, context, state, applications, preference = _executor_fixture(isolated_home, stub_command)
    status = module.status(context())
    draft = {"schemaVersion": 1, "changes": {"terminal": {"choice": "kitty", "install": True}}}
    plan = module.plan(build_context("defaults", "plan", paths=executor.paths,
                                     registry=executor.registry, plugin_dir=ROOT), draft, status)
    pending = executor.apply("defaults", draft, status.revision, confirmations=plan.requires_confirmation)
    stub_command("kitty", {"exit_code": 0})
    (applications / "kitty.desktop").write_text("[Desktop Entry]\nName=Kitty\n", encoding="utf-8")
    state["terminal"] = "kitty.desktop"
    preference.write_text("# preferred terminal\nkitty.desktop\n", encoding="utf-8")

    reconciled = executor.reconcile(pending.id)
    assert reconciled.state == "committed"
    assert reconciled.verify is not None and reconciled.verify.state == "pass"
    assert reconciled.verify.evidence["revision"] == reconciled.after_revision
    terminal = next(item for item in module.status(context()).data["categories"] if item["id"] == "terminal")
    assert terminal["outcome"] is None


def test_abandon_reports_inverse_rollback_failure(isolated_home, stub_command):
    executor, module, context, state, _, _ = _executor_fixture(isolated_home, stub_command)
    pending = _apply_mixed(executor, module, context)
    state["browser_inverse_fails"] = True

    failed = executor.abandon(pending.id)
    assert failed.state == "rollback_failed" and failed.reason == "user"
    assert failed.rollback_errors
    browser = next(item for item in module.status(context()).data["categories"] if item["id"] == "browser")
    assert browser["outcome"]["state"] == "rollback_failed"
    assert browser["outcome"]["transactionId"] == pending.id
