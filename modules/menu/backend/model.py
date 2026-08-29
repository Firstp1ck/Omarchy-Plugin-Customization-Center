from __future__ import annotations

from typing import Any

from .jsonc_menu import js_key_order

NORMAL_FIELDS = ("parent", "kind", "icon", "iconFont", "label", "title", "target", "description",
                 "action", "provider", "aliases", "when", "checked", "disabled")


def _truthy(value: Any) -> bool:
    return not (value is None or value is False or value == "" or value == 0)


def normalize(item_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    aliases = fields.get("aliases", [])
    if isinstance(aliases, str):
        aliases = [aliases] if aliases else []
    elif isinstance(aliases, list):
        aliases = [value for value in aliases if _truthy(value)]
    else:
        aliases = []
    parent = fields.get("parent") if "parent" in fields else (item_id.rsplit(".", 1)[0] if "." in item_id else "root")
    if item_id == "root":
        parent = ""
    action = fields.get("action") or ""
    target = fields.get("target") or ""
    return {"parent": parent, "kind": "action" if _truthy(action) else "link" if _truthy(target) else "menu",
            "icon": fields.get("icon") or "", "iconFont": fields.get("iconFont") or "",
            "label": fields.get("label") or item_id, "title": fields.get("title") or "",
            "target": target, "description": fields.get("description") or "", "action": action,
            "provider": fields.get("provider") or "", "aliases": aliases, "when": fields.get("when") or "",
            "checked": fields.get("checked") or "", "disabled": fields.get("disabled") or ""}


def _runtime_entries(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not document:
        return []
    entries = document.get("entries", [])
    by_id = {entry.get("id"): entry for entry in entries}
    return [by_id[key] for key in js_key_order(list(by_id)) if by_id[key].get("valueKind") == "object"]


def _depth(rows: dict[str, dict[str, Any]], item_id: str) -> tuple[int, bool]:
    seen: set[str] = set()
    depth = 0
    current = rows.get(item_id)
    while current and current["fields"].get("parent") not in {"", "root"}:
        parent = current["fields"].get("parent")
        if parent in seen or parent == item_id:
            return depth, True
        seen.add(parent)
        depth += 1
        if depth >= 33:
            return depth, False
        current = rows.get(parent)
    return depth, False


def _has_visible_descendant(rows: dict[str, dict[str, Any]], item_id: str, seen: set[str] | None = None) -> bool:
    walked = set() if seen is None else set(seen)
    if item_id in walked or len(walked) >= 32:
        return False
    walked.add(item_id)
    row = rows.get(item_id)
    if not row:
        return False
    if row["fields"].get("provider"):
        return True
    for child_id in row.get("children", []):
        child = rows[child_id]
        if child["fields"]["kind"] == "action" or child["fields"].get("provider"):
            return True
        if _has_visible_descendant(rows, child_id, walked):
            return True
    return False


def build_effective(default_doc: dict[str, Any] | None, user_doc: dict[str, Any] | None,
                    semantics: str = "full-shadow") -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    base_raw: dict[str, dict[str, Any]] = {}
    for source, document in (("default", default_doc), ("user", user_doc)):
        for entry in _runtime_entries(document):
            item_id = entry["id"]
            fields = entry.get("fields", {})
            normalized = normalize(item_id, fields)
            if item_id not in rows:
                order.append(item_id)
                rows[item_id] = {"id": item_id, "origin": "shipped" if source == "default" else "custom",
                                 "base": None, "user": None, "userDeclared": [], "provenance": {}, "problems": []}
            row = rows[item_id]
            if source == "default":
                base_raw[item_id] = dict(fields)
                row["base"] = normalized
                row["fields"] = dict(normalized)
                row["provenance"] = {key: "default" for key in normalized}
                for key in ("parent", "kind", "label"):
                    if key not in fields:
                        row["provenance"][key] = "inferred"
            else:
                row["user"] = normalized
                row["userDeclared"] = list(entry.get("known", []))
                if row.get("base") is not None:
                    row["origin"] = "shadowed"
                if semantics == "sparse" and row.get("base") is not None:
                    merged = dict(base_raw.get(item_id, {}))
                    merged.update(fields)
                    row["fields"] = normalize(item_id, merged)
                    row["provenance"] = {key: "user" if key in fields else "default" for key in row["fields"]}
                else:
                    row["fields"] = normalized
                    row["provenance"] = {key: "user" if key in fields or key in {"parent", "kind"} else "cleared"
                                         for key in normalized}
    if "root" not in rows:
        root_fields = normalize("root", {"label": "Go"})
        rows["root"] = {"id": "root", "origin": "injected-root", "base": None, "user": None,
                        "userDeclared": [], "fields": root_fields,
                        "provenance": {key: "inferred" for key in root_fields}, "problems": []}
        order.insert(0, "root")
    for index, item_id in enumerate(order):
        row = rows[item_id]
        row["order"] = index
        row["children"] = []
    for item_id in order:
        parent = rows[item_id]["fields"].get("parent")
        if parent in rows:
            rows[parent]["children"].append(item_id)
        elif parent not in {"", "root"}:
            rows[item_id]["problems"].append({"code": "menu_orphan_parent", "message": f"Parent {parent} does not exist"})
    for item_id in order:
        row = rows[item_id]
        depth, cycle = _depth(rows, item_id)
        row["depth"] = depth
        if cycle:
            row["problems"].append({"code": "menu_cycle", "message": "Parent hierarchy contains a cycle"})
        route = item_id.lower().replace("_", "-")
        row["route"] = route
        row["routable"] = route == item_id
        fields = row["fields"]
        row["kind"] = fields["kind"]
        row["parent"] = fields["parent"]
        row["structurallyHidden"] = fields["kind"] in {"menu", "link"} and not fields.get("provider") and not _has_visible_descendant(rows, fields.get("target") or item_id)
    return {"schemaVersion": 1, "semantics": semantics, "order": order, "rows": rows}


def resolve_route(effective: dict[str, Any], value: str) -> dict[str, Any]:
    raw = str(value or "").lower().replace("_", "-")
    rows = effective.get("rows", {})
    if raw in {"", "go", "menu"}:
        resolved, via = "root", "root"
    elif raw in rows:
        resolved, via = raw, "id"
    else:
        resolved, via = raw, "literal"
        for item_id in effective.get("order", []):
            row = rows[item_id]
            if row.get("kind") == "app":
                continue
            aliases = row.get("fields", {}).get("aliases", [])
            if any(str(alias or "").lower().replace("_", "-") == raw for alias in aliases):
                resolved, via = item_id, "alias"
                break
    row = rows.get(resolved)
    return {"schemaVersion": 1, "input": value, "resolved": resolved, "via": via,
            "kind": row.get("kind") if row else None,
            "wouldRunAction": bool(row and row.get("fields", {}).get("action"))}


def search_tokens(effective: dict[str, Any], item_id: str) -> dict[str, Any]:
    row = effective.get("rows", {}).get(item_id)
    if not row:
        return {"schemaVersion": 1, "id": item_id, "label": "", "leafTokens": [], "aliases": [], "descriptionWords": []}
    fields = row["fields"]
    leaf = item_id.rsplit(".", 1)[-1]
    return {"schemaVersion": 1, "id": item_id, "label": fields.get("label", ""),
            "leafTokens": [token for token in leaf.replace("_", " ").replace("-", " ").split() if token],
            "aliases": fields.get("aliases", []),
            "descriptionWords": fields.get("description", "").split()}
