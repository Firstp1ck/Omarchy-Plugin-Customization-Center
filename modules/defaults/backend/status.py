from __future__ import annotations

from pathlib import Path
from typing import Any

from customization_center.core import Status, Warning

from .catalog import categories
from .probes import (choice_probe, commands_drift, desktop_entry, desktop_name, installed_packages,
                     last_preference, one_line, read_state_file, run, selected_choice)


def _paths(ctx: Any) -> dict[str, Path]:
    return {
        "browser": ctx.paths.xdg_config_home / "mimeapps.list",
        "terminal": ctx.paths.xdg_config_home / "xdg-terminals.list",
        "terminalShadow": ctx.paths.xdg_config_home / "hyprland-xdg-terminals.list",
        "editor": ctx.paths.home / ".local/state/omarchy/defaults/editor",
        "agent": ctx.paths.xdg_config_home / "omarchy/defaults/agent",
    }


def _transaction_categories(tx: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for operation in tx.plan.operations:
        detail = operation.detail or {}
        category_id = str(detail.get("category", ""))
        if category_id:
            result[category_id] = detail
    return result


def _journal_projection(ctx: Any) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    all_pending: list[dict[str, Any]] = []
    pending_by_category: dict[str, dict[str, Any]] = {}
    outcomes: dict[str, dict[str, Any]] = {}
    for tx in ctx.journal.history(module="defaults", limit=100):
        transaction_categories = _transaction_categories(tx)
        if tx.state == "pending_handoff":
            terminal = next((op for op in tx.plan.operations if op.kind == "TerminalHandoff"), None)
            detail = terminal.detail if terminal and terminal.detail else {}
            category_id = str(detail.get("category", ""))
            all_pending.append({"id": tx.id,
                                "sentinelExists": (ctx.paths.state / "handoffs" / (tx.id + ".json")).is_file()})
            if category_id and category_id not in pending_by_category:
                pending_by_category[category_id] = {
                    "transactionId": tx.id, "choice": detail.get("choice", ""),
                    "startedAt": tx.created_at, "argv": terminal.params.get("argv", []) if terminal else [],
                    "lastReconciledAt": tx.updated_at,
                }
        for category_id, detail in transaction_categories.items():
            if category_id in outcomes:
                continue
            if tx.state == "rollback_failed":
                affected_paths = sorted({str(path) for error in tx.rollback_errors
                                         for path in error.get("affectedPaths", [])})
                outcomes[category_id] = {
                    "state": "rollback_failed", "transactionId": tx.id, "choice": detail.get("choice", ""),
                    "reason": tx.reason or "rollback", "failedChecks": [], "paths": affected_paths,
                    "recoveryCommands": [f"ccctl restore {tx.id} --path {path}" for path in affected_paths
                                         if path in tx.backups],
                }
            elif tx.state == "rolled_back" and tx.reason == "verification" and tx.verify:
                code = tx.verify.code or "defaults_verification_failed"
                evidence_category = str(tx.verify.evidence.get("category", ""))
                category_code = code if not evidence_category or evidence_category == category_id else "defaults_verification_failed"
                outcomes[category_id] = {
                    "state": "installed_not_set" if category_code == "defaults_installed_not_set" else "verify_failed",
                    "transactionId": tx.id, "choice": detail.get("choice", ""), "code": category_code,
                    "reason": tx.verify.reason if category_code == code else "Another default failed verification; this change was restored",
                    "failedChecks": tx.verify.evidence.get("failedChecks", []) if category_code == code else [],
                    "paths": [], "recoveryCommands": [],
                }
            else:
                outcomes[category_id] = {"state": "", "transactionId": tx.id}
    return all_pending, pending_by_category, outcomes


def _checks(category_data: dict[str, Any], current: dict[str, Any] | None, raw: dict[str, Any],
            choice_state: dict[str, Any] | None, selector_value: str) -> list[dict[str, Any]]:
    if current is None or choice_state is None:
        return [{"id": "selector", "ok": False, "expected": "known Omarchy choice", "actual": selector_value}]
    expected = current
    checks = [{"id": "selector", "ok": selector_value == expected["reported"],
               "expected": expected["reported"], "actual": selector_value}]
    category_id = category_data["id"]
    if category_id == "browser":
        for check_id, key in (("xdg_default_web_browser", "defaultWebBrowser"), ("xdg_text_html", "textHtml"),
                              ("xdg_http", "http"), ("xdg_https", "https")):
            checks.append({"id": check_id, "ok": raw.get(key) == expected["desktopId"],
                           "expected": expected["desktopId"], "actual": raw.get(key, "")})
    elif category_id == "terminal":
        checks.extend((
            {"id": "xdg_terminal_exec", "ok": raw.get("resolved") == expected["desktopId"],
             "expected": expected["desktopId"], "actual": raw.get("resolved", "")},
            {"id": "preference_file", "ok": raw.get("preference") == expected["desktopId"],
             "expected": expected["desktopId"], "actual": raw.get("preference", "")},
        ))
    elif category_id in {"editor", "agent"}:
        actual = raw.get("firstLine", "")
        if category_id == "editor" and raw.get("exists") is False and expected["reported"] == "nvim":
            actual = "nvim"
        checks.append({"id": "state_file", "ok": actual == expected["reported"],
                       "expected": expected["reported"], "actual": actual})
    if category_id == "agent":
        checks.append({"id": "mise_where", "ok": choice_state["runnable"] is True,
                       "expected": expected["misePackage"], "actual": choice_state["runnable"]})
    else:
        checks.append({"id": "command", "ok": choice_state["runnable"] is True,
                       "expected": expected["command"], "actual": choice_state["commandPath"]})
        if expected["desktopId"]:
            checks.append({"id": "desktop_entry", "ok": choice_state["desktopEntryPath"] is not None,
                           "expected": expected["desktopId"], "actual": choice_state["desktopEntryPath"]})
    return checks


def build_status(ctx: Any) -> Status:
    catalog = categories()
    paths = _paths(ctx)
    packages = installed_packages(ctx)
    drift, drift_warning = commands_drift(ctx, catalog)
    drifted = {item["category"] for item in drift}
    warnings: list[Warning] = []
    if drift_warning:
        warnings.append(Warning("defaults_catalog_unavailable", drift_warning, recovery="Repair omarchy commands or retry"))
    pending_handoffs, pending_by_category, outcomes = _journal_projection(ctx)
    result_categories = []
    revision_categories = []
    for category_data in catalog:
        category_id = category_data["id"]
        selector_result = run(ctx, [category_data["selector"]])
        selector_value, selector_error = one_line(selector_result)
        raw: dict[str, Any] = {}
        raw_error = ""
        if category_id == "browser":
            values = {}
            probes = (("defaultWebBrowser", ["xdg-settings", "get", "default-web-browser"]),
                      ("textHtml", ["xdg-mime", "query", "default", "text/html"]),
                      ("http", ["xdg-mime", "query", "default", "x-scheme-handler/http"]),
                      ("https", ["xdg-mime", "query", "default", "x-scheme-handler/https"]))
            for key, argv in probes:
                probe_value, error = one_line(run(ctx, argv))
                values[key] = probe_value
                raw_error = raw_error or error
            raw = values
            if not raw.get("defaultWebBrowser"):
                raw_error = raw_error or "xdg-settings returned an empty browser"
        elif category_id == "terminal":
            resolver_path = ctx.commands.which("xdg-terminal-exec")
            terminal_result = run(ctx, ["xdg-terminal-exec", "--print-id"])
            terminal_value, terminal_error = one_line(terminal_result)
            resolved = terminal_value.split(":", 1)[0]
            file_state = read_state_file(paths["terminal"])
            raw = {**file_state, "resolved": resolved, "fullOutput": terminal_value,
                   "preference": last_preference(paths["terminal"]), "shadowFile": str(paths["terminalShadow"])}
            if resolver_path is None:
                raw_error = "xdg-terminal-exec is not on PATH"
            elif terminal_result["timedOut"] or terminal_error == "malformed_output":
                raw_error = terminal_error
            if paths["terminalShadow"].is_file():
                warnings.append(Warning("defaults_terminal_shadowed",
                    "A higher-priority terminal preference shadows the Omarchy setting",
                    str(paths["terminalShadow"]), "Remove or update this file, then recheck"))
        else:
            raw = read_state_file(paths[category_id])
        current_choice, normalized_alias = selected_choice(category_data, selector_value, str(raw.get("firstLine", "")))
        choices = [choice_probe(ctx, category_data, item, packages) for item in category_data["choices"]]
        current_state = next((item for item in choices if current_choice and item["id"] == current_choice["id"]), None)
        if selector_error or raw_error:
            state = "probe_error"
        elif current_choice is None and not selector_value:
            state = category_data["emptyOutputMeans"] or "probe_error"
        elif current_choice is None:
            state = "unknown"
        elif current_state and current_state["state"] == "available":
            state = "ready"
        else:
            state = "broken"
        unknown_entry = desktop_entry(ctx, selector_value) if current_choice is None and category_id in {"browser", "terminal"} else None
        current = {"choice": current_choice["id"] if current_choice else None,
                   "reported": current_choice["reported"] if current_choice else selector_value,
                   "raw": raw, "normalisedFromAlias": normalized_alias,
                   "unknownDesktopEntry": unknown_entry, "unknownDesktopName": desktop_name(unknown_entry)}
        checks = _checks(category_data, current_choice, raw, current_state, selector_value)
        error = selector_error or raw_error
        result_categories.append({"id": category_id, "label": category_data["label"],
            "summary": category_data["summary"], "selector": category_data["selector"], "stateFile": str(paths[category_id]),
            "state": state, "default": category_data["defaultChoice"], "current": current, "checks": checks,
            "choices": choices, "pending": pending_by_category.get(category_id),
            "outcome": outcomes.get(category_id) if outcomes.get(category_id, {}).get("state") else None,
            "drifted": category_id in drifted,
            "probeError": {"command": "xdg-terminal-exec" if category_id == "terminal" and raw_error else category_data["selector"], "message": error,
                           "recovery": "Repair the named command or file, then retry status"} if error else None})
        revision_categories.append({"id": category_id, "selector": [selector_result["exitCode"], selector_value],
                                    "raw": raw, "stateFileSha256": read_state_file(paths[category_id])["sha256"],
                                    "runnable": sorted((item["id"], item["runnable"]) for item in choices)})
    data = {"schemaVersion": 1, "catalogBaseline": "omarchy-71b0887c", "catalog": catalog,
            "drift": drift, "warnings": [item.to_json() for item in warnings], "categories": result_categories,
            "pendingHandoffs": pending_handoffs}
    return Status("defaults", ctx.revision_of(revision_categories), data, tuple(warnings), 1)
