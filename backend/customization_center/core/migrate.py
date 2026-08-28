from __future__ import annotations

import json
from typing import Any

from .errors import CcError
from .schema_check import validate


def upgrade(module: Any, kind: str, document: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    if not isinstance(document, dict) or not isinstance(document.get("schemaVersion"), int):
        raise CcError("invalid_draft", "Document must contain an integer schemaVersion")
    current = int(module.schema_version)
    version = int(document["schemaVersion"])
    if version > current:
        raise CcError("schema_version_unsupported", f"Document schema {version} is newer than supported {current}",
                      {"documentVersion": version, "supportedVersion": current})
    migrated = dict(document)
    while version < current:
        method = getattr(module, "migrate", None)
        if method is None:
            raise CcError("schema_version_unsupported", f"No migration from schema {version}",
                          {"documentVersion": version, "supportedVersion": current})
        result = method(ctx, kind, migrated, version)
        if not isinstance(result, dict) or result.get("schemaVersion") != version + 1:
            raise CcError("schema_version_unsupported", f"Migration from schema {version} did not produce schema {version + 1}")
        migrated = result
        version += 1
    if ctx is not None and getattr(ctx, "registry", None) is not None:
        entry = ctx.registry.entry(module.id)
        if kind == "draft":
            relative = entry.metadata.get("draftSchema")
        else:
            relative = next((item.get("schema") for item in entry.metadata.get("storedDocuments", [])
                             if item.get("kind") == kind), None)
        if not relative:
            raise CcError("unsupported_config", f"Unknown stored document kind for {module.id}: {kind}",
                          {"kind": kind})
        try:
            schema = json.loads((entry.directory / relative).read_text(encoding="utf-8"))
            validate(migrated, schema, f"{module.id} {kind}")
        except CcError as error:
            raise CcError("invalid_draft", f"Migrated {kind} document is invalid", error.data) from error
        except (OSError, json.JSONDecodeError) as error:
            raise CcError("unsupported_config", f"Schema is unavailable for {module.id} {kind}") from error
    return migrated
