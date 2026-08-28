from __future__ import annotations

import errno
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from customization_center.core import BackupStore, CcError, CommandRunner, Hyprctl, Operation, ShellIpc, ops
from customization_center.core.paths import Paths


def _ctx(paths: Paths):
    return SimpleNamespace(module_id="sample", cache={}, paths=paths)


def _exec(paths: Paths, txid="tx"):
    commands = CommandRunner()
    return SimpleNamespace(paths=paths, commands=commands, shell=ShellIpc(commands), hyprctl=Hyprctl(commands),
                           cache={}, backups=BackupStore(paths), txid=txid,
                           ccctl_path=str(Path(__file__).resolve().parents[2] / "backend/ccctl"))


def _run_inverses(operation, result, exec_ctx):
    for inverse in ops.build_inverse(operation, exec_ctx, result):
        ops.run_forward(inverse, exec_ctx)


def test_write_file_forward_inverse_new_existing_and_mode(isolated_home):
    paths = Paths.from_env(); ctx = _ctx(paths); target = paths.module_config("sample") / "file"
    target.parent.mkdir(parents=True); target.write_text("old"); target.chmod(0o640)
    operation = ops.WriteFileAtomic(ctx, target, "new", None); exec_ctx = _exec(paths)
    exec_ctx.backups.take(exec_ctx.txid, [target]); result = ops.run_forward(operation, exec_ctx)
    assert target.read_text() == "new" and target.stat().st_mode & 0o777 == 0o640
    _run_inverses(operation, result, exec_ctx); assert target.read_text() == "old"
    target.unlink(); operation = ops.WriteFileAtomic(ctx, target, "created", "0600")
    exec_ctx = _exec(paths, "new"); exec_ctx.backups.take(exec_ctx.txid, [target])
    result = ops.run_forward(operation, exec_ctx); _run_inverses(operation, result, exec_ctx)
    assert not target.exists()


def test_managed_block_insert_replace_remove_inverse_and_collisions(isolated_home):
    paths = Paths.from_env(); ctx = _ctx(paths); target = paths.module_config("sample") / "config.lua"
    target.parent.mkdir(parents=True); target.write_text("outside\n")
    operation = ops.ReplaceManagedBlock(ctx, target, "TEST", 1, "one")
    exec_ctx = _exec(paths); exec_ctx.backups.take(exec_ctx.txid, [target])
    result = ops.run_forward(operation, exec_ctx); assert "one" in target.read_text()
    _run_inverses(operation, result, exec_ctx); assert target.read_text() == "outside\n"
    for content in ("-- BEGIN OMARCHY CUSTOMIZATION CENTER TEST v1\n",
                    "-- END OMARCHY CUSTOMIZATION CENTER TEST v1\n",
                    "-- END OMARCHY CUSTOMIZATION CENTER TEST v1\n-- BEGIN OMARCHY CUSTOMIZATION CENTER TEST v1\n",
                    "-- BEGIN OMARCHY CUSTOMIZATION CENTER TEST v1\n-- BEGIN OMARCHY CUSTOMIZATION CENTER TEST v1\n-- END OMARCHY CUSTOMIZATION CENTER TEST v1\n"):
        target.write_text(content)
        with pytest.raises(CcError) as caught: ops.run_forward(operation, exec_ctx)
        assert caught.value.code == "unsupported_config"


def test_ensure_directory_forward_inverse_created_and_existing(isolated_home):
    paths = Paths.from_env(); ctx = _ctx(paths); leaf = paths.module_config("sample") / "leaf"; exec_ctx = _exec(paths)
    operation = ops.EnsureDirectory(ctx, leaf); result = ops.run_forward(operation, exec_ctx)
    _run_inverses(operation, result, exec_ctx); assert not leaf.exists()
    leaf.mkdir(); operation = ops.EnsureDirectory(ctx, leaf); result = ops.run_forward(operation, exec_ctx)
    _run_inverses(operation, result, exec_ctx); assert leaf.exists()


def test_every_builder_produces_frozen_operations(isolated_home):
    paths = Paths.from_env(); ctx = _ctx(paths); target = paths.module_config("sample") / "x"
    staged = paths.staging_dir("sample", "plan")
    operations = [
        ops.WriteFileAtomic(ctx, target, "x", "0600"),
        ops.ReplaceManagedBlock(ctx, target.with_suffix(".lua"), "TEST", 1, "x"),
        ops.EnsureDirectory(ctx, target.parent), ops.ReplaceDirectoryAtomic(ctx, target, staged),
        ops.RunCommand(ctx, ["true"], 1, "run", inverse=["true"]), ops.RestoreBackup(ctx, target),
        ops.RemoveFile(ctx, target), ops.ShellIpc(ctx, "ping"), ops.HyprctlReload(ctx),
        ops.TimedConfirmation(ctx, 1), ops.TerminalHandoff(ctx, ["true"], "title"),
    ]
    assert {item.kind for item in operations} == set(ops._KINDS)
    for operation in operations:
        ops.validate_operation(operation, paths)
        with pytest.raises(Exception):
            operation.kind = "changed"


