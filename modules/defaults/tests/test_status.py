import json
from pathlib import Path

from customization_center.core import Paths, build_context, load_registry

ROOT = Path(__file__).resolve().parents[3]


def _metadata():
    return {"ok": True, "commands": [
        {"route": "omarchy default browser", "args": "[chromium|chrome|brave|brave-origin|edge|firefox|zen]"},
        {"route": "omarchy default terminal", "args": "[alacritty|foot|ghostty|kitty]"},
        {"route": "omarchy default editor", "args": "[code|cursor|zed|sublime_text|helix|vim|emacs|nvim]"},
        {"route": "omarchy default agent", "args": "[pi|omp|opencode|ori|claude|codex|grok|agy|copilot|crush]"},
    ]}


def _stub_baseline(stub_command):
    for name, stdout in (("omarchy-default-browser", "chromium\n"), ("omarchy-default-terminal", ""),
                         ("omarchy-default-editor", "nvim\n"), ("omarchy-default-agent", ""),
                         ("xdg-settings", "chromium.desktop\n"), ("xdg-mime", "chromium.desktop\n"),
                         ("pacman", "")):
        stub_command(name, {"exit_code": 0, "stdout": stdout})
    stub_command("mise", {"exit_code": 1})
    stub_command("omarchy", {"exit_code": 0, "stdout": json.dumps(_metadata())})


def _status(paths):
    registry = load_registry(ROOT, paths=paths)
    return registry.view.module("defaults").status(
        build_context("defaults", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))


def test_status_classifies_unknown_browser_and_unset_agent(isolated_home, stub_command):
    metadata = {"ok": True, "commands": [
        {"route": "omarchy default browser", "args": "[chromium|chrome|brave|brave-origin|edge|firefox|zen]"},
        {"route": "omarchy default terminal", "args": "[alacritty|foot|ghostty|kitty]"},
        {"route": "omarchy default editor", "args": "[code|cursor|zed|sublime_text|helix|vim|emacs|nvim]"},
        {"route": "omarchy default agent", "args": "[pi|omp|opencode|ori|claude|codex|grok|agy|copilot|crush]"},
    ]}
    for name, stdout in (("omarchy-default-browser", "custom.desktop\n"), ("omarchy-default-terminal", "foot\n"),
                         ("omarchy-default-editor", "nvim\n"), ("omarchy-default-agent", ""),
                         ("xdg-settings", "custom.desktop\n"), ("xdg-mime", "custom.desktop\n"),
                         ("xdg-terminal-exec", "foot.desktop\n"), ("pacman", "")):
        stub_command(name, {"exit_code": 0, "stdout": stdout})
    stub_command("mise", {"exit_code": 1})
    stub_command("omarchy", {"exit_code": 0, "stdout": json.dumps(metadata)})
    paths = Paths.from_env(); registry = load_registry(ROOT, paths=paths)
    status = registry.view.module("defaults").status(build_context("defaults", "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    states = {item["id"]: item["state"] for item in status.data["categories"]}
    assert states["browser"] == "unknown"
    assert states["agent"] == "unset"


def test_missing_xdg_terminal_exec_is_probe_error(isolated_home, stub_command):
    _stub_baseline(stub_command)
    status = _status(Paths.from_env())
    terminal = next(item for item in status.data["categories"] if item["id"] == "terminal")
    assert terminal["state"] == "probe_error"
    assert terminal["probeError"]["command"] == "xdg-terminal-exec"
    assert "not on PATH" in terminal["probeError"]["message"]


def test_installed_xdg_terminal_exec_with_no_choice_is_none_resolvable(isolated_home, stub_command):
    _stub_baseline(stub_command)
    stub_command("xdg-terminal-exec", {"exit_code": 1, "stderr": "no terminal found"})
    status = _status(Paths.from_env())
    terminal = next(item for item in status.data["categories"] if item["id"] == "terminal")
    assert terminal["state"] == "none_resolvable"
    assert terminal["probeError"] is None


def test_absent_editor_state_file_uses_nvim_default(isolated_home, stub_command):
    _stub_baseline(stub_command)
    stub_command("xdg-terminal-exec", {"exit_code": 1})
    stub_command("nvim", {"exit_code": 0})
    status = _status(Paths.from_env())
    editor = next(item for item in status.data["categories"] if item["id"] == "editor")
    assert editor["state"] == "ready"
    assert editor["current"]["choice"] == "nvim"
    assert editor["current"]["raw"]["exists"] is False
    assert next(item for item in editor["checks"] if item["id"] == "state_file")["ok"] is True
