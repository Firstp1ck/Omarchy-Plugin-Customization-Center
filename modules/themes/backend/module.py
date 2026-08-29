from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from customization_center.core import (
    Capabilities, Capability, CcError, Plan, ResourceClaim, Status, ValidationIssue,
    ValidationResult, VerifyResult, Warning, ops,
)

from .contrast import diagnostics
from .images import encode_swatch_png, image_info
from .inventory import classify, read_status
from .palette import normalize_palette, valid_slug
from .render import preview_payload, render_shell
from .sections import SECTIONS, TEMPLATE_SHA256
from .writer import colors_toml, section_toml, validate_section

_WALLPAPER_NAME = re.compile(r"^[0-9]{2}-[a-z0-9][a-z0-9._-]{0,100}\.(?:jpg|jpeg|png|gif|bmp|webp)$")
_ICON_NAME = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except (FileNotFoundError, OSError):
        return None


def _file_hashes(files: dict[str, bytes]) -> dict[str, str]:
    return {name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())}


def _template(ctx: Any) -> tuple[Path, bytes | None]:
    path = ctx.paths.omarchy_path / "default/themed/shell.toml.tpl"
    return path, _read_bytes(path)


def _preview_template(ctx: Any) -> tuple[Path, bytes | None]:
    user = ctx.paths.home / ".config/omarchy/themed/shell.toml.tpl"
    data = _read_bytes(user)
    return (user, data) if data is not None else _template(ctx)


def _tokens(palette: dict[str, Any], sections: dict[str, Any], machine: dict[str, Any]) -> dict[str, Any]:
    roles = {"foreground": palette["foreground"], "text": palette["foreground"], "accent": palette["accent"],
             "urgent": palette["red"], "muted": palette["muted"], "background": palette["background"],
             "transparent": "#00000000"}
    return {"palette": {**palette, "urgent": palette["red"]}, "roles": roles,
            "sections": sections, "machineOverride": machine, "masked": sorted(machine)}


