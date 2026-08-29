from modules.defaults.backend.catalog import CATALOG


def test_catalog_matches_pinned_selector_choices():
    expected = {
        "browser": ["chromium", "chrome", "brave", "brave-origin", "edge", "firefox", "zen"],
        "terminal": ["alacritty", "foot", "ghostty", "kitty"],
        "editor": ["code", "cursor", "zed", "sublime_text", "helix", "vim", "emacs", "nvim"],
        "agent": ["agy", "claude", "codex", "copilot", "crush", "grok", "omp", "opencode", "ori", "pi"],
    }
    assert {item["id"]: [choice["id"] for choice in item["choices"]] for item in CATALOG} == expected
    assert next(choice for item in CATALOG if item["id"] == "editor" for choice in item["choices"] if choice["id"] == "zed")["reported"] == "zeditor"


def test_catalog_handoff_tokens_are_shell_safe():
    forbidden = set(" \t\r\n;&|<>$`\"'")
    assert all(not (set(choice["id"]) & forbidden) for category in CATALOG for choice in category["choices"])
