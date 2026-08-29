from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

MOD_BITS = {"SUPER": 64, "WIN": 64, "LOGO": 64, "MOD4": 64,
            "CTRL": 4, "CONTROL": 4, "ALT": 8, "SHIFT": 1}
MOD_ORDER = (("SUPER", 64), ("CTRL", 4), ("ALT", 8), ("SHIFT", 1))
DISPLAY_ALIASES = {"grave": "~", "comma": ",", "period": ".", "slash": "/", "minus": "-",
                   "equal": "=", "space": "Space", "Return": "Enter", "BackSpace": "Backspace",
                   "Prior": "Page Up", "Next": "Page Down"}
_CANONICAL = {
    "tab": "Tab", "return": "Return", "enter": "Return", "kp_enter": "KP_Enter", "space": "space",
    "escape": "Escape", "esc": "Escape", "backspace": "BackSpace", "delete": "Delete", "insert": "Insert",
    "home": "Home", "end": "End", "pageup": "Prior", "prior": "Prior", "pagedown": "Next", "next": "Next",
    "left": "Left", "right": "Right", "up": "Up", "down": "Down", "print": "Print", "menu": "Menu",
    "pause": "Pause", "scroll_lock": "Scroll_Lock", "comma": "comma", "period": "period", "slash": "slash",
    "semicolon": "semicolon", "apostrophe": "apostrophe", "bracketleft": "bracketleft",
    "bracketright": "bracketright", "backslash": "backslash", "minus": "minus", "equal": "equal",
    "grave": "grave", "iso_left_tab": "ISO_Left_Tab",
}


@dataclass(frozen=True)
class ChordError(ValueError):
    code: str
    message: str


def _canonical_keysym(value: str, known: dict[str, str] | None = None) -> str | None:
    if known:
        for candidate in (value, value.lower(), value.capitalize(), "XF86" + value[4:] if value.lower().startswith("xf86") else value):
            found = known.get(candidate) or known.get(candidate.casefold())
            if found:
                return found
    folded = value.casefold()
    if folded in _CANONICAL:
        return _CANONICAL[folded]
    if len(value) == 1 and value.isascii() and value.isalnum():
        return value.lower() if value.isalpha() else value
    if re.fullmatch(r"F(?:[1-9]|[12][0-9]|3[0-5])", value, re.I):
        return value.upper()
    if re.fullmatch(r"XF86[A-Za-z0-9_]+", value, re.I):
        return "XF86" + value[4:]
    return None


def identity_text(modmask: int, kind: str, value: Any) -> str:
    normalized = str(value).casefold() if kind == "keysym" else str(value)
    return f"{int(modmask)}:{kind}:{normalized}"


def normalize(text: str, known: dict[str, str] | None = None,
              code_to_keysym: dict[int, str] | None = None) -> dict[str, Any]:
    if not isinstance(text, str):
        raise ChordError("keybindings_chord_grammar", "Chord must be text")
    value = text.strip()
    if not value or any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in value):
        raise ChordError("keybindings_chord_grammar", "Chord contains an empty or control character")
    parts = [part.strip() for part in value.split("+")]
    if any(not part for part in parts):
        raise ChordError("keybindings_chord_grammar", "Chord has an empty part")
    key = parts[-1]
    mask = 0
    for modifier in parts[:-1]:
        bit = MOD_BITS.get(modifier.upper())
        if bit is None:
            raise ChordError("keybindings_unsupported_modifier", f"Unsupported modifier: {modifier}")
        if mask & bit:
            raise ChordError("keybindings_chord_grammar", f"Duplicate modifier: {modifier}")
        mask |= bit
    lower = key.lower()
    if re.fullmatch(r"code:\d+", lower):
        number = int(lower[5:])
        if number < 8 or number > 255:
            raise ChordError("keybindings_chord_grammar", "Keycode must be between 8 and 255")
        kind, canonical, token = "code", number, f"code:{number}"
        mapped_keysym = (code_to_keysym or {}).get(number)
    elif (re.fullmatch(r"mouse:\d+", lower) or lower in {"mouse_up", "mouse_down", "mouse_left", "mouse_right"}
          or lower.startswith("switch:") or lower == "catchall"):
        raise ChordError("keybindings_unsupported_key", f"This key domain is read-only: {key}")
    elif not re.fullmatch(r"[A-Za-z0-9_]+", key):
        raise ChordError("keybindings_chord_grammar", "Key names may contain letters, digits, and underscores")
    else:
        resolved = _canonical_keysym(key, known)
        if resolved is None:
            raise ChordError("keybindings_unknown_keysym", f"Unknown keysym: {key}")
        kind, canonical = "keysym", resolved
        mapped_keysym = None
        token = resolved.upper() if len(resolved) == 1 and resolved.isascii() and resolved.isalpha() else resolved
    modifiers = [name for name, bit in MOD_ORDER if mask & bit]
    source = " + ".join([*modifiers, token])
    display_token = DISPLAY_ALIASES.get(str(canonical), token)
    display = " + ".join([*modifiers, display_token])
    return {"sourceKeys": source, "identity": identity_text(mask, kind, canonical), "display": display,
            "keyKind": kind, "keyValue": canonical, "modmask": mask, "modifiers": modifiers,
            "key": {"kind": kind, "value": canonical}, "mappedKeysym": mapped_keysym}


def from_model(chord: dict[str, Any], code_to_keysym: dict[int, str] | None = None) -> dict[str, Any]:
    modifiers = chord.get("modifiers", [])
    key = chord.get("key", {})
    value = key.get("value")
    text = " + ".join([*(str(item) for item in modifiers), f"code:{value}" if key.get("kind") == "code" else str(value)])
    return normalize(text, code_to_keysym=code_to_keysym)


def runtime_identity(modmask: int, key_token: str, keycode: int = 0) -> tuple[str, str, str]:
    token = key_token or (f"code:{keycode}" if keycode else "")
    try:
        parsed = normalize(" + ".join([*(name for name, bit in MOD_ORDER if modmask & bit), token]))
        return parsed["identity"], parsed["display"], parsed["keyKind"]
    except ChordError:
        return identity_text(modmask, "unknown", token), " + ".join([*(name for name, bit in MOD_ORDER if modmask & bit), token]), "unknown"
