from __future__ import annotations

import copy
import json
from dataclasses import replace
from typing import Any

from customization_center.core import CcError, Plan, ResourceClaim, Warning, ops
from .model import SECTIONS, all_entries, counts, serialize_entry, to_shell


def _same(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True, separators=(",", ":"), ensure_ascii=False) == json.dumps(b, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _catalog(status: Any) -> dict[str, dict[str, Any]]:
    return {item.get("id"): item for item in status.data.get("catalog", [])}


def route_reasons(base: dict[str, Any], draft: dict[str, Any], status: Any) -> list[str]:
    reasons: list[str] = []
    for key in ("id", "position", "transparent", "centerAnchor", "extra"):
        if not _same(base.get(key), draft.get(key)):
            reasons.append(key)
    base_counts, draft_counts = counts(base), counts(draft)
    if any(value > max(base_counts.get(widget_id, 0), 1) for widget_id, value in draft_counts.items()):
        reasons.append("repeated instance")
    catalog = _catalog(status)
    origins = {(entry.get("origin", {}).get("section"), entry.get("origin", {}).get("index")): entry
               for _, _, entry in all_entries(draft) if isinstance(entry.get("origin"), dict)}
    for section, index, old in all_entries(base):
        current = origins.get((section, index))
        item = catalog.get(old.get("id"), {})
        if current is None:
            if item.get("presence") != "shell": reasons.append("layout-only removal")
            if item.get("clonedFrom") or item.get("activeCloneId"): reasons.append("clone relationship")
        else:
            if set(old.get("settings", {})) - set(current.get("settings", {})): reasons.append("setting deletion")
            if old.get("form") == "string" and current.get("settings"): reasons.append("string entry settings")
    for _, _, entry in all_entries(draft):
        if entry.get("origin") is None:
            item = catalog.get(entry.get("id"), {})
            if item.get("clonedFrom") or item.get("activeCloneId"): reasons.append("clone relationship")
    return list(dict.fromkeys(reasons))


def _ipc(ctx: Any, method: str, args: tuple[Any, ...], summary: str, shell_path: str, inverse=None, detail=None):
    return ops.ShellIpc(ctx, method, args, expect=("ok",), backup_paths=(shell_path,), inverse=inverse,
                        summary=summary, detail=detail)


def _locate(layout: dict[str, list[dict[str, Any]]], marker: Any):
    for section in SECTIONS:
        for index, item in enumerate(layout[section]):
            if item.get("_marker") == marker:
                return section, index
    return None


def _first(layout: dict[str, list[dict[str, Any]]], widget_id: str):
    for section in SECTIONS:
        for index, item in enumerate(layout[section]):
            if item.get("id") == widget_id:
                return section, index
    return None


def _move(layout, source, target):
    item = layout[source[0]].pop(source[1]); index = min(target[1], len(layout[target[0]])); layout[target[0]].insert(index, item)
    return target[0], index


def ipc_operations(ctx: Any, base: dict[str, Any], draft: dict[str, Any], status: Any, shell_path: str):
    operations = []
    target_by_origin = {(entry["origin"]["section"], entry["origin"]["index"]): entry
                        for _, _, entry in all_entries(draft) if isinstance(entry.get("origin"), dict)}
    working = {section: [] for section in SECTIONS}
    removed = []
    for section, index, old in all_entries(base):
        target = target_by_origin.get((section, index))
        marker = target.get("key") if target else f"removed:{section}:{index}"
        item = copy.deepcopy(old); item["_marker"] = marker; working[section].append(item)
        if target is None: removed.append((section, index, marker, item))
    order = {"right": 0, "center": 1, "left": 2}
    removed.sort(key=lambda item: (order[item[0]], -item[1]))
    for _, _, marker, old in removed:
        source = _locate(working, marker); assert source is not None
        if _first(working, old["id"]) != source:
            inverse = _ipc(ctx, "moveBarWidget", (old["id"], {"fromSection": "left", "fromIndex": 0, "section": source[0], "index": source[1]}), "Restore removed widget position", shell_path)
            move = _ipc(ctx, "moveBarWidget", (old["id"], {"fromSection": source[0], "fromIndex": source[1], "section": "left", "index": 0}), f"Move {old['id']} for exact removal", shell_path, inverse)
            operations.append(move); _move(working, source, ("left", 0))
        remove_at = _first(working, old["id"]); assert remove_at is not None
        restore_ops = [_ipc(ctx, "enablePlugin", (old["id"], {"section": remove_at[0], "index": remove_at[1]}), f"Restore {old['id']}", shell_path)]
        for key, value in old.get("settings", {}).items():
            restore_ops.append(_ipc(ctx, "setBarWidget", (old["id"], key, value, {"section": remove_at[0], "index": remove_at[1]}), f"Restore {old['id']} {key}", shell_path))
        disable = _ipc(ctx, "setPluginEnabled", (old["id"], "false"), f"Remove {old['id']} from {remove_at[0]}[{remove_at[1]}]", shell_path)
        disable = replace(disable, inverse=tuple(replace(item, inverse=()) for item in restore_ops))
        operations.append(disable); working[remove_at[0]].pop(remove_at[1])
    for section in SECTIONS:
        for index, target in enumerate(draft["layout"][section]):
            marker = target["key"]; source = _locate(working, marker)
            if source is None:
                remove_inverse = _ipc(ctx, "setPluginEnabled", (target["id"], "false"), f"Remove added {target['id']}", shell_path)
                add = _ipc(ctx, "enablePlugin", (target["id"], {"section": section, "index": index}), f"Add {target['id']} to {section}[{index}]", shell_path, remove_inverse)
                operations.append(add)
                working[section].insert(index, {"id": target["id"], "settings": {}, "form": "object", "_marker": marker})
            elif source != (section, index):
                inverse = _ipc(ctx, "moveBarWidget", (target["id"], {"fromSection": section, "fromIndex": index, "section": source[0], "index": source[1]}), f"Restore {target['id']} position", shell_path)
                move = _ipc(ctx, "moveBarWidget", (target["id"], {"fromSection": source[0], "fromIndex": source[1], "section": section, "index": index}), f"Move {target['id']} to {section}[{index}]", shell_path, inverse)
                operations.append(move); _move(working, source, (section, index))
    approximate: list[str] = []
    for section in SECTIONS:
        for index, target in enumerate(draft["layout"][section]):
            current = working[section][index].get("settings", {})
            for key, value in target.get("settings", {}).items():
                if key in current and _same(current[key], value): continue
                if target.get("origin") is None:
                    inverse = ()
                elif key in current:
                    inverse = _ipc(ctx, "setBarWidget", (target["id"], key, current[key], {"section": section, "index": index}), f"Restore {target['id']} {key}", shell_path)
                else:
                    inverse = _ipc(ctx, "setBarWidget", (target["id"], key, None, {"section": section, "index": index}), f"Approximate restore of {target['id']} {key}", shell_path)
                    approximate.append(f"{target['id']}.{key}")
                setting = _ipc(ctx, "setBarWidget", (target["id"], key, value, {"section": section, "index": index}), f"Set {target['id']} {key} at {section}[{index}]", shell_path, inverse)
                if inverse == (): setting = replace(setting, inverse=())
                operations.append(setting); current[key] = copy.deepcopy(value)
    simulated = {section: [serialize_entry(item) for item in working[section]] for section in SECTIONS}
    expected = {section: [serialize_entry(item) for item in draft["layout"][section]] for section in SECTIONS}
    if not _same(simulated, expected):
        raise CcError("bar_plan_mismatch", "IPC simulation did not produce the requested layout", {"simulated": simulated, "expected": expected})
    return tuple(operations), approximate


def build_plan(ctx: Any, draft: dict[str, Any], status: Any) -> Plan:
    if draft.get("baseRevision") != status.revision:
        raise CcError("stale_revision", "The bar changed since this draft was created")
    base, target = status.data["bar"], draft["bar"]
    action = draft.get("action", "apply")
    if action in {"save-preset", "delete-preset"}:
        preset_id = draft["presetId"]
        preset_path = ctx.paths.module_config("bar") / "presets" / f"{preset_id}.json"
        existing = next((item for item in status.data.get("presets", []) if item.get("id") == preset_id), None)
        warning: Warning | None = None
        if action == "save-preset":
            document = {"schemaVersion": 1, "id": preset_id, "name": draft["presetName"].strip(),
                        "bar": to_shell(target)}
            operations = (ops.EnsureDirectory(ctx, preset_path.parent, "0700", "Ensure bar preset directory"),
                          ops.WriteFileAtomic(ctx, preset_path,
                              json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
                              "0600", "Save bar preset", detail={"presetAction": "save", "preset": document}))
            if existing is not None:
                warning = Warning(f"bar_preset_replace:{preset_id}", f"Replace bar preset {preset_id}",
                                  str(preset_path), "Confirm the named preset replacement", True)
        else:
            if existing is None:
                raise CcError("bar_preset_missing", f"Bar preset does not exist: {preset_id}")
            operations = (ops.RemoveFile(ctx, preset_path, f"Delete bar preset {preset_id}",
                                         detail={"presetAction": "delete", "presetId": preset_id}),)
            warning = Warning(f"bar_preset_delete:{preset_id}", f"Delete bar preset {preset_id}",
                              str(preset_path), "Confirm the named preset deletion", True)
        warnings = (warning,) if warning else ()
        confirmations = (warning.code,) if warning else ()
        return Plan("bar", status.revision, operations,
                    (ResourceClaim(f"file:{preset_path}", "exclusive"),),
                    f"{action.replace('-', ' ').title()} {preset_id}", warnings, confirmations)
    if not status.data.get("shell", {}).get("available"):
        raise CcError("capability_missing", "The Omarchy shell must be running before applying", {"capability": "applyFile"})
    if status.data.get("shell", {}).get("scanning"):
        raise CcError("bar_scan_in_progress", "The shell plugin scan is still in progress")
    reasons = route_reasons(base, target, status)
    shell_path = str(ctx.paths.home / ".config/omarchy/shell.json")
    warnings: list[Warning] = []
    expected = to_shell(target, omit_empty_anchor=True, base_had_anchor="centerAnchor" in status.data.get("rawShellConfig", {}).get("bar", {}))
    before = to_shell(base, omit_empty_anchor=True, base_had_anchor="centerAnchor" in status.data.get("rawShellConfig", {}).get("bar", {}))
    if reasons:
        capability = status.data.get("capabilities", {}).get("applyFile", {})
        if not capability.get("available"):
            raise CcError("capability_missing", capability.get("reason") or "File route is unavailable", {"capability": "applyFile"})
        document = copy.deepcopy(status.data.get("rawShellConfig", {})); document["version"] = 1; document["bar"] = expected
        if "plugins" not in document: document["plugins"] = []
        content = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        first = ops.ShellIpc(ctx, "reloadConfig", (), inverse=ops.ShellIpc(ctx, "reloadConfig", (), inverse=(), summary="Reload restored shell configuration"), summary="Synchronize shell configuration before write")
        write = ops.WriteFileAtomic(ctx, shell_path, content, "0644", summary="Write the complete bar configuration",
                                    detail={"route": "file", "before": before, "expected": expected})
        last = ops.ShellIpc(ctx, "reloadConfig", (), inverse=ops.ShellIpc(ctx, "reloadConfig", (), inverse=(), summary="Reload during rollback"), summary="Reload the new bar configuration")
        operations = (first, write, last); route = "file"; rollback_exact = True
        warnings.append(Warning("bar_route_file", "Apply uses shell.json because IPC cannot express: " + ", ".join(reasons), shell_path, "The file is backed up and reloadConfig runs after the write"))
        if not status.data.get("file", {}).get("exists"):
            warnings.append(Warning("bar_file_created", "Applying creates shell.json and stops inheriting future shipped defaults", shell_path, "Undo removes the newly created file"))
    else:
        operations, approximate = ipc_operations(ctx, base, target, status, shell_path); route = "ipc"; rollback_exact = not approximate
        if approximate:
            warnings.append(Warning("bar_rollback_approximate", "Rollback writes null for newly added keys: " + ", ".join(approximate), shell_path, "Choose the file route for an exact rollback"))
    detail = {"route": route, "expected": {"bar": expected}, "before": {"bar": before},
              "rollbackExact": rollback_exact, "reasons": reasons}
    operations = tuple(replace(item, detail={**(item.detail or {}), **detail}) if index == 0 else item for index, item in enumerate(operations))
    return Plan("bar", status.revision, operations, (ResourceClaim("shell.bar", "exclusive"),),
                f"Apply bar layout through {route} ({len(operations)} operations)", tuple(warnings), ())
