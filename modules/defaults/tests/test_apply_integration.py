import json
from pathlib import Path

import pytest

from customization_center.core import CcError, Executor, Paths, build_context, load_registry

ROOT = Path(__file__).resolve().parents[3]


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
