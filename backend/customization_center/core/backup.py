from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import Any, Iterable

from .atomic import mkdir_durable, remove_file, write_bytes_atomic
from .errors import CcError


class BackupStore:
    def __init__(self, state_or_paths: str | Path | Any) -> None:
        self.state = Path(state_or_paths.state if hasattr(state_or_paths, "state") else state_or_paths)
        self.root = self.state / "backups"

    def _dir(self, txid: str) -> Path:
        return self.root / txid

    def read_manifest(self, txid: str) -> dict[str, dict[str, Any]]:
        try:
            value = json.loads((self._dir(txid) / "manifest.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        if not isinstance(value, dict):
            raise CcError("unsupported_config", "Backup manifest is not an object")
        return value

    def take(self, txid: str, paths: Iterable[str | Path]) -> dict[str, dict[str, Any]]:
        directory = self._dir(txid)
        mkdir_durable(directory, 0o700)
        manifest = self.read_manifest(txid)
        by_path = {entry.get("path"): entry for entry in manifest.values()}
        for target_value in paths:
            target = Path(target_value).absolute()
            if str(target) in by_path:
                continue
            backup_id = str(len(manifest) + 1)
            try:
                info = target.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                    raise CcError("unsupported_config", f"Cannot back up non-regular file: {target}")
                data = target.read_bytes()
                write_bytes_atomic(directory / backup_id, data, 0o600)
                entry = {"path": str(target), "sha256": hashlib.sha256(data).hexdigest(),
                         "mode": format(stat.S_IMODE(info.st_mode), "04o"), "existed": True}
            except FileNotFoundError:
                entry = {"path": str(target), "sha256": None, "mode": None, "existed": False}
            manifest[backup_id] = entry
        write_bytes_atomic(directory / "manifest.json",
                           json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n", 0o600)
        return {entry["path"]: {"backupId": key, **{k: v for k, v in entry.items() if k != "path"}}
                for key, entry in manifest.items()}

    def restore(self, txid: str, path: str | Path) -> None:
        target = str(Path(path).absolute())
        manifest = self.read_manifest(txid)
        found = next(((key, value) for key, value in manifest.items() if value.get("path") == target), None)
        if found is None:
            raise CcError("transaction_not_found", f"No backup for {target}")
        backup_id, entry = found
        output = Path(target)
        if not entry["existed"]:
            remove_file(output)
            return
        data = (self._dir(txid) / backup_id).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
            raise CcError("unsupported_config", f"Backup content hash does not match its manifest: {target}")
        mode = int(str(entry["mode"]), 8)
        write_bytes_atomic(output, data, mode)


def take(state_or_paths: str | Path | Any, txid: str, paths: Iterable[str | Path]) -> dict[str, dict[str, Any]]:
    return BackupStore(state_or_paths).take(txid, paths)
