from __future__ import annotations

import json
import shlex
from typing import Any


def payload(mode_id: str, action: str = "review") -> dict[str, Any]:
    return {"module": "modes", "modeId": mode_id, "action": action}


def command(mode_id: str, action: str = "review") -> str:
    document = json.dumps(payload(mode_id, action), separators=(",", ":"), ensure_ascii=False)
    return " ".join(shlex.quote(item) for item in ("omarchy-shell", "shell", "summon", "firstpick.customization-center", document))


def keybinding(mode: dict[str, Any], chord: Any = None) -> dict[str, Any]:
    return {"addBinding": {"chord": chord, "description": f"Mode: {mode['name']}",
            "action": {"type": "exec", "command": command(mode["id"])}}}


def menu(mode: dict[str, Any]) -> dict[str, Any]:
    return {"addEntry": {"parent": "modes", "label": mode["name"], "action": command(mode["id"])}}
