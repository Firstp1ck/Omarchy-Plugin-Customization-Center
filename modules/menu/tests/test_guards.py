from types import SimpleNamespace

from modules.menu.backend.guards import check, substitute_readers


def test_guard_reader_substitution_and_no_execution(stub_command):
    stub_command("bash", lambda request: {"exit_code": 0})
    ctx = SimpleNamespace(commands=SimpleNamespace(run=lambda argv, **kwargs: _run(stub_command, argv, kwargs)))
    result = check(ctx, '[[ "$(omarchy-default-browser)" == "zen" ]]')
    assert result["ok"]
    assert "${__omarchy_read_2}" in substitute_readers('$(omarchy-default-browser)')
    assert result["script"].startswith("if { [[")


def _run(stubs, argv, kwargs):
    from customization_center.core.commands import CommandRunner
    runner = CommandRunner("apply")
    runner.environ["PATH"] = str(stubs.directory)
    return runner.run(argv, **kwargs)


def test_oversized_guard_is_rejected_before_bash(stub_command):
    ctx = SimpleNamespace(commands=SimpleNamespace(run=lambda *args, **kwargs: None))
    result = check(ctx, "x" * 5000)
    assert not result["ok"] and result["code"] == "menu_field_content"
    assert stub_command.calls("bash") == []
