from __future__ import annotations

import difflib
import hashlib
import json
from dataclasses import replace
from typing import Any

from customization_center.core import (
    Capabilities, Capability, CcError, Plan, ResourceClaim, Status, ValidationResult, VerifyResult, Warning, ops,
)

from .jsonc_menu import document_value, parse_runtime, parse_with_parity
from .model import build_effective, resolve_route, search_tokens
from .model_versions import describe
from .validate import validate_draft
from .warnings import classify
from .writer import authored_value, is_canonical, render


def _read(path: Any) -> tuple[bytes | None, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        info = path.stat()
        return raw, {"exists": True, "size": len(raw), "mode": info.st_mode & 0o777,
                     "sha256": hashlib.sha256(raw).hexdigest()}
    except FileNotFoundError:
        return None, {"exists": False, "size": 0, "mode": None, "sha256": None}
    except OSError as error:
        return None, {"exists": True, "size": 0, "mode": None, "sha256": None, "readError": str(error)}


def _source(path: Any, raw: bytes | None, info: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any], list[dict[str, Any]]]:
    if raw is None:
        if info.get("exists"):
            document, parse_state, diagnostics = None, "failed", [{"code": "menu_unparseable", "severity": "error", "path": "", "jsonPath": None, "line": None, "column": None, "message": info.get("readError", "file is unreadable")}]
        else:
            document, parse_state, diagnostics = parse_with_parity(b"")
    else:
        document, parse_state, diagnostics = parse_with_parity(raw)
    runtime_value, _ = parse_runtime(raw or b"")
    runtime_source = runtime_value.get("items") if isinstance(runtime_value, dict) and isinstance(runtime_value.get("items"), dict) else runtime_value
    runtime_count = sum(1 for value in runtime_source.values() if isinstance(value, dict)) if isinstance(runtime_source, dict) else 0
    source = {"schemaVersion": 1, "path": str(path), **{key: info.get(key) for key in ("exists", "size", "mode", "sha256")},
              "parse": parse_state, "runtimeEntryCount": runtime_count}
    for diagnostic in diagnostics:
        diagnostic["path"] = str(path)
    return document, source, diagnostics


