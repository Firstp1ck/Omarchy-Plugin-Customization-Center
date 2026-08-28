import pytest

from customization_center.core import CcError, CommandRunner, ShellIpc


def test_success_bodies_and_json(fake_shell, stub_command):
    shell = ShellIpc(CommandRunner())
    assert shell.ping()
    assert isinstance(shell.list_plugins(), list)
    assert shell.list_shell_config()["version"] == 1
    assert shell.call("reloadConfig").body == "ok"
    assert shell.call("rescanPlugins").body == ""
    assert shell.call("hide", "omarchy.menu").body == ""
    assert stub_command.calls("omarchy-shell")[0] == ["omarchy-shell", "shell", "ping"]


def test_exit_zero_error_body_is_rejected(fake_shell):
    fake_shell.reject("setPluginEnabled", "unknown")
    with pytest.raises(CcError) as caught:
        ShellIpc(CommandRunner()).call("setPluginEnabled", "missing", "true")
    assert caught.value.code == "ipc_rejected" and caught.value.data["body"] == "unknown"


def test_transport_classification(fake_shell, stub_command):
    fake_shell.switch("down")
    with pytest.raises(CcError) as caught:
        ShellIpc(CommandRunner()).ping()
    assert caught.value.code == "runtime_unavailable"
    stub_command("omarchy-shell", {"exit_code": 1, "stderr": "Function not found.\n"})
    with pytest.raises(CcError) as caught:
        ShellIpc(CommandRunner()).ping()
    assert caught.value.code == "unsupported_config"


def test_object_args_are_compact_json(fake_shell, stub_command):
    shell = ShellIpc(CommandRunner())
    shell.call("enablePlugin", "omarchy.menu", {"section": "left", "index": 0})
    assert stub_command.calls("omarchy-shell")[-1][-1] == '{"section":"left","index":0}'


def test_per_method_success_body_matrix(fake_shell):
    shell = ShellIpc(CommandRunner())
    calls = [
        ("ping", (), "ok"),
        ("reloadConfig", (), "ok"),
        ("enablePlugin", ("omarchy.menu", {"section": "left"}), "ok"),
        ("setPluginEnabled", ("omarchy.menu", "true"), "ok"),
        ("putBarWidget", ("omarchy.menu", {"section": "left"}), "ok"),
        ("moveBarWidget", ("omarchy.menu", {"section": "left", "index": 0}), "ok"),
        ("setBarWidget", ("omarchy.menu", "label", "1", {}), "ok"),
        ("applyTheme", ("YQ==", "Yg=="), "ok"),
        ("rescanPlugins", (), ""),
        ("summon", ("omarchy.menu", {}), "ok"),
        ("hide", ("omarchy.menu",), ""),
    ]
    for method, args, expected in calls:
        assert shell.call(method, *args).body == expected
    assert isinstance(shell.call("listPlugins", expect_json=True).parsed, list)
    assert isinstance(shell.call("listShellConfig", expect_json=True).parsed, dict)


def test_runner_timeout_is_timeout_error(fake_shell):
    fake_shell.switch("slow")
    with pytest.raises(CcError) as caught:
        ShellIpc(CommandRunner()).call("ping", timeout_s=.05)
    assert caught.value.code == "timeout"
