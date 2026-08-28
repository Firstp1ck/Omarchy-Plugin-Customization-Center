from __future__ import annotations

import hashlib
import json
import mimetypes
import stat
from pathlib import Path
from typing import Any

from .atomic import write_bytes_atomic
from .errors import CcError
from .schema_check import validate

_MAX_ASSET = 64 * 1024 * 1024
_ALLOWED_IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
_ALLOWED_TEXT = {".txt", ".json", ".jsonc", ".toml", ".lua", ".md", ".css"}


def _path(paths: Any, module_id: str) -> Path:
    return paths.drafts / module_id / "current.json"


def _schema(plugin_dir: str | Path) -> dict[str, Any]:
    try:
        return json.loads((Path(plugin_dir) / "schemas/draft-envelope-v1.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CcError("unsupported_config", "Draft envelope schema is unavailable") from error


def _validate_envelope(document: Any, module_id: str, plugin_dir: str | Path | None) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise CcError("invalid_draft", "Draft must be a JSON object")
    if plugin_dir is not None:
        try:
            validate(document, _schema(plugin_dir), "draft envelope")
        except CcError as error:
            raise CcError("invalid_draft", error.message, error.data) from error
    required = {"schemaVersion", "module", "baseRevision", "updatedAt", "draft"}
    if not required.issubset(document) or document.get("schemaVersion") != 1 or document.get("module") != module_id or not isinstance(document.get("draft"), dict):
        raise CcError("invalid_draft", "Draft envelope is invalid")
    return document


def load(paths: Any, module_id: str, plugin_dir: str | Path | None = None) -> dict[str, Any] | None:
    try:
        document = json.loads(_path(paths, module_id).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as error:
        raise CcError("invalid_draft", "Saved draft is malformed JSON") from error
    return _validate_envelope(document, module_id, plugin_dir)


def save(paths: Any, module_id: str, document: dict[str, Any], plugin_dir: str | Path | None = None) -> dict[str, Any]:
    checked = _validate_envelope(document, module_id, plugin_dir)
    payload = json.dumps(checked, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    write_bytes_atomic(_path(paths, module_id), payload, 0o600)
    return checked


def discard(paths: Any, module_id: str) -> bool:
    path = _path(paths, module_id)
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise CcError("unsupported_config", f"Refusing non-regular draft: {path}")
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def asset_add(paths: Any, module_id: str, source: str | Path) -> dict[str, Any]:
    path = Path(source).absolute()
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise CcError("invalid_draft", f"Asset does not exist: {path}") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise CcError("invalid_draft", "Draft asset must be a regular file")
    if info.st_size > _MAX_ASSET:
        raise CcError("invalid_draft", "Draft asset exceeds 64 MiB", {"size": info.st_size})
    suffix = path.suffix.lower()
    mime = mimetypes.guess_type(path.name)[0] or ""
    if suffix not in _ALLOWED_IMAGE | _ALLOWED_TEXT and not (mime.startswith("image/") or mime.startswith("text/")):
        raise CcError("invalid_draft", f"Unsupported draft asset type: {suffix or 'unknown'}")
    data = path.read_bytes()
    if suffix in _ALLOWED_TEXT or mime.startswith("text/") or suffix == ".svg":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise CcError("invalid_draft", "Text draft assets must be UTF-8") from error
        if "\x00" in text:
            raise CcError("invalid_draft", "Text draft assets may not contain NUL bytes")
    signatures = {
        ".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
        ".gif": (b"GIF87a", b"GIF89a"), ".webp": (b"RIFF",), ".bmp": (b"BM",),
    }
    if suffix in signatures and not any(data.startswith(item) for item in signatures[suffix]):
        raise CcError("invalid_draft", f"Asset content does not match {suffix} type")
    if suffix == ".webp" and (len(data) < 12 or data[8:12] != b"WEBP"):
        raise CcError("invalid_draft", "Asset content does not match .webp type")
    digest = hashlib.sha256(data).hexdigest()
    target = paths.drafts / module_id / "assets" / f"{digest}{suffix}"
    if not target.exists():
        write_bytes_atomic(target, data, 0o600)
    return {"path": str(target), "sha256": digest, "size": len(data), "type": mime or "application/octet-stream"}