class MenuModule:
    id = "menu"
    schema_version = 1

    def _paths(self, ctx: Any) -> tuple[Any, Any, Any]:
        return (ctx.paths.omarchy_path / "default/omarchy/omarchy-menu.jsonc",
                ctx.paths.home / ".config/omarchy/extensions/omarchy-menu.jsonc",
                ctx.paths.omarchy_path / "shell/plugins/menu/MenuModel.js")

    def _model_info(self, ctx: Any) -> tuple[str, dict[str, Any]]:
        model_path = self._paths(ctx)[2]
        raw, _ = _read(model_path)
        model_hash = hashlib.sha256(raw).hexdigest() if raw is not None else ""
        return model_hash, describe(model_hash)

    def capabilities(self, ctx: Any) -> Capabilities:
        _, user_path, _ = self._paths(ctx)
        model_hash, model_info = self._model_info(ctx)
        bash = ctx.commands.which("bash") is not None
        menu_command = ctx.commands.which("omarchy-menu") is not None
        ctx.commands.allow_readonly(("omarchy-menu", "ping"))
        ctx.commands.allow_readonly(("bash", "--noprofile", "--norc", "-n"))
        reachable = False
        shell_detail = "omarchy-menu is not on PATH"
        if menu_command:
            result = ctx.commands.run(["omarchy-menu", "ping"], timeout_s=5, capture_limit=1024)
            output = result.stdout.strip()
            reachable = not result.timed_out and result.exit_code == 0 and output == "ok"
            if reachable:
                shell_detail = "ok"
            elif output == "unknown":
                shell_detail = "menu plugin is not loaded"
            elif output == "error":
                shell_detail = "menu plugin ping failed"
            elif result.timed_out:
                shell_detail = "menu ping timed out"
            else:
                shell_detail = result.stderr.strip().splitlines()[0] if result.stderr.strip() else output or "menu ping failed"
        writable = ctx.paths.symlink_safe(user_path)
        items = (
            Capability("shell", reachable, shell_detail, True, ("omarchy-menu", "ping")),
            Capability("bash", bash, "" if bash else "bash_missing", True, ("bash", "--noprofile", "--norc", "-n")),
            Capability("can_write", writable, "" if writable else "menu file path contains a symlink"),
            Capability("model_recognized", bool(model_info["modelRecognized"]), "" if model_info["modelRecognized"] else f"unrecognized model hash {model_hash or 'missing'}"),
            Capability("sparse_overrides", model_info["overrideSemantics"] == "sparse",
                       "installed model uses full-entry shadows" if model_info["overrideSemantics"] != "sparse" else ""),
        )
        return Capabilities(self.id, items, ctx.clock.now_iso())

    def status(self, ctx: Any) -> Status:
        default_path, user_path, _ = self._paths(ctx)
        default_raw, default_info = _read(default_path)
        user_raw, user_info = _read(user_path)
        default_doc, default_source, default_diagnostics = _source(default_path, default_raw, default_info)
        user_doc, user_source, user_diagnostics = _source(user_path, user_raw, user_info)
        model_hash, model_info = self._model_info(ctx)
        diagnostics = default_diagnostics + user_diagnostics
        if not ctx.paths.symlink_safe(user_path):
            diagnostics.append({"code": "unsupported_config", "severity": "error", "path": str(user_path),
                                "jsonPath": None, "line": None, "column": None,
                                "message": "menu path contains a symlink; replace it with a regular path"})
            state = "unsupported"
        elif default_doc is None or default_source["parse"] in {"failed", "hazard"}:
            diagnostics.append({"code": "menu_default_unparseable", "severity": "error", "path": str(default_path),
                                "jsonPath": None, "line": None, "column": None,
                                "message": "The shipped menu cannot be parsed. Run omarchy-update."})
            state = "unsupported"
        elif user_source["parse"] == "hazard":
            state = "hazard"
        elif user_source["parse"] == "failed":
            state = "malformed"
        elif user_doc and user_doc.get("duplicates"):
            state = "duplicate-keys"
        elif not user_info.get("exists"):
            state = "absent"
        elif user_source["parse"] == "empty":
            state = "empty"
        else:
            state = "ok"
        revision = "menu1:" + ((default_info.get("sha256") or "missing")[:16]) + ":" + (
            (user_info.get("sha256") or "missing")[:16] if user_info.get("exists") else "absent")
        effective_user = user_doc if state not in {"malformed", "unsupported"} else None
        effective = build_effective(default_doc, effective_user, model_info["overrideSemantics"])
        backups = []
        try:
            candidates = list(user_path.parent.glob(user_path.name + ".bak.*")) + list(user_path.parent.glob(user_path.name + ".omarchy-upgrade-to-quattro.*.bak"))
            for path in candidates:
                info = path.stat()
                backups.append({"path": str(path), "mtime": info.st_mtime, "size": info.st_size})
        except OSError:
            pass
        backups.sort(key=lambda item: item["mtime"], reverse=True)
        data = {"schemaVersion": 1, "revision": revision, "default": default_source, "user": user_source,
                "documentState": state, "document": user_doc if state in {"ok", "empty", "duplicate-keys"} else None,
                "effective": effective, "externalBackups": backups, "diagnostics": diagnostics,
                "overrideSemantics": model_info["overrideSemantics"], "providers": model_info["providers"],
                "guardReaders": model_info["guardReaders"], "modelHash": model_hash,
                "modelRecognized": model_info["modelRecognized"]}
        warning_values = () if model_info["modelRecognized"] else (Warning("menu_model_unrecognized", "MenuModel.js is not recognized; full-shadow behavior is assumed", str(self._paths(ctx)[2]), "Update the module's model version table"),)
        return Status(self.id, revision, data, warning_values, 1)

    def validate(self, ctx: Any, draft: dict[str, Any], status: Status) -> ValidationResult:
        return validate_draft(ctx, draft, status, status.data.get("overrideSemantics", "full-shadow"))

    def plan(self, ctx: Any, draft: dict[str, Any], status: Status) -> Plan:
        if draft.get("baseRevision") != status.revision:
            raise CcError("stale_revision", "The menu files changed on disk")
        state = status.data.get("documentState")
        recovery_mode = (draft.get("recovery") or {}).get("mode")
        if state == "unsupported":
            raise CcError("unsupported_config", "The shipped menu or menu path must be repaired before applying")
        if recovery_mode == "replace-after-backup" and state not in {"malformed", "hazard"}:
            raise CcError("unsupported_config", "Replace after backup is only available for malformed or hazardous user files")
        if state in {"malformed", "hazard"} and recovery_mode != "replace-after-backup":
            raise CcError("unsupported_config", "Use Replace after backup before overwriting this menu file")
        shell = ctx.ctx_for(self.id, "read").capabilities.get("shell")
        if not shell.available:
            raise CcError("capability_missing", shell.reason or "omarchy-menu ping did not answer ok",
                          {"capability": "shell"})
        content = render(draft)
        parsed, parse_state, diagnostics = parse_with_parity(content)
        if parsed is None or parse_state not in {"ok", "empty"} or document_value(parsed) != authored_value(draft):
            raise CcError("menu_writer_mismatch", "Generated menu did not round trip", {"diagnostics": diagnostics})
        _, user_path, _ = self._paths(ctx)
        current_raw, current_info = _read(user_path)
        mode = current_info.get("mode") if current_info.get("mode") in {0o600, 0o644} else 0o600
        before = (current_raw or b"").decode("utf-8", "replace").splitlines(keepends=True)
        after = content.decode("utf-8").splitlines(keepends=True)
        diff = "".join(difflib.unified_diff(before, after, fromfile=str(user_path), tofile=str(user_path)))
        write = ops.WriteFileAtomic(ctx, user_path, content.decode("utf-8"), mode, summary="Write personal menu")
        refresh = ops.RunCommand(ctx, ["omarchy-menu", "refresh"], timeout_s=10, capture_limit=4096,
                                 summary="Refresh the Omarchy menu", inverse=["omarchy-menu", "refresh"])
        rollback_refresh = ops.RunCommand(ctx, ["omarchy-menu", "refresh"], timeout_s=10, capture_limit=4096,
                                          summary="Refresh the restored Omarchy menu")
        write = replace(write, inverse=(write.inverse, replace(rollback_refresh, inverse=())))
        plan_warnings: list[Warning] = []
        confirmations: set[str] = set()
        for entry in draft.get("entries", []):
            if entry.get("deleted"):
                continue
            for field in ("action", "when", "checked", "disabled"):
                for warning in classify(field, entry.get("fields", {}).get(field, ""), entry.get("draftId", "")):
                    warning_code = warning["code"]
                    if warning["ack"]:
                        warning_code += "_" + warning["key"]
                    plan_warning = Warning(warning_code, warning["message"], f"{entry.get('id')}.{field}", warning.get("match", ""), warning["ack"])
                    plan_warnings.append(plan_warning)
                    if warning["ack"]:
                        confirmations.add(warning_code)
        if current_raw is not None and not is_canonical(current_raw):
            plan_warnings.append(Warning("menu_normalization", "Comments and formatting will be replaced by canonical JSONC", str(user_path), "Review the generated diff", True))
            confirmations.add("menu_normalization")
        recovery = draft.get("recovery") or {}
        if recovery.get("mode") == "replace-after-backup":
            confirmations.add("replace")
        summary = "Save personal menu and request a shell refresh"
        return Plan(self.id, status.revision, (write, refresh),
                    (ResourceClaim(f"file:{user_path}", "exclusive"),), summary, tuple(plan_warnings),
                    tuple(sorted(confirmations)))

    def verify(self, ctx: Any, plan: Plan, status_after: Status, results: dict[str, Any]) -> VerifyResult:
        write = next((operation for operation in plan.operations if operation.kind == "WriteFileAtomic"), None)
        refresh = next((operation for operation in plan.operations if operation.kind == "RunCommand"), None)
        expected = hashlib.sha256(write.params["content"].encode("utf-8") if isinstance(write.params["content"], str) else b"").hexdigest() if write else ""
        if status_after.data.get("user", {}).get("sha256") != expected:
            return VerifyResult("fail", "limited", "Written bytes did not match", "menu_verify_bytes", {"expectedSha256": expected})
        if status_after.data.get("documentState") not in {"ok", "empty"}:
            return VerifyResult("fail", "limited", "Written menu did not parse safely", "menu_verify_parse", status_after.data.get("user", {}))
        result = results.get(refresh.id) if refresh else None
        if not result or result.timed_out:
            return VerifyResult("fail", "limited", "Menu refresh timed out", "timeout")
        output = result.stdout_head.strip()
        if result.exit_code != 0 or output != "ok":
            detail = "plugin not loaded" if output == "unknown" else "refresh() threw" if output == "error" else result.stderr_head.strip() or output or "refresh failed"
            return VerifyResult("fail", "limited", detail, "menu_refresh_failed", {"stdout": output})
        return VerifyResult("pass", "limited", "refresh-ack-only", evidence={"userSha256": expected, "refresh": "ok"})

    def _project(self, ctx: Any, status: Status, draft: dict[str, Any]) -> dict[str, Any]:
        default_path, _, _ = self._paths(ctx)
        default_raw, _ = _read(default_path)
        default_doc, _, _ = parse_with_parity(default_raw or b"")
        user_doc, parse_state, diagnostics = parse_with_parity(render(draft))
        if user_doc is None or parse_state not in {"ok", "empty"}:
            raise CcError("menu_writer_mismatch", "Draft projection did not parse", {"diagnostics": diagnostics})
        effective = build_effective(default_doc, user_doc, draft.get("semantics", status.data.get("overrideSemantics", "full-shadow")))
        rows = effective["rows"]
        order = effective["order"]
        current_rows = status.data.get("effective", {}).get("rows", {})
        for entry in draft.get("entries", []):
            if entry.get("deleted"):
                item_id = entry.get("originalId") or entry.get("id")
                if item_id in current_rows:
                    deleted_row = {**current_rows[item_id], "draftState": "deleted"}
                    rows[item_id] = deleted_row
                    if item_id not in order:
                        order.append(item_id)
            elif entry.get("id") in rows:
                rows[entry["id"]] = {**rows[entry["id"]], "draftState": "draft"}
        return effective

    def query(self, ctx: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
        status = self.status(ctx)
        draft = args.get("draft")
        effective = self._project(ctx, status, draft) if isinstance(draft, dict) and draft.get("schemaVersion") == 1 else status.data["effective"]
        if name == "projection":
            return {"schemaVersion": 1, "effective": effective}
        if name == "route":
            return resolve_route(effective, str(args.get("input", "")))
        if name == "search-tokens":
            return search_tokens(effective, str(args.get("id", "")))
        raise CcError("unknown_query", f"Unknown menu query: {name}")

    def migrate(self, ctx: Any, kind: str, document: dict[str, Any], from_version: int) -> dict[str, Any]:
        if from_version == self.schema_version:
            return dict(document)
        raise CcError("unsupported_config", f"No menu {kind} migration from version {from_version}")


MODULE = MenuModule()
