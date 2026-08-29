import json
from pathlib import Path

from customization_center.core import Paths, build_context, load_registry

ROOT = Path(__file__).resolve().parents[3]


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
