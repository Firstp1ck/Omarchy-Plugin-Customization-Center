from __future__ import annotations

CONFIRMATIONS = {
    "add": "Open a terminal to add a plugin. Omarchy will warn that plugins run unsandboxed and will ask before enabling it.",
    "update": "Open a terminal to review and update this plugin. Updates are not reversible by the Customization Center.",
    "remove": "Open a terminal to remove this plugin. The command may delete a checkout after confirmation and is not reversible here.",
    "clone": "Clone and switch to this plugin. The clone is enabled immediately; undo by removing the clone.",
    "clone-edit": "Clone, switch, and open this plugin in the configured editor. This is not reversible here.",
}

SELF_CLOSE = "The Customization Center will close. Re-enable it with `omarchy plugin enable firstpick.customization-center`."


def confirmation(action: str, *, self_action: bool = False) -> str:
    text = CONFIRMATIONS[action]
    return f"{text} {SELF_CLOSE}" if self_action else text
