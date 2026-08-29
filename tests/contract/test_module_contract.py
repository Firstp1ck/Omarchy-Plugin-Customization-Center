from __future__ import annotations

import ast
import json
import shutil
import sys
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
SERVICE_MODULES = {
    "shell_ipc": {"shell_ipc"},
    "hyprctl": {"hyprctl"},
    "managed_block": {"managed_block"},
    "jsonc": {"jsonc"},
    "lua": {"lua", "lua_string", "luac_check"},
    "toml_writer": {"toml_writer"},
    "drafts": {"drafts"},
    "registry": {"registry"},
    "settings_schema": {"settings_schema"},
    "catalog": {"catalog"},
}
CORE_PACKAGE = "customization_center.core"
FORBIDDEN_IMPORTS = {"subprocess", "shutil", "tempfile", "socket"}
FORBIDDEN_OS_IMPORTS = {"system", "popen", "open"}
FORBIDDEN_CALL_ATTRIBUTES = {
    "write_text", "write_bytes", "unlink", "mkdir", "rmdir", "symlink", "touch", "chmod", "lchmod",
    "link", "hardlink_to", "symlink_to",
}
FORBIDDEN_FILESYSTEM_CALL_ATTRIBUTES = {
    "replace", "rename", "remove", "removedirs", "makedirs", "rmtree", "copy", "copy2", "copyfile",
    "copytree", "move",
}
FORBIDDEN_OS_CALL_ATTRIBUTES = {"system", "popen", "open"}
FILESYSTEM_RECEIVER_ROOTS = {"os", "shutil", "pathlib", "Path"}


