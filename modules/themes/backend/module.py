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
from .palette import PALETTE_ORDER, normalize_palette, valid_slug
from .render import preview_payload, render_shell
from .resolver import resolve_tokens
from .sections import SECTIONS, TEMPLATE_SHA256, defaults
from .writer import colors_toml, parse_shell, section_toml, validate_section

_WALLPAPER_NAME = re.compile(r"^[0-9]{2}-[a-z0-9][a-z0-9._-]{0,100}\.(?:jpg|jpeg|png|gif|bmp|webp)$")
_ICON_NAME = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_COLOR_LINE = re.compile(r'^\s*([A-Za-z0-9_-]+)\s*=\s*["\']?([^"\'#\s][^"\']*|#[0-9A-Fa-f]{6})')
_TEMPLATE_OUTPUTS = {
    "alacritty.toml", "btop.theme", "chromium.theme", "claude.json", "foot.ini", "ghostty.conf",
    "gum_env.lua", "helix.toml", "hyprland.lua", "hyprland-preview-share-picker.css", "kitty.conf",
    "neovim.lua", "obsidian.css", "pi.json", "shell.toml", "vscode-theme.json", "vscode.json",
}


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


def _shell_reachable(ctx: Any) -> bool:
    try:
        return bool(ctx.shell.ping())
    except (CcError, OSError):
        return False


