from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from customization_center.modules import MODULES
from customization_center.core.context import build_context
from customization_center.core.migrate import upgrade
from customization_center.core.operations import _KINDS, validate_operation
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry
from customization_center.core.schema_check import load_and_validate, validate

ROOT = Path(__file__).resolve().parents[2]
IDS = [*MODULES, "hello"]
SERVICE_MODULES = {"shell_ipc": "shell_ipc", "hyprctl": "hyprctl", "managed_block": "managed_block",
 "jsonc": "jsonc", "lua": "lua", "toml_writer": "toml_writer", "drafts": "drafts",
 "settings_schema": "settings_schema", "catalog": "catalog"}


def _directory(module_id: str) -> Path:
    return ROOT / (f"tests/fixtures/modules/{module_id}" if module_id == "hello" else f"modules/{module_id}")


def _registry(paths: Paths):
    return load_registry(ROOT, [ROOT / "tests/fixtures/modules/hello"], paths)


@pytest.mark.parametrize("module_id", IDS)
def test_registered_module_contract(module_id, isolated_home):
    paths = Paths.from_env(); directory = _directory(module_id); registry = _registry(paths)
    metadata = load_and_validate(directory / "module.json", ROOT / "schemas/module-v1.json")
    entry = registry.view.entry(module_id); module = entry.module
    assert module.id == directory.name == metadata["id"]
    sample = json.loads((directory / "tests/fixtures/sample-draft.json").read_text())
    before = {str(p): (p.stat().st_mode, p.read_bytes()) for p in isolated_home.rglob("*") if p.is_file()}
    status = module.status(build_context(module_id, "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    capabilities = module.capabilities(build_context(module_id, "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    validation = module.validate(build_context(module_id, "validate", paths=paths, registry=registry.view, plugin_dir=ROOT), sample, status)
    assert validation.ok and validation.normalized_draft is not None and capabilities.module_id == module_id
    plan = module.plan(build_context(module_id, "plan", paths=paths, registry=registry.view, plugin_dir=ROOT), validation.normalized_draft, status)
    after = {str(p): (p.stat().st_mode, p.read_bytes()) for p in isolated_home.rglob("*") if p.is_file()}
    assert before == after
    status_schema = json.loads((directory / metadata["statusSchema"]).read_text())
    validate(status.data, status_schema, "status")
    declared = set(plan.requires_confirmation)
    assert {op.id for op in plan.operations if op.inverse is None} <= declared
    assert {warning.code for warning in plan.warnings if warning.ack} <= declared
    for operation in plan.operations:
        assert operation.kind in _KINDS
        validate_operation(operation, paths,
            [paths.expand_template(item, operation.module_id) for item in metadata.get("extraWritablePaths", [])])


@pytest.mark.parametrize("module_id", IDS)
def test_imports_and_declared_services(module_id):
    directory = _directory(module_id); metadata = json.loads((directory / "module.json").read_text())
    source = (directory / "backend/__init__.py").read_text(); tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module not in {"__future__", "customization_center.core"}:
            raise AssertionError(f"disallowed import from {node.module}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in {"json", "re", "hashlib", "base64", "math", "typing", "dataclasses"}
    declared = set(metadata["coreServices"])
    for service, module_name in SERVICE_MODULES.items():
        if f"import {module_name}" in source or f" {module_name}," in source:
            assert service in declared
    if "ctx.registry" in source: assert "registry" in declared
    if "ops.TimedConfirmation" in source: assert "timed_confirmation" in declared
    if "ops.TerminalHandoff" in source: assert "terminal_handoff" in declared
    if "paths.staging_dir" in source: assert "staging" in declared


def _minimal(schema, version=1):
    if "const" in schema: return schema["const"]
    if "enum" in schema: return schema["enum"][0]
    kind = schema.get("type")
    if isinstance(kind, list): kind = next(item for item in kind if item != "null")
    if kind == "object" or "properties" in schema:
        value = {name: _minimal(schema.get("properties", {}).get(name, {}), version)
                 for name in schema.get("required", [])}
        if "schemaVersion" in schema.get("properties", {}): value["schemaVersion"] = version
        return value
    if kind == "array": return []
    if kind == "integer" or kind == "number": return schema.get("minimum", 0)
    if kind == "boolean": return False
    return "x"


@pytest.mark.parametrize("module_id", IDS)
def test_stored_document_schemas_and_migrations(module_id, isolated_home):
    paths = Paths.from_env(); registry = _registry(paths); entry = registry.view.entry(module_id)
    module = entry.module; ctx = build_context(module_id, "validate", paths=paths, registry=registry.view, plugin_dir=ROOT)
    for stored in entry.metadata.get("storedDocuments", []):
        current = module.schema_version
        schemas = []
        for version in range(1, current + 1):
            schema_path = entry.directory / "schemas" / f"{stored['kind']}-v{version}.json"
            assert schema_path.is_file()
            schemas.append(json.loads(schema_path.read_text()))
        document = _minimal(schemas[0], 1)
        upgraded = upgrade(module, stored["kind"], document, ctx)
        validate(upgraded, schemas[-1], f"{module_id} {stored['kind']} current")