class ThemesModule:
    id = "themes"
    schema_version = 1

    def capabilities(self, ctx: Any) -> Capabilities:
        template_path, template = _template(ctx)
        template_hash = hashlib.sha256(template).hexdigest() if template is not None else ""
        compose = template is not None and (ctx.paths.omarchy_path / "bin/omarchy-theme-set-templates").is_file()
        activate = ctx.commands.which("omarchy-theme-set") is not None
        wallpaper = ctx.commands.which("omarchy-theme-bg-set") is not None
        shell = ctx.commands.which("omarchy-shell") is not None
        items = (
            Capability("compose", compose, "" if compose else f"Missing {template_path} or omarchy-theme-set-templates"),
            Capability("activate", activate, "" if activate else "omarchy-theme-set is not on PATH"),
            Capability("wallpaper", wallpaper, "" if wallpaper else "omarchy-theme-bg-set is not on PATH"),
            Capability("sections", template_hash == TEMPLATE_SHA256,
                       "" if template_hash == TEMPLATE_SHA256 else f"themes_template_drift: expected {TEMPLATE_SHA256}, found {template_hash or 'missing'}"),
            Capability("tryInShell", shell, "" if shell else "omarchy-shell is not on PATH"),
            Capability("themeSwitcherVisible", compose, "" if compose else "Preview generation requires the Omarchy theme template"),
        )
        return Capabilities(self.id, items, ctx.clock.now_iso())

    def status(self, ctx: Any) -> Status:
        data = read_status(ctx)
        revision_data = data.pop("revisionData")
        revision = "sha256:" + hashlib.sha256(json.dumps(revision_data, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        warnings: list[Warning] = []
        template_path, template = _template(ctx)
        actual = hashlib.sha256(template).hexdigest() if template else "missing"
        if actual != TEMPLATE_SHA256:
            warnings.append(Warning("themes_template_drift", "The installed shell theme template changed",
                                    str(template_path), "Update the theme section table or edit palette values only"))
        return Status(self.id, revision, data, tuple(warnings), 1)

    def validate(self, ctx: Any, draft: dict[str, Any], status: Status) -> ValidationResult:
        issues: list[ValidationIssue] = []
        if not isinstance(draft, dict) or draft.get("schemaVersion") != 1:
            return ValidationResult(False, (ValidationIssue("validation_failed", "schemaVersion must be 1", "/schemaVersion", "error"),), None)
        kind = draft.get("kind")
        if kind not in {"compose", "activate"}:
            issues.append(ValidationIssue("validation_failed", "kind must be compose or activate", "/kind", "error"))
        slug = draft.get("slug")
        if not valid_slug(slug):
            issues.append(ValidationIssue("themes_slug_invalid", "Slug must be lowercase letters, digits, and single hyphens", "/slug", "error"))
        themes = status.data.get("themes", [])
        existing = next((item for item in themes if item.get("slug") == slug), None)
        normalized = dict(draft)
        if kind == "activate":
            if existing is None:
                issues.append(ValidationIssue("themes_target_missing", "The selected theme does not exist", "/slug", "error"))
            preferred = draft.get("preferredWallpaper")
            if preferred is not None and (not isinstance(preferred, str) or not Path(preferred).is_absolute() or not Path(preferred).is_file()):
                issues.append(ValidationIssue("themes_preferred_unknown", "Preferred wallpaper must be an existing absolute path", "/preferredWallpaper", "error"))
        elif draft.get("delete") is True:
            if existing is None:
                issues.append(ValidationIssue("themes_target_missing", "The selected theme does not exist", "/slug", "error"))
            elif existing.get("source") == "builtin":
                issues.append(ValidationIssue("themes_target_builtin", "Built-in themes cannot be deleted", "/slug", "error"))
            elif status.data.get("active", {}).get("slug") == slug:
                issues.append(ValidationIssue("themes_target_active", "The active theme cannot be deleted", "/slug", "error"))
            elif existing.get("classification") in {"git", "symlink"}:
                issues.append(ValidationIssue("themes_target_readonly", "Git and symlink themes are read-only", "/slug", "error"))
        elif kind == "compose":
            if slug in status.data.get("builtInSlugs", []):
                issues.append(ValidationIssue("themes_slug_is_builtin", "Choose a slug that is not a built-in theme", "/slug", "error"))
            palette, palette_errors = normalize_palette(draft.get("palette"))
            for key, message in palette_errors:
                issues.append(ValidationIssue("themes_value_syntax", message, f"/palette/{key}", "error"))
            sections = draft.get("sections", {})
            if not isinstance(sections, dict):
                issues.append(ValidationIssue("themes_section_incomplete", "sections must be an object", "/sections", "error"))
                sections = {}
            for name in sections:
                if name not in SECTIONS:
                    issues.append(ValidationIssue("themes_section_incomplete", f"Unknown section {name}", f"/sections/{name}", "error"))
            for name in SECTIONS:
                for key, message in validate_section(name, sections.get(name)):
                    issues.append(ValidationIssue("themes_section_incomplete" if "key" in message else "themes_value_syntax",
                                                  message, f"/sections/{name}/{key}", "error"))
            wallpapers = draft.get("wallpapers", [])
            if not isinstance(wallpapers, list) or len(wallpapers) > 12:
                issues.append(ValidationIssue("themes_wallpaper_too_many", "At most 12 wallpapers are allowed", "/wallpapers", "error"))
                wallpapers = []
            total = 0; names: set[str] = set()
            for index, item in enumerate(wallpapers):
                pointer = f"/wallpapers/{index}"
                if not isinstance(item, dict) or not _WALLPAPER_NAME.fullmatch(str(item.get("outputName", ""))):
                    issues.append(ValidationIssue("themes_wallpaper_name", "Wallpaper output name is not valid", pointer + "/outputName", "error")); continue
                output_name = item["outputName"]
                if output_name.lower() in names:
                    issues.append(ValidationIssue("themes_wallpaper_name", "Wallpaper output names must be unique", pointer + "/outputName", "error"))
                names.add(output_name.lower())
                source = ctx.paths.resolve_user_path(item.get("sourcePath", ""))
                if source is None or not source.is_file():
                    issues.append(ValidationIssue("themes_wallpaper_missing", "Wallpaper source file is missing", pointer + "/sourcePath", "error")); continue
                if source.is_symlink() or not ctx.paths.symlink_safe(source):
                    issues.append(ValidationIssue("themes_wallpaper_symlink", "Wallpaper source must not be a symlink", pointer + "/sourcePath", "error")); continue
                try:
                    size = source.stat().st_size; data = source.read_bytes(); total += size
                    if size < 1 or size > 25 * 1024 * 1024:
                        raise OverflowError
                    width, height = image_info(data, Path(output_name).suffix)
                    if not 16 <= width <= 16384 or not 16 <= height <= 16384:
                        raise ValueError("dimensions")
                except OverflowError:
                    issues.append(ValidationIssue("themes_wallpaper_too_large", "Wallpaper must be at most 25 MiB", pointer + "/sourcePath", "error"))
                except ValueError as error:
                    code = "themes_wallpaper_signature" if str(error) == "signature" else "themes_wallpaper_unreadable"
                    issues.append(ValidationIssue(code, "Wallpaper signature or dimensions are invalid", pointer + "/sourcePath", "error"))
                except OSError:
                    issues.append(ValidationIssue("themes_wallpaper_unreadable", "Wallpaper could not be read", pointer + "/sourcePath", "error"))
            if total > 200 * 1024 * 1024:
                issues.append(ValidationIssue("themes_wallpaper_too_large", "Wallpaper total exceeds 200 MiB", "/wallpapers", "error"))
            preferred = draft.get("preferredWallpaper")
            if preferred is not None and preferred not in names and str(preferred).lower() not in names:
                issues.append(ValidationIssue("themes_preferred_unknown", "Preferred wallpaper is not in the wallpaper list", "/preferredWallpaper", "error"))
            icon = draft.get("iconTheme")
            if icon is not None and (not isinstance(icon, str) or not _ICON_NAME.fullmatch(icon)):
                issues.append(ValidationIssue("themes_value_syntax", "Icon theme name is invalid", "/iconTheme", "error"))
            if palette is not None:
                normalized["palette"] = palette
                normalized["sections"] = {name: sections.get(name) for name in SECTIONS}
                contrast = diagnostics(palette)
                accepted = set(draft.get("acceptedWarnings", []))
                for item in contrast:
                    if not item["passes"]:
                        code = "themes_contrast_low"
                        issues.append(ValidationIssue(code, f"Low contrast for {item['pairId']}: {item['ratio']}", "/palette", "warning"))
                if not wallpapers:
                    issues.append(ValidationIssue("themes_no_wallpaper", "A preview.png will be generated; activation keeps the previous wallpaper", "/wallpapers", "warning"))
                normalized["acceptedWarnings"] = sorted(accepted)
        errors = any(issue.severity == "error" for issue in issues)
        details = {}
        if not errors and kind == "compose" and draft.get("delete") is not True:
            details = {"tokens": _tokens(normalized["palette"], normalized["sections"], status.data.get("machineOverride", {}).get("values", {})),
                       "contrast": diagnostics(normalized["palette"])}
        return ValidationResult(not errors, tuple(issues), None if errors else normalized, details)

    def _generated(self, ctx: Any, draft: dict[str, Any]) -> dict[str, bytes]:
        files: dict[str, bytes] = {"colors.toml": colors_toml(draft["palette"]).encode()}
        for name, value in draft.get("sections", {}).items():
            if value is not None:
                files[f"shell.{name}.toml"] = section_toml(name, value).encode()
        if draft.get("iconTheme"):
            files["icons.theme"] = (draft["iconTheme"] + "\n").encode()
        wallpapers = draft.get("wallpapers", [])
        if wallpapers:
            for index, item in enumerate(wallpapers, 1):
                tail = item["outputName"].split("-", 1)[-1]
                files[f"backgrounds/{index:02d}-{tail}"] = Path(item["sourcePath"]).read_bytes()
        else:
            files["preview.png"] = encode_swatch_png(draft["palette"])
        return files

    def plan(self, ctx: Any, draft: dict[str, Any], status: Status) -> Plan:
        slug = draft["slug"]
        theme_root = ctx.paths.home / ".config/omarchy/themes"
        target = theme_root / slug
        sidecar = ctx.paths.module_state(self.id) / f"{slug}.json"
        active = status.data.get("active", {})
        if draft.get("kind") == "activate":
            return self._activation_plan(ctx, draft, status, ())
        if draft.get("delete") is True:
            operations = (ops.ReplaceDirectoryAtomic(ctx, target, None, True, f"Delete theme {slug}"),
                          ops.RemoveFile(ctx, sidecar, f"Remove ownership record for {slug}"))
            return Plan(self.id, status.revision, operations,
                        (ResourceClaim(f"file:{target}", "exclusive"),), f"Delete theme {slug}", (), ())
        if draft.get("tryInShell") is True:
            template_path, template = _preview_template(ctx)
            current_colors = _read_bytes(ctx.paths.home / ".local/state/omarchy/current/theme/colors.toml")
            current_shell = _read_bytes(ctx.paths.home / ".local/state/omarchy/current/theme/shell.toml")
            if template is None or current_colors is None or current_shell is None:
                raise CcError("capability_missing", f"Try in shell needs {template_path} and the current colors.toml and shell.toml")
            colors = colors_toml(draft["palette"]).encode()
            shell = render_shell(template.decode("utf-8"), draft["palette"], draft["sections"]).encode()
            if max(map(len, (colors, shell, current_colors, current_shell))) > 65536:
                raise CcError("themes_preview_too_large", "A Try in shell payload exceeds 64 KiB")
            inverse = ops.ShellIpc(ctx, "applyTheme", (base64.b64encode(current_colors).decode(), base64.b64encode(current_shell).decode()),
                                   summary="Restore the running shell theme")
            operation = ops.ShellIpc(ctx, "applyTheme", (base64.b64encode(colors).decode(), base64.b64encode(shell).decode()),
                                     inverse=inverse, summary=f"Try {slug} in the running shell")
            return Plan(self.id, status.revision, (operation,), (ResourceClaim("theme.shell-preview", "exclusive"),),
                        f"Try theme {slug} in shell", (), ())
        existing_sidecar = ctx.paths.read_json(sidecar, default=None)
        classification, inventory = classify(target, existing_sidecar)
        if classification in {"git", "symlink", "unsupported"}:
            raise CcError("themes_target_readonly", f"Theme {slug} is {classification}; duplicate it under a new slug")
        warning_code = f"themes_replace_unmanaged:{slug}"
        accepted = set(draft.get("acceptedWarnings", []))
        warnings: list[Warning] = []
        if classification in {"plain", "managed-modified"}:
            warning = Warning(warning_code, f"Replacing {target} removes: {', '.join(inventory) or 'all existing files'}",
                              str(target), "Duplicate the theme or accept replacement", True)
            warnings.append(warning)
            if warning_code not in accepted:
                raise CcError("themes_replace_unmanaged", warning.message, {"warning": warning_code, "files": inventory})
        files = self._generated(ctx, draft)
        plan_id = hashlib.sha256((status.revision + json.dumps(draft, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()[:16]
        staging = ctx.paths.state / "staging/themes" / plan_id
        staged_theme = staging / "theme"
        operations: list[Any] = [ops.EnsureDirectory(ctx, theme_root, "0755", "Ensure the user theme directory"),
                                 ops.EnsureDirectory(ctx, staged_theme, "0755", "Create theme staging directory")]
        if any(name.startswith("backgrounds/") for name in files):
            operations.append(ops.EnsureDirectory(ctx, staged_theme / "backgrounds", "0755", "Create staged wallpaper directory"))
        for name, content in sorted(files.items()):
            operations.append(ops.WriteFileAtomic(ctx, staged_theme / name, content, "0644", f"Stage {name}"))
        operations.append(ops.ReplaceDirectoryAtomic(ctx, target, staged_theme, classification != "absent", f"Save theme {slug}"))
        sidecar_document = {"schemaVersion": 1, "slug": slug, "transactionId": plan_id,
                            "savedAt": ctx.clock.now_iso(), "files": _file_hashes(files)}
        operations.append(ops.WriteFileAtomic(ctx, sidecar, json.dumps(sidecar_document, sort_keys=True, separators=(",", ":")) + "\n",
                                              "0644", f"Record ownership of {slug}"))
        claims = [ResourceClaim(f"file:{target}", "exclusive"), ResourceClaim(f"file:{sidecar}", "exclusive")]
        if draft.get("activate"):
            activation = self._activation_operations(ctx, draft, status)
            operations.extend(activation)
            claims.append(ResourceClaim("theme.current", "exclusive"))
        if not draft.get("wallpapers"):
            warnings.append(Warning("themes_no_wallpaper", "No wallpaper was selected", str(target / "preview.png"),
                                    "Add a wallpaper or keep the current desktop background"))
        confirmations = tuple(warning.code for warning in warnings if warning.ack)
        summary = f"Create theme {slug} ({len(files)} files, {len(draft.get('wallpapers', []))} wallpapers)"
        residual = ("Theme-set hooks and application retints cannot be undone exactly",) if draft.get("activate") else ()
        return Plan(self.id, status.revision, tuple(operations), tuple(claims), summary, tuple(warnings), confirmations, residual)

    def _activation_operations(self, ctx: Any, draft: dict[str, Any], status: Status) -> list[Any]:
        slug = draft["slug"]; previous = status.data.get("active", {}).get("slug")
        preferred = draft.get("preferredWallpaper")
        argv = ["omarchy-theme-set", slug]
        if preferred:
            argv = ["env", "OMARCHY_THEME_SKIP_BACKGROUND=1", *argv]
        inverse = ["omarchy-theme-set", previous] if previous else None
        operations = [ops.RunCommand(ctx, argv, timeout_s=120, capture_limit=65536,
                                     summary=f"Activate {slug} with omarchy-theme-set", inverse=inverse)]
        if preferred:
            path = preferred if draft.get("kind") == "activate" else str(ctx.paths.home / ".local/state/omarchy/current/theme/backgrounds" / preferred)
            previous_background = status.data.get("active", {}).get("background")
            operations.append(ops.RunCommand(ctx, ["omarchy-theme-bg-set", path], timeout_s=10,
                                             summary=f"Set wallpaper {Path(path).name}",
                                             inverse=["omarchy-theme-bg-set", previous_background] if previous_background else None))
        return operations

    def _activation_plan(self, ctx: Any, draft: dict[str, Any], status: Status, warnings: tuple[Warning, ...]) -> Plan:
        operations = tuple(self._activation_operations(ctx, draft, status))
        confirmations = tuple(operation.id for operation in operations if operation.inverse is None)
        return Plan(self.id, status.revision, operations, (ResourceClaim("theme.current", "exclusive"),),
                    f"Activate theme {draft['slug']}", warnings, confirmations,
                    ("Theme-set hooks and application retints cannot be undone exactly",))

    def verify(self, ctx: Any, plan: Plan, status_after: Status, results: dict[str, Any]) -> VerifyResult:
        replacement = next((operation for operation in plan.operations if operation.kind == "ReplaceDirectoryAtomic" and operation.params.get("staged_dir")), None)
        sidecar_write = next((operation for operation in plan.operations if operation.kind == "WriteFileAtomic" and operation.params.get("path", "").endswith(".json") and "/themes/" in operation.params.get("path", "")), None)
        if replacement and sidecar_write:
            sidecar = json.loads(sidecar_write.params["content"])
            target = Path(replacement.params["path"])
            actual: dict[str, str] = {}
            try:
                for path in target.rglob("*"):
                    if path.is_symlink() or path.is_file() and path.stat().st_mode & 0o111:
                        return VerifyResult("fail", "full", "Theme contains a symlink or executable file", "themes_verify_files", {"path": str(path)})
                    if path.is_file():
                        actual[str(path.relative_to(target))] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as error:
                return VerifyResult("fail", "full", str(error), "themes_verify_files")
            if actual != sidecar["files"]:
                return VerifyResult("fail", "full", "Saved theme files do not match the ownership record", "themes_verify_files",
                                    {"expected": sidecar["files"], "actual": actual})
        activation = next((operation for operation in plan.operations if operation.kind == "RunCommand" and "omarchy-theme-set" in operation.params.get("argv", [])), None)
        if activation:
            argv = activation.params["argv"]; slug = argv[-1]
            if status_after.data.get("active", {}).get("slug") != slug:
                return VerifyResult("fail", "full", f"theme.name did not become {slug}", "themes_verify_active",
                                    status_after.data.get("active", {}))
        return VerifyResult("pass", "full", "", evidence={"revision": status_after.revision})

    def query(self, ctx: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name != "preview":
            raise CcError("unknown_query", f"Unknown themes query: {name}")
        draft = args.get("draft")
        status = self.status(ctx)
        validation = self.validate(ctx, draft, status) if isinstance(draft, dict) else ValidationResult(False, (), None)
        if not validation.ok or validation.normalized_draft is None or validation.normalized_draft.get("kind") != "compose":
            raise CcError("validation_failed", "Preview requires a valid compose draft",
                          {"issues": [issue.to_json() for issue in validation.issues]})
        normalized = validation.normalized_draft
        template_path, template = _preview_template(ctx)
        if template is None:
            raise CcError("capability_missing", f"Theme template is missing: {template_path}")
        colors = colors_toml(normalized["palette"])
        try:
            shell = render_shell(template.decode("utf-8"), normalized["palette"], normalized["sections"])
        except (UnicodeDecodeError, ValueError) as error:
            raise CcError("themes_render_failed", str(error)) from error
        if "{{" in shell:
            raise CcError("themes_render_failed", "Rendered shell.toml contains an unresolved placeholder")
        tokens = _tokens(normalized["palette"], normalized["sections"], status.data.get("machineOverride", {}).get("values", {}))
        return preview_payload(colors, shell, tokens)

    def migrate(self, ctx: Any, kind: str, document: dict[str, Any], from_version: int) -> dict[str, Any]:
        if from_version == 1:
            return dict(document)
        raise CcError("unsupported_config", f"No themes {kind} migration from version {from_version}")


MODULE = ThemesModule()
