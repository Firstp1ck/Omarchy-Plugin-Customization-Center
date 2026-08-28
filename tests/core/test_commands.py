import time

import pytest

from customization_center.core import CcError, CommandRunner, redact


def test_argv_only_minimal_env_unset_and_stdin(stub_command, monkeypatch):
    monkeypatch.setenv("SHOULD_NOT_LEAK", "secret")
    stub_command("show", lambda req: {"stdout": req["stdin"] + "!"})
    runner = CommandRunner()
    result = runner.run(["show", "arg with space"], 2, env_extra={"LANG": None, "CUSTOM": "yes"}, stdin="input")
    record = stub_command.records("show")[0]
    assert result.stdout == "input!"
    assert "SHOULD_NOT_LEAK" not in record["env"] and "LANG" not in record["env"]
    assert record["env"]["CUSTOM"] == "yes"
    with pytest.raises(TypeError): runner.run("show", 1)


def test_mode_allowlists(stub_command):
    stub_command("check", {"stdout": "ok"})
    runner = CommandRunner(mode="validate")
    with pytest.raises(CcError): runner.run(["check"], 1)
    runner.allow_readonly(("check", "--read"))
    assert runner.run(["check", "--read", "x"], 1).exit_code == 0
    runner.mode = "plan"
    with pytest.raises(CcError): runner.run(["check", "--read"], 1)


def test_timeout_output_cap_and_redaction(stub_command):
    stub_command("hang", {"hang": True})
    result = CommandRunner().run(["hang"], .05)
    assert result.timed_out and result.duration_ms < 3000
    stub_command("large", {"stdout": "x" * 100})
    result = CommandRunner().run(["large"], 1, capture_limit=10)
    assert result.stdout == "x" * 10 and result.truncated
    text = redact("token=abc password: xyz Bearer abc.def https://user:pass@example.com/x")
    assert "abc" not in text and "xyz" not in text and "user:pass@" not in text


def test_output_is_drained_with_bounded_retention(stub_command):
    script = stub_command.directory / "twenty-megabytes"
    script.write_text("#!/usr/bin/python3\nimport os\nchunk=b'x'*65536\nfor _ in range(320): os.write(1, chunk)\n")
    script.chmod(0o755)
    started = time.monotonic()
    result = CommandRunner().run(["twenty-megabytes"], 10, capture_limit=4096)
    assert time.monotonic() - started < 5
    assert len(result.stdout.encode()) == 4096
    assert result.stderr == "" and result.truncated


def test_timeout_escalates_to_sigkill_when_sigterm_is_ignored(stub_command):
    script = stub_command.directory / "ignore-term"
    script.write_text("#!/bin/bash\ntrap '' TERM\n/bin/sleep 30\n")
    script.chmod(0o755)
    result = CommandRunner().run(["ignore-term"], .05)
    assert result.timed_out
    assert 2000 <= result.duration_ms < 5000
    assert result.exit_code == -9
