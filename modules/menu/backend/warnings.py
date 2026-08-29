from __future__ import annotations

import hashlib
import re
from typing import Any


_RULES = (
    ("menu_exec_elevated", r"(^|[\s;&|(])(sudo|doas|pkexec|su)(\s|$)|\bsystemctl\b(?!\s+--user)|\b(pacman|yay|paru)\s+-[A-Za-z]*[SRU]|\b(chown|chmod)\s+(-[A-Za-z]*R|--recursive)|(^|[\s>])/(etc|usr|boot|var/lib)/", "Needs privileges or writes system paths"),
    ("menu_exec_destructive", r"\brm\s+(-[A-Za-z]*[rRf]\b|--recursive|--force)|\b(mkfs(?:\.\w+)?|dd|shred|wipefs|fdisk|sfdisk|parted|cryptsetup)\b|\b(shutdown|reboot|poweroff|halt)\b|systemctl\s+(poweroff|reboot|halt|kexec|suspend|hibernate)|omarchy-system-(factory-reset|reboot|shutdown|logout)|\b(killall|pkill\s+-9|kill\s+-9)\b|>\s*/dev/(sd|nvme|vd|mmcblk)|:\s*\(\)\s*\{", "Can delete data, power off, or kill processes"),
    ("menu_exec_remote_code", r"\b(curl|wget)\b[^|;&]*\|\s*(sudo\s+)?(ba)?sh\b|\beval\b|(^|[\s;&|])(source|\.)\s+\S", "Executes downloaded or evaluated text"),
)
_COMPLEX = re.compile(r";|\||&&|\|\||&|>|<|\$\(|`|<\(|>\(|\$\{|\$[A-Za-z_]|\n")
_SLOW = re.compile(r"\b(sleep|curl|wget|ping|ssh|scp|rsync|git\s+(pull|fetch|clone)|pacman\s+-S[yu]|yay|paru|flatpak\s+(update|install)|docker\s+(pull|run))\b")
_WRITES = re.compile(r"\b(rm|mv|cp|touch|mkdir|tee|sed\s+-i)\b|(^|[^<>])>{1,2}\s*(?!&2\b|/dev/null\b)[^&\s]", re.MULTILINE)


def acknowledgement_key(draft_id: str, field: str, text: str) -> str:
    return hashlib.sha256((draft_id + field + text).encode("utf-8")).hexdigest()


def classify(field: str, text: str, draft_id: str = "") -> list[dict[str, Any]]:
    if not text:
        return []
    found: list[dict[str, Any]] = []
    is_guard = field in {"when", "checked", "disabled"}
    category = "menu_exec_guard" if is_guard else "menu_exec_action"
    found.append({"code": category, "message": "Runs on every shell reload and menu open without selecting the row" if is_guard else "Runs as bash -lc when selected",
                  "field": field, "match": text, "ack": is_guard,
                  "key": acknowledgement_key(draft_id, field, text)})
    for code, pattern, message in _RULES:
        match = re.search(pattern, text)
        if match:
            found.append({"code": code, "message": message, "field": field, "match": match.group(0), "ack": True,
                          "key": acknowledgement_key(draft_id, field, text)})
    if _COMPLEX.search(text):
        found.append({"code": "menu_exec_complex", "message": "Contains pipes, redirects, substitutions, or multiple commands",
                      "field": field, "match": _COMPLEX.search(text).group(0), "ack": False,
                      "key": acknowledgement_key(draft_id, field, text)})
    if is_guard:
        match = _SLOW.search(text)
        if match:
            found.append({"code": "menu_slow_guard", "message": "Looks slow or network-bound; the menu waits on this on every reload",
                          "field": field, "match": match.group(0), "ack": True,
                          "key": acknowledgement_key(draft_id, field, text)})
        match = _WRITES.search(text)
        if match:
            found.append({"code": "menu_guard_writes", "message": "A guard that changes files runs on every reload",
                          "field": field, "match": match.group(0), "ack": True,
                          "key": acknowledgement_key(draft_id, field, text)})
    return found
