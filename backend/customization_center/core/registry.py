from __future__ import annotations

import importlib.util
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

from .errors import CcError
from .paths import Paths
from .schema_check import load_and_validate
from .types import Warning

_TEMPLATE = re.compile(r"\{(home|xdg_config_home|state|module_config|module_state)\}")


@dataclass(frozen=True)
class RegistryEntry:
    id: str
    module: Any
    metadata: dict[str, Any]
    directory: Path


class RegistryView:
    def __init__(self, entries: dict[str, RegistryEntry]) -> None:
        self.entries = dict(entries)

    def module(self, module_id: str) -> Any:
        try:
            return self.entries[module_id].module
        except KeyError as error:
            raise CcError("unknown_module", f"Unknown module: {module_id}") from error

    def entry(self, module_id: str) -> RegistryEntry:
        try:
            return self.entries[module_id]
        except KeyError as error:
            raise CcError("unknown_module", f"Unknown module: {module_id}") from error

    def __iter__(self):
        return iter(self.entries.values())


@dataclass(frozen=True)
class Registry:
    view: RegistryView
    warnings: tuple[Warning, ...]

    @property
    def entries(self) -> dict[str, RegistryEntry]:
        return self.view.entries

    def module(self, module_id: str) -> Any:
        return self.view.module(module_id)


def _load_ids() -> list[str]:
    from customization_center.modules import MODULES
    return list(MODULES)


def _module_dirs(plugin_dir: Path, extra_module_dirs: Iterable[str | Path] | None) -> tuple[list[str], dict[str, Path]]:
    ids = _load_ids()
    directories = {item: plugin_dir / "modules" / item for item in ids}
    extras = list(extra_module_dirs or ())
    environment = os.environ.get("CC_EXTRA_MODULE_DIRS", "")
    if environment:
        extras.extend(Path(value) for value in environment.split(os.pathsep) if value)
    for raw in extras:
        path = Path(raw).absolute()
        # An override may name one module or a directory containing modules.
        candidates = [path] if (path / "module.json").is_file() else [p for p in path.iterdir() if p.is_dir()]
        for candidate in candidates:
            module_id = candidate.name
            if module_id not in ids:
                ids.append(module_id)
            directories[module_id] = candidate
    return ids, directories


def _validate_extra_paths(metadata: dict[str, Any], paths: Paths, module_id: str) -> None:
    allowed_names = {"home", "xdg_config_home", "state", "module_config", "module_state"}
    for template in metadata.get("extraWritablePaths", []):
        if not isinstance(template, str) or not template.startswith(("/", "{")) or ".." in Path(template).parts:
            raise CcError("unsupported_config", f"Invalid extraWritablePaths template: {template!r}")
        unknown = set(re.findall(r"\{([^{}]+)\}", template)) - allowed_names
        if unknown:
            raise CcError("unsupported_config", f"Unknown path template name: {sorted(unknown)[0]}")
        expanded = Path(paths.expand_template(template, module_id)).absolute()
        user_roots = (paths.home, paths.xdg_config_home, paths.state.parent.parent)
        if (not expanded.is_absolute() or not any(expanded == root or expanded.is_relative_to(root) for root in user_roots)
                or expanded == paths.omarchy_path or expanded.is_relative_to(paths.omarchy_path)
                or not paths.symlink_safe(expanded)):
            raise CcError("permission_required", f"Extra writable path is unsafe: {template}")


def _import_backend(module_id: str, directory: Path) -> ModuleType:
    source = directory / "backend" / "__init__.py"
    if not source.is_file():
        raise CcError("unsupported_config", f"Backend does not exist: {source}")
    package_name = "cc_modules"
    if package_name not in sys.modules:
        package = ModuleType(package_name)
        package.__path__ = []  # type: ignore[attr-defined]
        sys.modules[package_name] = package
    name = f"{package_name}.{module_id}"
    spec = importlib.util.spec_from_file_location(name, source, submodule_search_locations=[str(source.parent)])
    if spec is None or spec.loader is None:
        raise CcError("unsupported_config", f"Cannot import backend: {source}")
    imported = importlib.util.module_from_spec(spec)
    sys.modules[name] = imported
    try:
        spec.loader.exec_module(imported)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return imported


def load_registry(plugin_dir: str | Path, extra_module_dirs: Iterable[str | Path] | None = None,
                  paths: Paths | None = None) -> Registry:
    root = Path(plugin_dir).absolute()
    schema = root / "schemas/module-v1.json"
    runtime_paths = paths or Paths.from_env()
    ids, directories = _module_dirs(root, extra_module_dirs)
    entries: dict[str, RegistryEntry] = {}
    warnings: list[Warning] = []
    for module_id in ids:
        try:
            directory = directories[module_id]
            metadata = load_and_validate(directory / "module.json", schema)
            if metadata.get("id") != module_id:
                raise CcError("unsupported_config", f"module.json id does not match directory: {module_id}")
            for relative in (metadata["page"], metadata["draftSchema"], metadata.get("statusSchema")):
                if relative and (Path(relative).is_absolute() or ".." in Path(relative).parts):
                    raise CcError("unsupported_config", f"Unsafe module path: {relative}")
            _validate_extra_paths(metadata, runtime_paths, module_id)
            imported = _import_backend(module_id, directory)
            module = getattr(imported, "MODULE", None)
            if module is None or getattr(module, "id", None) != module_id:
                raise CcError("unsupported_config", f"MODULE.id does not match {module_id}")
            entries[module_id] = RegistryEntry(module_id, module, metadata, directory)
        except Exception as error:
            message = error.message if isinstance(error, CcError) else str(error)
            warnings.append(Warning("registry", f"Module {module_id} is unavailable: {message}",
                                    recovery="Fix or remove the module registration"))
    return Registry(RegistryView(entries), tuple(warnings))