class _BackendContractVisitor(ast.NodeVisitor):
    def __init__(self, source_path: Path, backend: Path):
        self.source_path = source_path
        self.backend = backend
        self.violations: list[str] = []
        self.service_uses: dict[str, tuple[Path, int]] = {}

    def _error(self, node: ast.AST, message: str) -> None:
        self.violations.append(f"{self.source_path.relative_to(ROOT)}:{node.lineno}: {message}")

    def _use_service(self, service: str, node: ast.AST) -> None:
        self.service_uses.setdefault(service, (self.source_path, node.lineno))

    def _check_import_name(self, node: ast.AST, name: str) -> None:
        root = name.split(".")[0]
        if root not in sys.stdlib_module_names and not (name == CORE_PACKAGE or name.startswith(f"{CORE_PACKAGE}.")):
            self._error(node, f"disallowed import {name}")
        if root in FORBIDDEN_IMPORTS:
            self._error(node, f"forbidden import {name}")
        if name in {f"os.{item}" for item in FORBIDDEN_OS_IMPORTS}:
            self._error(node, f"forbidden import {name}")

    def _record_core_import(self, node: ast.ImportFrom | ast.Import, name: str) -> None:
        if name == CORE_PACKAGE:
            return
        if name.startswith(f"{CORE_PACKAGE}."):
            service_name = name.removeprefix(f"{CORE_PACKAGE}.").split(".")[0]
            for service, import_names in SERVICE_MODULES.items():
                if service_name in import_names:
                    self._use_service(service, node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import_name(node, alias.name)
            self._record_core_import(node, alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            parent = self.source_path.parent
            for _ in range(node.level - 1):
                parent = parent.parent
            if not parent.is_relative_to(self.backend):
                self._error(node, "relative import escapes the backend package")
        elif node.module is not None:
            self._check_import_name(node, node.module)
            self._record_core_import(node, node.module)
            if node.module == "os" and any(alias.name in FORBIDDEN_OS_IMPORTS or alias.name == "*"
                                       for alias in node.names):
                self._error(node, f"forbidden import from {node.module}")
            if node.module == CORE_PACKAGE:
                for alias in node.names:
                    for service, import_names in SERVICE_MODULES.items():
                        if alias.name in import_names:
                            self._use_service(service, node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.value, ast.Name):
            if node.value.id == "ctx" and node.attr in {"shell", "hyprctl", "registry"}:
                self._use_service({"shell": "shell_ipc", "hyprctl": "hyprctl", "registry": "registry"}[node.attr], node)
            elif node.value.id == "ops" and node.attr == "TimedConfirmation":
                self._use_service("timed_confirmation", node)
            elif node.value.id == "ops" and node.attr == "TerminalHandoff":
                self._use_service("terminal_handoff", node)
            elif node.value.id == "paths" and node.attr == "staging_dir":
                self._use_service("staging", node)
        self.generic_visit(node)

    @staticmethod
    def _receiver_root(receiver: ast.expr) -> str | None:
        while isinstance(receiver, ast.Attribute):
            receiver = receiver.value
        return receiver.id if isinstance(receiver, ast.Name) else None

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            mode = node.args[1] if len(node.args) > 1 else next(
                (keyword.value for keyword in node.keywords if keyword.arg == "mode"), None)
            if isinstance(mode, ast.Constant) and isinstance(mode.value, str) and any(flag in mode.value for flag in "wa+"):
                self._error(node, f"forbidden write mode for open: {mode.value!r}")
        elif isinstance(node.func, ast.Attribute):
            receiver_root = self._receiver_root(node.func.value)
            if node.func.attr in FORBIDDEN_CALL_ATTRIBUTES:
                self._error(node, f"forbidden call to {node.func.attr}")
            elif node.func.attr in FORBIDDEN_FILESYSTEM_CALL_ATTRIBUTES and receiver_root in FILESYSTEM_RECEIVER_ROOTS:
                self._error(node, f"forbidden call to {node.func.attr}")
            elif node.func.attr in FORBIDDEN_OS_CALL_ATTRIBUTES and receiver_root == "os":
                self._error(node, f"forbidden call to {node.func.attr}")
        self.generic_visit(node)


def _backend_sources(module_id: str) -> list[Path]:
    return sorted((_directory(module_id) / "backend").rglob("*.py"))


def _relative_imports_stay_in_backend(tree: ast.AST, source_path: Path, backend: Path) -> _BackendContractVisitor:
    visitor = _BackendContractVisitor(source_path, backend)
    visitor.visit(tree)
    return visitor


def _directory(module_id: str) -> Path:
    return ROOT / (f"tests/fixtures/modules/{module_id}" if module_id == "hello" else f"modules/{module_id}")


def _registry(paths: Paths):
    return load_registry(ROOT, [ROOT / "tests/fixtures/modules/hello"], paths)


def _install_contract_stubs(directory: Path, isolated_home: Path, request) -> None:
    fixture = directory / "tests/fixtures/contract-stubs.json"
    if not fixture.is_file():
        return
    stubs = json.loads(fixture.read_text())
    for home_relative, fixture_relative in stubs.pop("files", {}).items():
        source = (fixture.parent / fixture_relative).resolve()
        destination = (isolated_home / home_relative).resolve()
        assert source.is_relative_to(fixture.parent.resolve())
        assert destination.is_relative_to(isolated_home.resolve())
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    stub_command = request.getfixturevalue("stub_command")
    for name, handler in stubs.items():
        stub_command(name, handler)


def test_contract_stubs_copy_files(tmp_path, isolated_home, request):
    directory = tmp_path / "module"
    fixture_dir = directory / "tests/fixtures"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "seed.lua").write_text("monitor = {}\n")
    (fixture_dir / "contract-stubs.json").write_text(json.dumps({
        "files": {".config/hypr/monitors.lua": "seed.lua"},
    }))

    _install_contract_stubs(directory, isolated_home, request)

    assert (isolated_home / ".config/hypr/monitors.lua").read_text() == "monitor = {}\n"


@pytest.mark.parametrize("module_id", IDS)
def test_registered_module_contract(module_id, isolated_home, request):
    directory = _directory(module_id)
    _install_contract_stubs(directory, isolated_home, request)
    paths = Paths.from_env(); registry = _registry(paths)
    metadata = load_and_validate(directory / "module.json", ROOT / "schemas/module-v1.json")
    entry = registry.view.entry(module_id); module = entry.module
    assert module.id == directory.name == metadata["id"]
    sample = json.loads((directory / "tests/fixtures/sample-draft.json").read_text())
    before = {str(p): (p.stat().st_mode, p.read_bytes()) for p in isolated_home.rglob("*") if p.is_file()}
    status = module.status(build_context(module_id, "read", paths=paths, registry=registry.view, plugin_dir=ROOT))
    if "baseRevision" in sample:
        sample["baseRevision"] = status.revision
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
    backend = directory / "backend"; visitors = []
    for source_path in _backend_sources(module_id):
        tree = ast.parse(source_path.read_text(), filename=str(source_path))
        visitors.append(_relative_imports_stay_in_backend(tree, source_path, backend))

    violations = [violation for visitor in visitors for violation in visitor.violations]
    declared = set(metadata["coreServices"])
    for visitor in visitors:
        for service, (source_path, line) in visitor.service_uses.items():
            if service not in declared:
                violations.append(f"{source_path.relative_to(ROOT)}:{line}: core service {service} is not declared")
    if violations:
        pytest.fail("\n".join(violations))


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