def _parse_colors(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return values
    for line in lines:
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            continue
        value = value.strip()
        if value.startswith(('"', "'")) and len(value) >= 2:
            quote = value[0]
            finish = value.rfind(quote)
            value = value[1:finish] if finish > 0 else value[1:]
        else:
            value = value.split("#", 1)[0].strip() if not value.startswith("#") else value.split()[0]
        values[key] = value.strip()
    aliases = {"background": ("color0", "bg"), "foreground": ("color7", "fg"), "accent": ("color4",),
               "red": ("color1",), "yellow": ("color3",), "green": ("color2",), "cyan": ("color6",),
               "blue": ("color4",), "magenta": ("color5", "purple")}
    seed: dict[str, Any] = {"mode": values.get("mode", values.get("theme_type", "dark"))}
    for key, fallbacks in aliases.items():
        seed[key] = next((values.get(name) for name in (key, *fallbacks) if values.get(name)), None)
    for key in PALETTE_ORDER[1:]:
        if values.get(key):
            seed[key] = values[key]
    for key in ("hyprland_active_border", "hyprland_inactive_border"):
        seed[key] = values.get(key)
    palette, _ = normalize_palette(seed)
    return palette or {}


def _exact_preview_restore(colors: bytes | None, shell: bytes | None) -> tuple[bool, str]:
    if colors is None or shell is None:
        return False, "Current colors.toml and shell.toml are required for an exact restore"
    if max(len(colors), len(shell)) > 65536:
        return False, "A current shell theme payload exceeds 64 KiB"
    text = colors.decode("utf-8", "replace")
    keys = {line.split("=", 1)[0].strip() for line in text.splitlines() if "=" in line}
    groups = (("foreground",), ("background",), ("accent", "color4"), ("muted", "color8"), ("red", "color1"))
    missing = [" or ".join(group) for group in groups if not any(key in keys for key in group)]
    if missing:
        return False, "Current colors.toml cannot be restored exactly; missing " + ", ".join(missing)
    return True, ""


def _unaffected_state(data: dict[str, Any], target_slug: str) -> dict[str, Any]:
    themes = sorted(
        ({key: value for key, value in item.items() if key != "sidecar"}
         for item in data.get("themes", []) if item.get("slug") != target_slug),
        key=lambda item: str(item.get("slug", "")),
    )
    return {"themes": themes, "machineOverride": data.get("machineOverride"),
            "userTemplates": data.get("userTemplates"), "builtInSlugs": data.get("builtInSlugs")}


def _unaffected(data: dict[str, Any], target_slug: str) -> str:
    value = _unaffected_state(data, target_slug)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _saved_preferred(draft: dict[str, Any]) -> str | None:
    preferred = draft.get("preferredWallpaper")
    if not preferred or draft.get("kind") == "activate":
        return preferred
    for index, item in enumerate(draft.get("wallpapers", []), 1):
        if item.get("outputName", "").lower() == str(preferred).lower():
            return f"{index:02d}-{item['outputName'].split('-', 1)[-1]}"
    return preferred


def _activation_roots(ctx: Any, slug: str, entry: dict[str, Any] | None) -> tuple[Path, ...]:
    roots = [ctx.paths.home / ".config/omarchy/backgrounds" / slug]
    if entry and entry.get("path"):
        roots.append(Path(entry["path"]) / "backgrounds")
    return tuple(root.absolute() for root in roots)


def _is_under(path: Path, roots: tuple[Path, ...]) -> bool:
    absolute = path.absolute()
    return any(absolute.is_relative_to(root) for root in roots)


def _read_wallpaper(ctx: Any, source: str, output_name: str) -> bytes:
    path = Path(source)
    if not path.is_absolute():
        raise CcError("themes_wallpaper_missing", "Wallpaper source paths must be absolute")
    try:
        data = ctx.paths.read_regular(path, 25 * 1024 * 1024)
    except CcError as error:
        if not path.exists():
            raise CcError("themes_wallpaper_missing", f"Wallpaper is missing: {path}") from error
        if path.is_symlink() or not ctx.paths.symlink_safe(path):
            raise CcError("themes_wallpaper_symlink", f"Wallpaper source is symlinked: {path}") from error
        if path.is_file() and path.stat().st_size > 25 * 1024 * 1024:
            raise CcError("themes_wallpaper_too_large", f"Wallpaper exceeds 25 MiB: {path}") from error
        raise CcError("themes_wallpaper_unreadable", f"Wallpaper could not be read safely: {path}") from error
    if not data:
        raise CcError("themes_wallpaper_too_large", f"Wallpaper must not be empty: {path}")
    try:
        width, height = image_info(data, Path(output_name).suffix)
    except ValueError as error:
        code = "themes_wallpaper_signature" if str(error) == "signature" else "themes_wallpaper_unreadable"
        raise CcError(code, f"Wallpaper header is invalid: {path}") from error
    if not 16 <= width <= 16384 or not 16 <= height <= 16384:
        raise CcError("themes_wallpaper_unreadable", f"Wallpaper dimensions are outside 16 to 16384 pixels: {path}")
    return data


class ThemesModule:
    id = "themes"
    schema_version = 1

    def capabilities(self, ctx: Any) -> Capabilities:
        template_path, template = _template(ctx)
        template_hash = hashlib.sha256(template).hexdigest() if template is not None else ""
        compose = template is not None and (ctx.paths.omarchy_path / "bin/omarchy-theme-set-templates").is_file()
        activate = ctx.commands.which("omarchy-theme-set") is not None
        wallpaper = ctx.commands.which("omarchy-theme-bg-set") is not None
        current_colors = _read_bytes(ctx.paths.home / ".local/state/omarchy/current/theme/colors.toml")
        current_shell = _read_bytes(ctx.paths.home / ".local/state/omarchy/current/theme/shell.toml")
        exact, exact_reason = _exact_preview_restore(current_colors, current_shell)
        shell = ctx.commands.which("omarchy-shell") is not None and _shell_reachable(ctx)
        open_preview = read_status(ctx).get("openPreviewTransaction") if shell and exact else None
        try_available = shell and exact and open_preview is None
        try_reason = "" if try_available else ("Another Try in shell preview is open" if open_preview else
                     exact_reason if not exact else "The Omarchy shell did not answer ping")
        items = (
            Capability("compose", compose, "" if compose else f"Missing {template_path} or omarchy-theme-set-templates"),
            Capability("activate", activate, "" if activate else "omarchy-theme-set is not on PATH"),
            Capability("wallpaper", wallpaper, "" if wallpaper else "omarchy-theme-bg-set is not on PATH"),
            Capability("sections", template_hash == TEMPLATE_SHA256,
                       "" if template_hash == TEMPLATE_SHA256 else f"themes_template_drift: expected {TEMPLATE_SHA256}, found {template_hash or 'missing'}"),
            Capability("tryInShell", try_available, try_reason),
            Capability("themeSwitcherVisible", compose, "" if compose else "Preview generation requires the Omarchy theme template"),
        )
        return Capabilities(self.id, items, ctx.clock.now_iso())

    def status(self, ctx: Any) -> Status:
        data = read_status(ctx)
        current_colors = _read_bytes(ctx.paths.home / ".local/state/omarchy/current/theme/colors.toml")
        current_shell = _read_bytes(ctx.paths.home / ".local/state/omarchy/current/theme/shell.toml")
        exact, exact_reason = _exact_preview_restore(current_colors, current_shell)
        shell_reachable = _shell_reachable(ctx)
        open_preview = data.get("openPreviewTransaction")
        data["tryInShellEligibility"] = {"available": shell_reachable and exact and open_preview is None,
                                         "shellReachable": shell_reachable, "exactRestore": exact,
                                         "reason": ("Another Try in shell preview is open" if open_preview else
                                                    exact_reason if not exact else
                                                    "" if shell_reachable else "The Omarchy shell did not answer ping")}
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
        normalized = json.loads(json.dumps(draft))
        if kind == "activate":
            if existing is None:
                issues.append(ValidationIssue("themes_target_missing", "The selected theme does not exist", "/slug", "error"))
            preferred = draft.get("preferredWallpaper")
            if preferred is not None:
                path = Path(preferred) if isinstance(preferred, str) else Path(".")
                if not isinstance(preferred, str) or not path.is_absolute() or not path.is_file() or not _is_under(path, _activation_roots(ctx, str(slug), existing)):
                    issues.append(ValidationIssue("themes_preferred_unknown", "Preferred wallpaper must be an existing absolute file under the theme backgrounds or user background overlay", "/preferredWallpaper", "error"))
        elif draft.get("delete") is True:
            allowed = {"schemaVersion", "kind", "slug", "delete", "acceptedWarnings"}
            if set(draft) - allowed:
                issues.append(ValidationIssue("validation_failed", "Delete drafts cannot contain composer fields", "", "error"))
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
                code = "themes_palette_missing" if draft.get("palette", {}).get(key) is None else "themes_value_syntax"
                issues.append(ValidationIssue(code, message, f"/palette/{key}", "error"))
            sections = draft.get("sections", {})
            if not isinstance(sections, dict):
                issues.append(ValidationIssue("themes_section_incomplete", "sections must be an object", "/sections", "error")); sections = {}
            for name in sections:
                if name not in SECTIONS:
                    issues.append(ValidationIssue("themes_section_incomplete", f"Unknown section {name}", f"/sections/{name}", "error"))
            for name in SECTIONS:
                for key, message in validate_section(name, sections.get(name)):
                    code = "themes_range" if "invalid" in message and any(word in message for word in ("alpha", "size", "scale", "width", "spacing")) else "themes_section_incomplete" if "key" in message else "themes_value_syntax"
                    issues.append(ValidationIssue(code, message, f"/sections/{name}/{key}", "error"))
            wallpapers = draft.get("wallpapers", [])
            if not isinstance(wallpapers, list) or len(wallpapers) > 12:
                issues.append(ValidationIssue("themes_wallpaper_too_many", "At most 12 wallpapers are allowed", "/wallpapers", "error")); wallpapers = []
            total = 0; names: set[str] = set()
            for index, item in enumerate(wallpapers):
                pointer = f"/wallpapers/{index}"
                if not isinstance(item, dict) or not _WALLPAPER_NAME.fullmatch(str(item.get("outputName", ""))):
                    issues.append(ValidationIssue("themes_wallpaper_name", "Wallpaper output name is not valid", pointer + "/outputName", "error")); continue
                output_name = item["outputName"]
                if output_name.lower() in names:
                    issues.append(ValidationIssue("themes_wallpaper_name", "Wallpaper output names must be unique", pointer + "/outputName", "error"))
                names.add(output_name.lower())
                source = item.get("sourcePath")
                if not isinstance(source, str) or not Path(source).is_absolute():
                    issues.append(ValidationIssue("themes_wallpaper_missing", "Wallpaper source paths must be absolute", pointer + "/sourcePath", "error")); continue
                try:
                    data = _read_wallpaper(ctx, source, output_name); total += len(data)
                except CcError as error:
                    issues.append(ValidationIssue(error.code, error.message, pointer + "/sourcePath", "error"))
            if total > 200 * 1024 * 1024:
                issues.append(ValidationIssue("themes_wallpaper_too_large", "Wallpaper total exceeds 200 MiB", "/wallpapers", "error"))
            preferred = draft.get("preferredWallpaper")
            if preferred is not None and (not isinstance(preferred, str) or preferred.lower() not in names):
                issues.append(ValidationIssue("themes_preferred_unknown", "Preferred wallpaper is not in the wallpaper list", "/preferredWallpaper", "error"))
            icon = draft.get("iconTheme")
            if icon is not None and (not isinstance(icon, str) or not _ICON_NAME.fullmatch(icon)):
                issues.append(ValidationIssue("themes_value_syntax", "Icon theme name is invalid", "/iconTheme", "error"))
            elif icon and icon not in status.data.get("iconThemes", []):
                issues.append(ValidationIssue("themes_icon_theme_missing", f"Icon theme {icon} is not installed", "/iconTheme", "warning"))
            if palette is not None:
                normalized["palette"] = palette
                normalized["sections"] = {name: sections.get(name) for name in SECTIONS}
                tokens = resolve_tokens(normalized, status.data.get("machineOverride", {}).get("values", {}))
                contrast = diagnostics(tokens)
                accepted = set(draft.get("acceptedWarnings", []))
                for item in contrast:
                    if item["blocked"]:
                        issues.append(ValidationIssue("themes_contrast_invisible", f"Invisible required text for {item['pairId']} ({item['ratio']})", "/palette", "error"))
                    elif not item["passes"]:
                        issues.append(ValidationIssue(item["warningId"], f"Low contrast for {item['pairId']}: {item['ratio']}", "/palette", "warning"))
                for item in tokens["masked"]:
                    issues.append(ValidationIssue(f"themes_masked:{item['section']}.{item['key']}", "The machine shell override masks this theme value", f"/sections/{item['section']}/{item['key']}", "warning"))
                if not wallpapers:
                    issues.append(ValidationIssue("themes_no_wallpaper", "A preview.png will be generated; activation keeps the previous wallpaper", "/wallpapers", "warning"))
                normalized["acceptedWarnings"] = sorted(accepted)
        errors = any(issue.severity == "error" for issue in issues)
        details: dict[str, Any] = {}
        if not errors and kind == "compose" and draft.get("delete") is not True:
            tokens = resolve_tokens(normalized, status.data.get("machineOverride", {}).get("values", {}))
            details = {"tokens": tokens, "contrast": diagnostics(tokens)}
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
                files[f"backgrounds/{index:02d}-{tail}"] = _read_wallpaper(ctx, item["sourcePath"], item["outputName"])
        else:
            files["preview.png"] = encode_swatch_png(draft["palette"])
        return files

    def _rendered_shell(self, ctx: Any, draft: dict[str, Any]) -> str:
        template_path, template = _preview_template(ctx)
        if template is None:
            raise CcError("themes_render_failed", f"Theme template is missing: {template_path}")
        try:
            shell = render_shell(template.decode("utf-8"), draft["palette"], draft.get("sections", {}))
        except (UnicodeDecodeError, ValueError) as error:
            raise CcError("themes_render_failed", str(error)) from error
        if "{{" in shell:
            raise CcError("themes_render_failed", "Rendered shell.toml contains an unresolved placeholder")
        parse_shell(shell)
        return shell

    def plan(self, ctx: Any, draft: dict[str, Any], status: Status) -> Plan:
        slug = draft["slug"]
        theme_root = ctx.paths.home / ".config/omarchy/themes"
        target = theme_root / slug
        sidecar = ctx.paths.module_state(self.id) / f"{slug}.json"
        if draft.get("kind") == "activate":
            return self._activation_plan(ctx, draft, status)
        if draft.get("delete") is True:
            operations = (ops.ReplaceDirectoryAtomic(ctx, target, None, True, f"Delete theme {slug}"),
                          ops.RemoveFile(ctx, sidecar, f"Remove ownership record for {slug}"))
            warning = Warning(f"themes_delete:{slug}", f"Delete user theme {slug} at {target}", str(target),
                              "Type or confirm the named theme; rollback restores the directory", True)
            return Plan(self.id, status.revision, operations, (ResourceClaim(f"file:{target}", "exclusive"),),
                        f"Delete theme {slug}", (warning,), (warning.code,))
        if draft.get("tryInShell") is True:
            if status.data.get("openPreviewTransaction") is not None:
                raise CcError("themes_preview_open", "Stop the current Try in shell transaction before starting another")
            current_colors = _read_bytes(ctx.paths.home / ".local/state/omarchy/current/theme/colors.toml")
            current_shell = _read_bytes(ctx.paths.home / ".local/state/omarchy/current/theme/shell.toml")
            exact, reason = _exact_preview_restore(current_colors, current_shell)
            eligibility = status.data.get("tryInShellEligibility", {})
            if not eligibility.get("shellReachable") or not exact:
                raise CcError("capability_missing", reason or eligibility.get("reason") or "The Omarchy shell did not answer ping")
            colors = colors_toml(draft["palette"]).encode(); shell = self._rendered_shell(ctx, draft).encode()
            if max(len(colors), len(shell), len(current_colors or b""), len(current_shell or b"")) > 65536:
                raise CcError("themes_preview_too_large", "A Try in shell payload exceeds 64 KiB")
            inverse = ops.ShellIpc(ctx, "applyTheme", (base64.b64encode(current_colors or b"").decode(), base64.b64encode(current_shell or b"").decode()), summary="Restore the running shell theme")
            operation = ops.ShellIpc(ctx, "applyTheme", (base64.b64encode(colors).decode(), base64.b64encode(shell).decode()), inverse=inverse, summary=f"Try theme {slug} in shell", detail={"preview": True, "slug": slug})
            return Plan(self.id, status.revision, (operation,), (ResourceClaim("theme.shell-preview", "exclusive"),),
                        f"Try theme {slug} in shell", (), ())

        existing_sidecar = ctx.paths.read_json(sidecar, default=None)
        classification, inventory = classify(target, existing_sidecar)
        if classification in {"git", "symlink", "unsupported"}:
            raise CcError("themes_target_readonly", f"Theme {slug} is {classification}; duplicate it under a new slug")
        warning_code = f"themes_replace_unmanaged:{slug}"
        accepted = set(draft.get("acceptedWarnings", [])); warnings: list[Warning] = []
        if classification in {"plain", "managed-modified"}:
            warning = Warning(warning_code, f"Replacing {target} removes: {', '.join(inventory) or 'all existing files'}", str(target), "Duplicate the theme or accept replacement", True)
            warnings.append(warning)
            if warning_code not in accepted:
                raise CcError("themes_replace_unmanaged", warning.message, {"warning": warning_code, "files": inventory})
        files = self._generated(ctx, draft)
        rendered_shell = self._rendered_shell(ctx, draft)
        plan_id = hashlib.sha256((status.revision + json.dumps(draft, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()[:16]
        staging = ctx.paths.state / "staging/themes" / plan_id; staged_theme = staging / "theme"
        operations: list[Any] = [ops.EnsureDirectory(ctx, theme_root, "0755", "Ensure the user theme directory"),
                                 ops.EnsureDirectory(ctx, staged_theme, "0755", "Create theme staging directory")]
        if any(name.startswith("backgrounds/") for name in files):
            operations.append(ops.EnsureDirectory(ctx, staged_theme / "backgrounds", "0755", "Create staged wallpaper directory"))
        for name, content in sorted(files.items()):
            operations.append(ops.WriteFileAtomic(ctx, staged_theme / name, content, "0644", f"Stage {name}"))
        replacement = ops.ReplaceDirectoryAtomic(ctx, target, staged_theme, classification != "absent", f"Save theme {slug}")
        operations.append(replacement)
        sidecar_document = {"schemaVersion": 1, "slug": slug, "transactionId": plan_id,
                            "savedAt": ctx.clock.now_iso(), "files": _file_hashes(files)}
        operations.append(ops.WriteFileAtomic(ctx, sidecar, json.dumps(sidecar_document, sort_keys=True, separators=(",", ":")) + "\n", "0644", f"Record ownership of {slug}"))
        claims = [ResourceClaim(f"file:{target}", "exclusive"), ResourceClaim(f"file:{sidecar}", "exclusive")]
        for item in diagnostics(resolve_tokens(draft, status.data.get("machineOverride", {}).get("values", {}))):
            if not item["passes"] and not item["blocked"]:
                warnings.append(Warning(item["warningId"], f"{item['pairId']} contrast is {item['ratio']}:1", "", f"Use {item['nearestPaletteKey'] or 'a higher contrast color'}", item["warningId"] not in accepted))
        if draft.get("activate"):
            detail = self._verify_detail(ctx, draft, status, files["colors.toml"], rendered_shell)
            operations.extend(self._activation_operations(ctx, draft, status, replacement.id, detail))
            claims.append(ResourceClaim("theme.current", "exclusive"))
        if not draft.get("wallpapers"):
            warnings.append(Warning("themes_no_wallpaper", "No wallpaper was selected", str(target / "preview.png"), "Add a wallpaper or keep the current desktop background"))
        confirmations = tuple(warning.code for warning in warnings if warning.ack)
        summary = f"Create theme {slug} ({len(files)} files, {len(draft.get('wallpapers', []))} wallpapers)"
        residual = ("Theme-set hooks and application retints cannot be undone exactly",) if draft.get("activate") else ()
        return Plan(self.id, status.revision, tuple(operations), tuple(claims), summary, tuple(warnings), confirmations, residual)

    def _verify_detail(self, ctx: Any, draft: dict[str, Any], status: Status, colors: bytes | None = None, shell: str | None = None) -> dict[str, Any]:
        slug = draft["slug"]
        entry = next((item for item in status.data.get("themes", []) if item.get("slug") == slug), None)
        if colors is None and entry:
            colors = _read_bytes(Path(entry["path"]) / "colors.toml")
        if shell is None and colors is not None:
            palette = _parse_colors(Path(entry["path"]) / "colors.toml") if entry else {}
            if palette:
                import_draft = {"palette": palette, "sections": {}}
                shell = self._rendered_shell(ctx, import_draft)
        return {"slug": slug, "colorsB64": base64.b64encode(colors or b"").decode(), "shellToml": shell or "",
                "customSections": [name for name, value in draft.get("sections", {}).items() if value is not None],
                "preferredWallpaper": _saved_preferred(draft), "previousBackground": status.data.get("active", {}).get("background"),
                "shellWasReachable": bool(status.data.get("tryInShellEligibility", {}).get("shellReachable")), "unaffected": _unaffected(status.data, slug),
                "unaffectedState": _unaffected_state(status.data, slug)}

    def _activation_operations(self, ctx: Any, draft: dict[str, Any], status: Status,
                               directory_operation_id: str | None = None, detail: dict[str, Any] | None = None) -> list[Any]:
        slug = draft["slug"]; previous = status.data.get("active", {}).get("slug"); preferred = _saved_preferred(draft)
        argv = ["omarchy-theme-set", slug]
        inverse_argv = ["omarchy-theme-set", previous] if previous else None
        if preferred:
            argv = ["env", "OMARCHY_THEME_SKIP_BACKGROUND=1", *argv]
            if inverse_argv:
                inverse_argv = ["env", "OMARCHY_THEME_SKIP_BACKGROUND=1", *inverse_argv]
        activation = ops.RunCommand(ctx, argv, timeout_s=120, capture_limit=65536,
                                    summary=f"Activate {slug} with omarchy-theme-set", inverse=inverse_argv,
                                    inverse_after=(directory_operation_id,) if directory_operation_id else (), detail=detail)
        operations = [activation]
        if preferred:
            path = preferred if draft.get("kind") == "activate" else str(ctx.paths.home / ".local/state/omarchy/current/theme/backgrounds" / preferred)
            previous_background = status.data.get("active", {}).get("background")
            operations.append(ops.RunCommand(ctx, ["omarchy-theme-bg-set", path], timeout_s=10,
                                             summary=f"Set wallpaper {Path(path).name}", inverse=["omarchy-theme-bg-set", previous_background] if previous_background else None,
                                             inverse_after=(activation.id,)))
        return operations

    def _activation_plan(self, ctx: Any, draft: dict[str, Any], status: Status) -> Plan:
        entry = next((item for item in status.data.get("themes", []) if item.get("slug") == draft["slug"]), None)
        warnings: list[Warning] = []
        if entry and entry.get("source") == "user" and entry.get("classification") == "plain" and entry.get("unsupportedFiles"):
            files = ", ".join(entry["unsupportedFiles"])
            warnings.append(Warning("themes_activation_untrusted_files", f"This plain theme includes executable or config-bearing files: {files}", entry["path"], "Inspect these files before activation", True))
        detail = self._verify_detail(ctx, draft, status)
        operations = tuple(self._activation_operations(ctx, draft, status, detail=detail))
        confirmations = tuple([warning.code for warning in warnings if warning.ack] + [operation.id for operation in operations if operation.inverse is None])
        return Plan(self.id, status.revision, operations, (ResourceClaim("theme.current", "exclusive"),),
                    f"Activate theme {draft['slug']}", tuple(warnings), confirmations,
                    ("Theme-set hooks and application retints cannot be undone exactly",))

    def verify(self, ctx: Any, plan: Plan, status_after: Status, results: dict[str, Any]) -> VerifyResult:
        replacement = next((operation for operation in plan.operations if operation.kind == "ReplaceDirectoryAtomic" and operation.params.get("staged_dir")), None)
        sidecar_write = next((operation for operation in plan.operations if operation.kind == "WriteFileAtomic" and operation.params.get("path", "").endswith(".json") and "/themes/" in operation.params.get("path", "")), None)
        if replacement and sidecar_write:
            sidecar = json.loads(sidecar_write.params["content"]); target = Path(replacement.params["path"]); actual: dict[str, str] = {}
            try:
                if not target.is_dir():
                    raise OSError("target directory is missing")
                for path in target.rglob("*"):
                    if path.is_symlink() or path.is_file() and path.stat().st_mode & 0o111:
                        return VerifyResult("fail", "full", "Check save: theme contains a symlink or executable file", "themes_verify_files", {"path": str(path)})
                    if path.is_file(): actual[str(path.relative_to(target))] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as error:
                return VerifyResult("fail", "full", f"Check save: {error}", "themes_verify_files")
            if actual != sidecar["files"]:
                return VerifyResult("fail", "full", "Check save: files do not match the ownership record", "themes_verify_files", {"expected": sidecar["files"], "actual": actual})
        activation = next((operation for operation in plan.operations if operation.kind == "RunCommand" and "omarchy-theme-set" in operation.params.get("argv", [])), None)
        if not activation:
            return VerifyResult("pass", "full", "", evidence={"revision": status_after.revision})
        detail = activation.detail or {}; slug = detail.get("slug") or activation.params["argv"][-1]
        active = status_after.data.get("active", {})
        if active.get("slug") != slug:
            return VerifyResult("fail", "full", f"Check 1: theme.name did not become {slug}", "themes_verify_active", {"check": 1, "actual": active})
        current = ctx.paths.home / ".local/state/omarchy/current/theme"
        expected_colors = base64.b64decode(detail.get("colorsB64", ""))
        if not expected_colors or _read_bytes(current / "colors.toml") != expected_colors:
            return VerifyResult("fail", "full", "Check 2: active colors.toml differs from the candidate", "themes_verify_colors", {"check": 2})
        expected_shell = detail.get("shellToml", "")
        try:
            actual_shell_text = (current / "shell.toml").read_text(encoding="utf-8")
            actual_shell = parse_shell(actual_shell_text); expected_parsed = parse_shell(expected_shell)
        except (FileNotFoundError, OSError, UnicodeDecodeError) as error:
            return VerifyResult("fail", "full", f"Check 3: active shell.toml is unreadable: {error}", "themes_verify_sections", {"check": 3})
        if not expected_shell or actual_shell != expected_parsed:
            return VerifyResult("fail", "full", "Check 3: rendered shell sections differ from the candidate", "themes_verify_sections", {"check": 3, "expected": expected_parsed, "actual": actual_shell})
        try:
            for path in current.rglob("*"):
                if path.is_file() and path.name in _TEMPLATE_OUTPUTS and path.stat().st_size <= 1024 * 1024 and b"{{" in path.read_bytes():
                    return VerifyResult("fail", "full", "Check 4: rendered output contains an unresolved placeholder", "themes_verify_placeholder", {"check": 4, "path": str(path)})
        except OSError as error:
            return VerifyResult("fail", "full", f"Check 4: rendered output could not be inspected: {error}", "themes_verify_placeholder", {"check": 4})
        for name in detail.get("customSections", []):
            if not (current / f"shell.{name}.toml").is_file():
                return VerifyResult("fail", "full", f"Check 5: shell.{name}.toml is missing", "themes_verify_fragment", {"check": 5, "section": name})
        preferred = detail.get("preferredWallpaper")
        background = active.get("background")
        if preferred:
            expected = Path(preferred) if Path(preferred).is_absolute() else current / "backgrounds" / preferred
            if not background or Path(background).absolute() != expected.absolute() or not expected.is_file():
                return VerifyResult("fail", "full", "Check 6: preferred wallpaper was not activated", "themes_verify_background", {"check": 6, "expected": str(expected), "actual": background})
        else:
            no_wallpaper = any(warning.code == "themes_no_wallpaper" for warning in plan.warnings)
            previous_background = detail.get("previousBackground")
            if no_wallpaper and background != previous_background:
                return VerifyResult("fail", "full", "Check 6: activation changed the wallpaper despite the no-wallpaper warning", "themes_verify_background",
                                    {"check": 6, "expected": previous_background, "actual": background})
            if background and not Path(background).is_file():
                return VerifyResult("fail", "full", "Check 6: active wallpaper target is missing", "themes_verify_background", {"check": 6, "actual": background})
            if not no_wallpaper and not background:
                return VerifyResult("fail", "full", "Check 6: activation did not select a wallpaper", "themes_verify_background", {"check": 6, "actual": background})
        if detail.get("shellWasReachable") and not _shell_reachable(ctx):
            return VerifyResult("fail", "full", "Check 7: shell stopped answering ping", "themes_verify_shell", {"check": 7})
        actual_unaffected_state = _unaffected_state(status_after.data, slug)
        actual_unaffected = _unaffected(status_after.data, slug)
        if detail.get("unaffected") != actual_unaffected:
            expected_state = detail.get("unaffectedState", {})
            changed = sorted(key for key in set(expected_state) | set(actual_unaffected_state)
                             if expected_state.get(key) != actual_unaffected_state.get(key))
            return VerifyResult("fail", "full", f"Check 8: unrelated theme inputs changed during activation ({', '.join(changed)})", "themes_concurrent_change",
                                {"check": 8, "expected": detail.get("unaffected"), "actual": actual_unaffected,
                                 "changed": changed})
        return VerifyResult("pass", "full", "", evidence={"revision": status_after.revision, "checks": list(range(1, 9))})

    def _import_draft(self, ctx: Any, status: Status, slug: str, duplicate_slug: str | None = None) -> dict[str, Any]:
        entry = next((item for item in status.data.get("themes", []) if item.get("slug") == slug), None)
        if entry is None or entry.get("classification") == "symlink":
            raise CcError("themes_target_readonly", f"Theme {slug} cannot be imported")
        path = Path(entry["path"]); palette = _parse_colors(path / "colors.toml")
        if not palette:
            raise CcError("themes_palette_missing", f"Theme {slug} has no importable colors.toml")
        sections: dict[str, Any] = {name: None for name in SECTIONS}; unsupported_keys: list[str] = []
        for name in SECTIONS:
            fragment = path / f"shell.{name}.toml"
            if not fragment.is_file(): continue
            try: values = parse_shell(fragment.read_text(encoding="utf-8")).get(name, {})
            except (OSError, UnicodeDecodeError): values = {}
            table = {item[0] for item in SECTIONS[name]}; unsupported_keys.extend(f"{name}.{key}" for key in values if key not in table)
            materialized = defaults(name, palette); materialized.update({key: value for key, value in values.items() if key in table})
            sections[name] = materialized
        wallpapers = []
        for index, source in enumerate(entry.get("wallpaperPaths", [])[:12], 1):
            tail = re.sub(r"[^a-z0-9._-]+", "-", Path(source).name.lower()).strip("-.") or f"wallpaper{Path(source).suffix.lower()}"
            wallpapers.append({"sourcePath": str(Path(source).absolute()), "outputName": f"{index:02d}-{tail}"})
        icon = None
        try: icon = (path / "icons.theme").read_text(encoding="utf-8").strip() or None
        except (FileNotFoundError, OSError, UnicodeDecodeError): pass
        revision = "sha256:" + hashlib.sha256(json.dumps({"entry": entry, "colors": palette}, sort_keys=True).encode()).hexdigest()
        return {"draft": {"schemaVersion": 1, "kind": "compose", "slug": duplicate_slug or slug,
                "displayName": (duplicate_slug or slug).replace("-", " ").title(),
                "origin": {"type": entry["source"], "slug": slug, "revision": revision}, "palette": palette,
                "sections": sections, "wallpapers": wallpapers, "preferredWallpaper": wallpapers[0]["outputName"] if wallpapers else None,
                "iconTheme": icon, "acceptedWarnings": []}, "unsupportedFiles": entry.get("unsupportedFiles", []),
                "unsupportedKeys": unsupported_keys}

    def query(self, ctx: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
        status = self.status(ctx)
        if name == "import":
            return self._import_draft(ctx, status, str(args.get("slug", "")), args.get("duplicateSlug"))
        if name != "preview":
            raise CcError("unknown_query", f"Unknown themes query: {name}")
        draft = args.get("draft")
        validation = self.validate(ctx, draft, status) if isinstance(draft, dict) else ValidationResult(False, (), None)
        if not validation.ok or validation.normalized_draft is None or validation.normalized_draft.get("kind") != "compose":
            raise CcError("validation_failed", "Preview requires a valid compose draft", {"issues": [issue.to_json() for issue in validation.issues]})
        normalized = validation.normalized_draft; colors = colors_toml(normalized["palette"]); shell = self._rendered_shell(ctx, normalized)
        tokens = resolve_tokens(normalized, status.data.get("machineOverride", {}).get("values", {}), not bool(args.get("portable")))
        payload = preview_payload(colors, shell, tokens); payload["contrast"] = diagnostics(tokens)
        return payload

    def migrate(self, ctx: Any, kind: str, document: dict[str, Any], from_version: int) -> dict[str, Any]:
        if from_version == 1: return dict(document)
        raise CcError("unsupported_config", f"No themes {kind} migration from version {from_version}")


MODULE = ThemesModule()
