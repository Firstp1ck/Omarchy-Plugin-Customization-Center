from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from customization_center.core.drafts import discard, load, save
from customization_center.core.errors import CcError
from customization_center.core.migrate import upgrade
from customization_center.core.paths import Paths


def test_draft_round_trip(isolated_home):
    paths = Paths.from_env()
    envelope = {"schemaVersion": 1, "module": "hello", "baseRevision": "r",
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "draft": {"schemaVersion": 1, "message": "hello"}}
    save(paths, "hello", envelope)
    assert load(paths, "hello") == envelope
    assert discard(paths, "hello")


def test_migration_steps_and_rejects_newer():
    module = SimpleNamespace(schema_version=2,
        migrate=lambda ctx, kind, document, version: {**document, "schemaVersion": version + 1})
    assert upgrade(module, "draft", {"schemaVersion": 1})["schemaVersion"] == 2
    with pytest.raises(CcError, match="newer"):
        upgrade(module, "draft", {"schemaVersion": 3})


def test_unknown_migration_kind_is_rejected(tmp_path: Path):
    entry = SimpleNamespace(directory=tmp_path, metadata={"draftSchema": "draft.json", "storedDocuments": []})
    ctx = SimpleNamespace(registry=SimpleNamespace(entry=lambda module_id: entry))
    module = SimpleNamespace(id="sample", schema_version=1)
    with pytest.raises(CcError) as caught:
        upgrade(module, "unknown", {"schemaVersion": 1}, ctx)
    assert caught.value.code == "unsupported_config" and "unknown" in caught.value.message


def test_migration_chain_must_reach_current_version():
    module = SimpleNamespace(schema_version=3,
        migrate=lambda ctx, kind, document, version: {**document, "schemaVersion": version + 2})
    with pytest.raises(CcError) as caught:
        upgrade(module, "draft", {"schemaVersion": 1})
    assert caught.value.code == "schema_version_unsupported"


def test_migration_validates_current_schema(tmp_path: Path):
    schema = tmp_path / "draft.json"
    schema.write_text('{"type":"object","required":["schemaVersion","name"],"properties":{"schemaVersion":{"const":2},"name":{"type":"string"}}}')
    entry = SimpleNamespace(directory=tmp_path, metadata={"draftSchema": "draft.json"})
    registry = SimpleNamespace(entry=lambda module_id: entry)
    ctx = SimpleNamespace(registry=registry)
    module = SimpleNamespace(id="sample", schema_version=2,
        migrate=lambda ctx, kind, document, version: {"schemaVersion": 2})
    with pytest.raises(CcError) as caught:
        upgrade(module, "draft", {"schemaVersion": 1}, ctx)
    assert caught.value.code == "invalid_draft"
