from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .errors import CcError


def _omarchy_path(env: dict[str, str]) -> Path:
    if env.get("OMARCHY_PATH"):
        return Path(env["OMARCHY_PATH"]).expanduser().absolute()
    conf = Path("/etc/omarchy.conf")
    if conf.is_file():
        try:
            for line in conf.read_text(encoding="utf-8").splitlines():
                match = re.match(r"\s*(?:export\s+)?OMARCHY_PATH=(.*)\s*$", line)
                if match:
                    value = match.group(1).strip().strip("'\"")
                    if value:
                        return Path(value).expanduser().absolute()
        except OSError:
            pass
    return Path("/usr/share/omarchy")


@dataclass(frozen=True)
class Paths:
    home: Path
    xdg_config_home: Path
    state: Path
    cache: Path
    runtime: Path
    omarchy_path: Path

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Paths":
        values = dict(os.environ if env is None else env)
        home = Path(values.get("HOME", str(Path.home()))).expanduser().absolute()
        config = Path(values.get("XDG_CONFIG_HOME", str(home / ".config"))).expanduser().absolute()
        state_home = Path(values.get("XDG_STATE_HOME", str(home / ".local/state"))).expanduser().absolute()
        cache_home = Path(values.get("XDG_CACHE_HOME", str(home / ".cache"))).expanduser().absolute()
        runtime_home = Path(values.get("XDG_RUNTIME_DIR", str(state_home / "runtime"))).expanduser().absolute()
        return cls(home, config, state_home / "omarchy/customization-center",
                   cache_home / "omarchy/customization-center",
                   runtime_home / "omarchy-customization-center", _omarchy_path(values))

    def module_config(self, module_id: str) -> Path:
        return self.xdg_config_home / "omarchy/customization-center" / module_id

    def module_state(self, module_id: str) -> Path:
        return self.state / module_id

    @property
    def drafts(self) -> Path:
        return self.xdg_config_home / "omarchy/customization-center/drafts"

    @property
    def exports(self) -> Path:
        return self.xdg_config_home / "omarchy/customization-center/exports"

    @property
    def allowed_write_roots(self) -> tuple[Path, ...]:
        return (
            self.home / ".config/omarchy",
            self.home / ".config/hypr",
            self.home / ".local/state/omarchy",
            self.xdg_config_home / "omarchy/customization-center",
            self.state,
        )

    def staging_dir(self, module_id: str, plan_id: str) -> Path:
        from .atomic import mkdir_durable

        path = self.state / "staging" / module_id / plan_id
        mkdir_durable(path, 0o700)
        os.chmod(path, 0o700)
        return path

    def private_tmpfile(self, suffix: str = "") -> Path:
        from .atomic import mkdir_durable

        directory = self.runtime / "tmp"
        mkdir_durable(directory, 0o700)
        os.chmod(directory, 0o700)
        fd, name = tempfile.mkstemp(suffix=suffix, dir=directory)
        os.fchmod(fd, 0o600)
        os.close(fd)
        return Path(name)

    def read_json(self, path: str | Path, default: Any = None) -> Any:
        try:
            with Path(path).open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return default

    def readlink(self, path: str | Path, default: Any = None) -> str | Any:
        try:
            return os.readlink(path)
        except (FileNotFoundError, OSError):
            return default

    def resolve_user_path(self, value: str | Path) -> Path | None:
        if not isinstance(value, (str, Path)) or str(value).strip() == "":
            return None
        text = str(value)
        if text == "~" or text.startswith("~/"):
            text = str(self.home) + text[1:]
        path = Path(text)
        if not path.is_absolute():
            path = self.home / path
        return path.absolute()

    def expand_template(self, value: str, module_id: str = "") -> str:
        mapping = {
            "home": self.home, "xdg_config_home": self.xdg_config_home, "state": self.state,
            "module_config": self.module_config(module_id), "module_state": self.module_state(module_id),
        }
        result = value
        for name, path in mapping.items():
            result = result.replace("{" + name + "}", str(path))
        return result

    def is_allowed_write(self, path: str | Path, extra: Iterable[str | Path] = ()) -> bool:
        target = Path(path).absolute()
        roots = [root.absolute() for root in self.allowed_write_roots]
        exact = [self.home / ".config/xdg-terminals.list"]
        for item in extra:
            item_path = Path(item).absolute()
            if item_path == target:
                return self.symlink_safe(target)
            if item_path.exists() and item_path.is_dir():
                roots.append(item_path)
        allowed = target in exact or any(target == root or target.is_relative_to(root) for root in roots)
        return allowed and self.symlink_safe(target)

    def symlink_safe(self, path: str | Path) -> bool:
        target = Path(path).absolute()
        current = Path(target.anchor)
        for component in target.parts[1:]:
            current = current / component
            try:
                if stat.S_ISLNK(current.lstat().st_mode):
                    return False
            except FileNotFoundError:
                continue
        return True


def expand_template(value: str, paths: Paths, module_id: str = "") -> str:
    return paths.expand_template(value, module_id)


def no_symlink_components(path: str | Path) -> bool:
    target = Path(path).absolute()
    current = Path(target.anchor)
    for component in target.parts[1:]:
        current /= component
        try:
            if current.is_symlink():
                return False
        except OSError:
            return False
    return True