def test_directory_replace_create_replace_remove_inverse_and_git_refusal(isolated_home):
    paths = Paths.from_env(); ctx = _ctx(paths); target = paths.module_config("sample") / "theme"
    staged = paths.staging_dir("sample", "create"); (staged / "value").write_text("new")
    operation = ops.ReplaceDirectoryAtomic(ctx, target, staged); exec_ctx = _exec(paths)
    result = ops.run_forward(operation, exec_ctx); assert (target / "value").read_text() == "new"
    _run_inverses(operation, result, exec_ctx); assert not target.exists()
    target.mkdir(); (target / "value").write_text("old")
    staged = paths.staging_dir("sample", "replace"); (staged / "value").write_text("new")
    with pytest.raises(CcError): ops.run_forward(ops.ReplaceDirectoryAtomic(ctx, target, staged), exec_ctx)
    operation = ops.ReplaceDirectoryAtomic(ctx, target, staged, allow_existing=True)
    result = ops.run_forward(operation, exec_ctx); _run_inverses(operation, result, exec_ctx)
    assert (target / "value").read_text() == "old"
    operation = ops.ReplaceDirectoryAtomic(ctx, target, None, allow_existing=True)
    result = ops.run_forward(operation, exec_ctx); assert not target.exists()
    _run_inverses(operation, result, exec_ctx); assert (target / "value").read_text() == "old"
    (target / ".git").mkdir()
    with pytest.raises(CcError): ops.run_forward(ops.ReplaceDirectoryAtomic(ctx, target, None, True), exec_ctx)


def test_directory_replace_cross_filesystem_fallback(isolated_home, monkeypatch):
    paths = Paths.from_env(); ctx = _ctx(paths); target = paths.module_config("sample") / "cross"
    staged = paths.staging_dir("sample", "cross"); (staged / "value").write_text("copied")
    original_rename = os.rename; raised = {"value": False}
    def exdev_once(source, destination):
        if not raised["value"] and Path(destination) == target:
            raised["value"] = True
            raise OSError(errno.EXDEV, "cross-device")
        return original_rename(source, destination)
    monkeypatch.setattr(os, "rename", exdev_once)
    result = ops.run_forward(ops.ReplaceDirectoryAtomic(ctx, target, staged), _exec(paths))
    assert raised["value"] and (target / "value").read_text() == "copied"


def test_staging_and_backup_paths_are_validated(isolated_home, tmp_path):
    paths = Paths.from_env(); ctx = _ctx(paths)
    outside_stage = ops.ReplaceDirectoryAtomic(ctx, paths.module_config("sample") / "theme", tmp_path)
    with pytest.raises(CcError) as caught:
        ops.validate_operation(outside_stage, paths)
    assert caught.value.code == "permission_required"
    operation = Operation("sample.9999", "sample", "ShellIpc",
        {"method": "ping", "args": [], "expect": ["ok"], "expect_json": False},
        "unsafe backup", (), ("/etc/passwd",), 5)
    with pytest.raises(CcError) as caught:
        ops.validate_operation(operation, paths)
    assert caught.value.code == "permission_required"


def test_run_command_expect_env_stdin_capture_and_inverse(isolated_home, stub_command):
    def handler(request):
        assert request["stdin"] == "input"
        assert "BROWSER" not in request["env"]
        return {"exit_code": 7, "stdout": "abcdefgh", "stderr": "err"}
    stub_command("runner", handler); stub_command("undo", {"exit_code": 0})
    paths = Paths.from_env(); operation = ops.RunCommand(_ctx(paths), ["runner"], 1, "run",
        inverse=["undo"], expect_exit=7, capture_limit=4, env_extra={"BROWSER": None}, stdin="input")
    exec_ctx = _exec(paths); result = ops.run_forward(operation, exec_ctx)
    assert result.exit_code == 7 and result.stdout_head == "abcd"
    _run_inverses(operation, result, exec_ctx)
    assert stub_command.calls("undo") == [["undo"]]


def test_restore_backup_remove_file_and_refusals(isolated_home):
    paths = Paths.from_env(); ctx = _ctx(paths); target = paths.module_config("sample") / "remove"
    target.parent.mkdir(parents=True); target.write_text("old")
    exec_ctx = _exec(paths); exec_ctx.backups.take(exec_ctx.txid, [target])
    remove = ops.RemoveFile(ctx, target); result = ops.run_forward(remove, exec_ctx); assert not target.exists()
    _run_inverses(remove, result, exec_ctx); assert target.read_text() == "old"
    target.unlink(); target.mkdir()
    with pytest.raises(CcError): ops.run_forward(remove, exec_ctx)
    target.rmdir(); outside = target.parent / "outside"; outside.write_text("x"); target.symlink_to(outside)
    with pytest.raises(CcError): ops.run_forward(remove, exec_ctx)


