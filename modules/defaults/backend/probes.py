from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .catalog import choice


def run(ctx: Any, argv: list[str], timeout: float = 5) -> dict[str, Any]:
    result = ctx.commands.run(argv, timeout_s=timeout, env_extra={"BROWSER": None}, capture_limit=65536)
    return {"exitCode": result.exit_code, "stdout": result.stdout, "stderr": result.stderr,
            "timedOut": result.timed_out, "truncated": result.truncated}


def one_line(result: dict[str, Any]) -> tuple[str, str]:
    if result["timedOut"]:
        return "", "timeout"
    if result["exitCode"] != 0:
        return "", result["stderr"].strip() or "command failed"
    text = result["stdout"]
    lines = text.splitlines()
    if len(lines) > 1:
        return "", "malformed_output"
    return (lines[0] if lines else ""), ""


def read_state_file(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return {"exists": False, "firstLine": "", "sha256": None}
    text = data.decode("utf-8", "replace")
    return {"exists": True, "firstLine": text.splitlines()[0] if text.splitlines() else "",
            "sha256": hashlib.sha256(data).hexdigest()}


def last_preference(path: Path) -> str:
    state = read_state_file(path)
    if not state["exists"]:
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    values = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]
    return values[-1] if values else ""


def desktop_entry(ctx: Any, desktop_id: str | None) -> str | None:
    if not desktop_id:
        return None
    env = ctx.commands.environ
    roots = [Path(env.get("XDG_DATA_HOME", str(ctx.paths.home / ".local/share")))]
    roots.extend(Path(item) for item in env.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":") if item)
    for root in roots:
        candidate = root / "applications" / desktop_id
        if candidate.is_file():
            return str(candidate)
    return None


def desktop_name(path: str | None) -> str:
    if not path:
        return ""
    try:
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("Name="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def installed_packages(ctx: Any) -> set[str]:
    result = run(ctx, ["pacman", "-Qq"])
    if result["exitCode"] != 0 or result["timedOut"]:
        return set()
    return {line.strip() for line in result["stdout"].splitlines() if line.strip()}


def choice_probe(ctx: Any, category_data: dict[str, Any], item: dict[str, Any], packages: set[str]) -> dict[str, Any]:
    command_path = None
    if category_data["installedPredicate"] == "path":
        command_path = ctx.commands.which(item["command"]) if item["command"] else None
        runnable: bool | None = command_path is not None
    elif ctx.commands.which("mise") is None:
        runnable = None
    else:
        result = run(ctx, ["mise", "where", item["misePackage"]])
        runnable = result["exitCode"] == 0 and not result["timedOut"]
    desktop_path = desktop_entry(ctx, item["desktopId"])
    integration_required = bool(item["desktopId"])
    wrapper = False
    if category_data["id"] == "agent":
        wrapper_path = ctx.paths.home / ".local/bin" / item["id"]
        try:
            wrapper = ('mise use -g --quiet "' + item["misePackage"] + '"') in wrapper_path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError, UnicodeDecodeError):
            wrapper = False
    if runnable is None:
        state = "unprobed"
    elif not runnable:
        state = "missing"
    elif integration_required and desktop_path is None:
        state = "degraded"
    else:
        state = "available"
    package = dict(item["package"]) if item["package"] else None
    if package is not None:
        package["installed"] = package["name"] in packages
    return {"id": item["id"], "label": item["label"], "reported": item["reported"],
            "state": state, "runnable": runnable, "commandPath": command_path,
            "desktopEntryPath": desktop_path, "integration": {"wrapper": wrapper} if category_data["id"] == "agent" else None,
            "package": package, "installer": dict(item["installer"]), "desktopId": item["desktopId"],
            "misePackage": item["misePackage"], "command": item["command"], "aliases": list(item["aliases"])}


def commands_drift(ctx: Any, catalog: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    result = run(ctx, ["omarchy", "commands", "--json"])
    if result["timedOut"] or result["exitCode"] != 0:
        return [], result["stderr"].strip() or "omarchy commands --json is unavailable"
    try:
        document = json.loads(result["stdout"])
        entries = document.get("commands", [])
    except (json.JSONDecodeError, AttributeError):
        return [], "omarchy commands --json returned malformed output"
    drift = []
    for category_data in catalog:
        entry = next((row for row in entries if row.get("route") == category_data["route"]), None)
        actual = str(entry.get("args", "")) if entry else ""
        actual_ids = [part for part in actual.strip("[]").split("|") if part]
        expected_ids = [item["id"] for item in category_data["choices"]]
        if set(actual_ids) != set(expected_ids):
            drift.append({"category": category_data["id"], "expected": expected_ids, "actual": actual_ids})
    return drift, ""


def selected_choice(category_data: dict[str, Any], reported: str, raw_line: str = "") -> tuple[dict[str, Any] | None, bool]:
    found = next((item for item in category_data["choices"] if item["reported"] == reported), None)
    if found:
        return found, False
    for item in category_data["choices"]:
        if raw_line in item["aliases"]:
            return item, True
    return None, False
