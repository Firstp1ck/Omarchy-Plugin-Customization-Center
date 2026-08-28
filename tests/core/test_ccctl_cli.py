from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CCCTL = ROOT / "backend/ccctl"
SAMPLE = ROOT / "tests/fixtures/modules/hello/tests/fixtures/sample-draft.json"


def _run(args, *, stdin=None, env=None):
    completed = subprocess.run([str(CCCTL), *args], input=stdin, text=True, capture_output=True,
                               env=env or dict(os.environ), timeout=15)
    lines = completed.stdout.splitlines(); assert lines
    envelope = json.loads(lines[-1]); assert isinstance(envelope, dict)
    return completed, envelope


def test_cli_hello_end_to_end_and_envelopes(isolated_home, stub_command, monkeypatch):
    stub_command("hello-command", {"exit_code": 0})
    monkeypatch.setenv("CC_EXTRA_MODULE_DIRS", str(ROOT / "tests/fixtures/modules/hello"))
    completed, modules = _run(["modules"]); assert completed.returncode == 0
    hello_rows = [row for row in modules["data"]["modules"] if row["id"] == "hello"]
    assert len(hello_rows) == 1
    row = hello_rows[0]
    assert row["pageUrl"].startswith("file://") and "recovery" in modules["data"]
    _, doctor = _run(["doctor"]); assert doctor["data"]["bytecodeDisabled"] and doctor["data"]["pythonSupported"]
    _, status = _run(["status", "hello"]); revision = status["revision"]
    raw = SAMPLE.read_text()
    envelope = json.dumps({"schemaVersion":1,"module":"hello","baseRevision":revision,
                           "updatedAt":"2024-01-01T00:00:00Z","draft":json.loads(raw)})
    assert _run(["draft", "save", "hello", "--draft", "-"], stdin=envelope)[0].returncode == 0
    asset = isolated_home / "asset.txt"; asset.write_text("asset")
    assert _run(["draft", "asset-add", "hello", "--path", str(asset)])[0].returncode == 0
    assert _run(["migrate", "hello", "--kind", "draft", "--document", "-"], stdin=raw)[0].returncode == 0
    for command in (["capabilities", "hello"], ["validate", "hello", "--draft", "-"],
                    ["plan", "hello", "--draft", "-"], ["history"], ["recover"],
                    ["transaction", "current"], ["draft", "load", "hello"]):
        completed, envelope = _run(command, stdin=raw if "-" in command else None)
        assert completed.returncode == 0 and envelope["ok"]
    completed, applied = _run(["apply", "hello", "--draft", "-", "--expected-revision", revision], stdin=raw)
    assert completed.returncode == 0; txid = applied["transactionId"]
    for command in (["transaction", txid], ["history", "--module", "hello"],
                    ["rollback", txid], ["draft", "discard", "hello"]):
        assert _run(command)[0].returncode == 0
    unknown = "00000000-0000-0000-0000-000000000000"
    failing = [["confirm", unknown, "--token", "x"], ["reconcile", unknown], ["abandon", unknown],
               ["restore", unknown, "--path", "/tmp/x"], ["resolve", unknown, "--operation", "x"],
               ["query", "hello", "missing"], ["migrate", "missing", "--kind", "draft", "--document", "-"]]
    for command in failing:
        completed, envelope = _run(command, stdin=raw if command[-1] == "-" else None)
        assert completed.returncode == 1 and not envelope["ok"] and envelope["errors"][0]["code"] != "internal_error"
    assert _run([])[0].returncode == 2


def test_stray_module_print_is_tolerated(isolated_home, tmp_path, monkeypatch):
    module = tmp_path / "hello"
    shutil.copytree(ROOT / "tests/fixtures/modules/hello", module)
    backend = module / "backend/__init__.py"
    source = backend.read_text().replace("from __future__ import annotations\n", "from __future__ import annotations\nprint('stray output')\n")
    backend.write_text(source)
    monkeypatch.setenv("CC_EXTRA_MODULE_DIRS", str(module))
    completed, envelope = _run(["modules"])
    assert completed.returncode == 0 and envelope["ok"]
    assert "stray output" in completed.stdout.splitlines()[:-1]