def test_run_command_detach_leaves_process_running(isolated_home, stub_command):
    stub_command("forever", {"hang": True, "hangSeconds": .3})
    paths = Paths.from_env(); context = _ctx(paths)
    operation = ops.RunCommand(context, ["forever"], .05, "detach", wait_policy="detach")
    exec_ctx = SimpleNamespace(commands=CommandRunner(), cache={})
    result = ops.run_forward(operation, exec_ctx)
    assert result.exit_code is None and result.timed_out is False


def test_shell_ipc_operation_mappings(isolated_home, fake_shell, stub_command):
    paths = Paths.from_env(); ctx = _ctx(paths); exec_ctx = _exec(paths)
    success = ops.ShellIpc(ctx, "ping"); assert ops.run_forward(success, exec_ctx).stdout_head == "ok"
    parsed = ops.ShellIpc(ctx, "listShellConfig", expect_json=True)
    assert json.loads(ops.run_forward(parsed, exec_ctx).stdout_head)["version"] == 1
    fake_shell.reject("setPluginEnabled", "unknown")
    with pytest.raises(CcError) as caught:
        ops.run_forward(ops.ShellIpc(ctx, "setPluginEnabled", ["x", "true"]), exec_ctx)
    assert caught.value.code == "ipc_rejected"
    fake_shell.switch("down")
    with pytest.raises(CcError) as caught: ops.run_forward(success, exec_ctx)
    assert caught.value.code == "runtime_unavailable"
    stub_command("omarchy-shell", {"exit_code": 0, "stdout": "Function not found.\n"})
    with pytest.raises(CcError) as caught: ops.run_forward(success, exec_ctx)
    assert caught.value.code == "unsupported_config"


def test_hyprctl_reload_operation_guard_errors_and_config_only(isolated_home, stub_command):
    state = {"paused": True, "errors": []}
    stub_command("omarchy-hyprland-reload-guard", lambda request:
        {"exit_code": 0 if state["paused"] else 1})
    def hypr(request):
        argv = request["argv"]
        if argv[1:3] == ["-j", "configerrors"]: return {"stdout": json.dumps(state["errors"])}
        return {"stdout": "ok"}
    stub_command("hyprctl", hypr)
    paths = Paths.from_env(); ctx = _ctx(paths); exec_ctx = _exec(paths); exec_ctx.cache["hyprctl_configerrors_baseline"] = []
    operation = ops.HyprctlReload(ctx, True)
    with pytest.raises(CcError) as caught: ops.run_forward(operation, exec_ctx)
    assert caught.value.code == "runtime_unavailable"
    state["paused"] = False; ops.run_forward(operation, exec_ctx)
    assert ["hyprctl", "reload", "config-only"] in stub_command.calls("hyprctl")
    state["errors"] = [{"line": 1}]
    with pytest.raises(CcError) as caught: ops.run_forward(operation, exec_ctx)
    assert caught.value.code == "verification_failed"


def test_wrapped_handoff_uses_exact_launcher_argv(isolated_home, stub_command):
    stub_command("omarchy-launch-floating-terminal-with-presentation", {"exit_code": 0})
    paths = Paths.from_env(); context = _ctx(paths)
    operation = ops.TerminalHandoff(context, ["command", "arg"], "title", wrapped=True)
    repo = Path(__file__).resolve().parents[2]
    exec_ctx = SimpleNamespace(commands=CommandRunner(), cache={}, txid="12345678-1234-1234-1234-123456789abc",
                               ccctl_path=str(repo / "backend/ccctl"))
    ops.run_forward(operation, exec_ctx)
    assert stub_command.calls("omarchy-launch-floating-terminal-with-presentation") == [[
        "omarchy-launch-floating-terminal-with-presentation", str(repo / "backend/cc-handoff"),
        exec_ctx.txid, "command", "arg"]]


def test_terminal_handoff_rejects_metacharacters(isolated_home):
    paths = Paths.from_env()
    with pytest.raises(CcError): ops.validate_operation(ops.TimedConfirmation(_ctx(paths), 0), paths)
    for token in ("two words", "a;b", "a$b", 'a"b'):
        with pytest.raises(CcError):
            ops.validate_operation(ops.TerminalHandoff(_ctx(paths), [token], "title"), paths)


def test_cc_handoff_writes_sentinel(isolated_home):
    repo = Path(__file__).resolve().parents[2]
    txid = "12345678-1234-1234-1234-123456789abc"
    result = __import__("subprocess").run([str(repo / "backend/cc-handoff"), txid, "/usr/bin/true"],
        env=dict(os.environ), timeout=5, check=False)
    assert result.returncode == 0
    sentinel = Paths.from_env().state / "handoffs" / f"{txid}.json"
    assert '"exitCode":0' in sentinel.read_text()
