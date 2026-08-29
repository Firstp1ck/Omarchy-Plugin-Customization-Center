from __future__ import annotations

from typing import Any


def _installer(summary: str, sudo: bool, launches: bool = False) -> dict[str, Any]:
    return {"kind": "selector-install", "summary": summary, "needsSudo": sudo, "launchesApp": launches}


def _choice(id: str, label: str, *, command: str | None = None, desktop: str | None = None,
            package: tuple[str, str] | None = None, reported: str | None = None,
            aliases: tuple[str, ...] = (), mise: str | None = None, summary: str = "Install through the Omarchy selector",
            sudo: bool = True, launches: bool = False, icon: str = "") -> dict[str, Any]:
    return {"id": id, "label": label, "aliases": list(aliases), "reported": reported or id,
            "command": command, "desktopId": desktop, "misePackage": mise,
            "package": {"name": package[0], "source": package[1]} if package else None,
            "installer": _installer(summary, sudo, launches), "icon": icon}


CATALOG: tuple[dict[str, Any], ...] = (
    {"id": "browser", "label": "Browser", "summary": "Web links and browser XDG handlers",
     "selector": "omarchy-default-browser", "route": "omarchy default browser",
     "stateSource": {"kind": "xdg-settings"}, "stateFile": "~/.config/mimeapps.list",
     "emptyOutputMeans": None, "defaultChoice": "chromium", "installedPredicate": "path",
     "setLaunches": False, "setTimeoutS": 30, "choices": [
        _choice("chromium", "Chromium", command="chromium", desktop="chromium.desktop", package=("chromium", "pacman")),
        _choice("chrome", "Chrome", command="google-chrome-stable", desktop="google-chrome.desktop", package=("google-chrome", "aur")),
        _choice("brave", "Brave", command="brave", desktop="brave-browser.desktop", package=("brave-bin", "aur")),
        _choice("brave-origin", "Brave Origin", command="brave-origin", desktop="brave-origin.desktop", package=("brave-origin-bin", "aur")),
        _choice("edge", "Edge", command="microsoft-edge-stable", desktop="microsoft-edge.desktop", package=("microsoft-edge-stable-bin", "aur")),
        _choice("firefox", "Firefox", command="firefox", desktop="firefox.desktop", package=("firefox", "pacman")),
        _choice("zen", "Zen", command="zen-browser", desktop="zen.desktop", package=("zen-browser-bin", "aur")),
     ]},
    {"id": "terminal", "label": "Terminal", "summary": "Terminal used by xdg-terminal-exec",
     "selector": "omarchy-default-terminal", "route": "omarchy default terminal",
     "stateSource": {"kind": "xdg-terminal-exec"}, "stateFile": "~/.config/xdg-terminals.list",
     "emptyOutputMeans": "none_resolvable", "defaultChoice": "foot", "installedPredicate": "path",
     "setLaunches": False, "setTimeoutS": 30, "choices": [
        _choice("alacritty", "Alacritty", command="alacritty", desktop="Alacritty.desktop", package=("alacritty", "pacman")),
        _choice("foot", "Foot", command="foot", desktop="foot.desktop", package=("foot", "pacman")),
        _choice("ghostty", "Ghostty", command="ghostty", desktop="com.mitchellh.ghostty.desktop", package=("ghostty", "pacman")),
        _choice("kitty", "Kitty", command="kitty", desktop="kitty.desktop", package=("kitty", "pacman")),
     ]},
    {"id": "editor", "label": "Editor", "summary": "Editor used by omarchy-launch-editor",
     "selector": "omarchy-default-editor", "route": "omarchy default editor",
     "stateSource": {"kind": "file", "path": "~/.local/state/omarchy/defaults/editor"},
     "stateFile": "~/.local/state/omarchy/defaults/editor", "emptyOutputMeans": None,
     "defaultChoice": "nvim", "installedPredicate": "path", "setLaunches": False, "setTimeoutS": 30,
     "choices": [
        _choice("code", "VSCode", command="code", package=("visual-studio-code-bin", "aur"), launches=True),
        _choice("cursor", "Cursor", command="cursor", package=("cursor-bin", "aur")),
        _choice("zed", "Zed", command="zeditor", reported="zeditor", aliases=("zeditor",), package=("zed", "pacman"), launches=True),
        _choice("sublime_text", "Sublime Text", command="sublime_text", package=("sublime-text-4", "pacman")),
        _choice("helix", "Helix", command="helix", package=("helix", "pacman")),
        _choice("vim", "Vim", command="vim", package=("vim", "pacman")),
        _choice("emacs", "Emacs", command="emacs", package=("omarchy-emacs", "aur"), launches=True),
        _choice("nvim", "Neovim", command="nvim", package=("neovim", "pacman")),
     ]},
    {"id": "agent", "label": "Coding agent", "summary": "Coding agent launched by Omarchy",
     "selector": "omarchy-default-agent", "route": "omarchy default agent",
     "stateSource": {"kind": "file", "path": "~/.config/omarchy/defaults/agent"},
     "stateFile": "~/.config/omarchy/defaults/agent", "emptyOutputMeans": "unset",
     "defaultChoice": None, "installedPredicate": "mise", "setLaunches": True, "setTimeoutS": 60,
     "choices": [
        _choice("agy", "Antigravity", aliases=("antigravity", "antigravity-cli", "gemini", "gemini-cli"), mise="antigravity-cli", sudo=False, launches=True),
        _choice("claude", "Claude Code", aliases=("claude-code",), mise="claude", sudo=False, launches=True),
        _choice("codex", "Codex", mise="codex", sudo=False, launches=True),
        _choice("copilot", "GitHub Copilot", aliases=("github-copilot",), mise="copilot", sudo=False, launches=True),
        _choice("crush", "Crush", mise="crush", sudo=False, launches=True),
        _choice("grok", "Grok", mise="npm:@xai-official/grok", sudo=False, launches=True),
        _choice("omp", "Oh My Pi", aliases=("oh-my-pi",), mise="github:can1357/oh-my-pi", sudo=False, launches=True),
        _choice("opencode", "OpenCode", aliases=("open-code",), mise="opencode", sudo=False, launches=True),
        _choice("ori", "Ori", aliases=("openrouter",), mise="github:OpenRouterLabs/ori-releases", sudo=False, launches=True),
        _choice("pi", "Pi", mise="pi", sudo=False, launches=True),
     ]},
)


def categories() -> list[dict[str, Any]]:
    return [{**category, "choices": [{**choice, "aliases": list(choice["aliases"]),
                                       "installer": dict(choice["installer"]),
                                       "package": dict(choice["package"]) if choice["package"] else None}
                                      for choice in category["choices"]]}
            for category in CATALOG]


def category(category_id: str) -> dict[str, Any] | None:
    return next((item for item in CATALOG if item["id"] == category_id), None)


def choice(category_data: dict[str, Any], choice_id: str) -> dict[str, Any] | None:
    return next((item for item in category_data["choices"] if item["id"] == choice_id), None)
