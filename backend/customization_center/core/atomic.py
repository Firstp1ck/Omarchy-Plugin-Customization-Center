from __future__ import annotations

import errno
import os
import shutil
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from .errors import CcError
from .paths import no_symlink_components


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def mkdir_durable(path: str | Path, mode: int = 0o700) -> Path:
    target = Path(path)
    missing: list[Path] = []
    current = target
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=mode if directory == target else 0o700)
        except FileExistsError:
            if not directory.is_dir():
                raise
        _fsync_dir(directory.parent)
    return target


def _fsync_tree(path: Path) -> None:
    directories = [path]
    for item in path.rglob("*"):
        if item.is_file():
            fd = os.open(item, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        elif item.is_dir():
            directories.append(item)
    for directory in reversed(directories):
        _fsync_dir(directory)


def write_bytes_atomic(path: str | Path, data: bytes, mode: int | None = None) -> None:
    target = Path(path)
    if not no_symlink_components(target):
        raise CcError("unsupported_config", f"Refusing symlinked path: {target}")
    mkdir_durable(target.parent)
    existing_mode = None
    try:
        existing_mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        pass
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temp = Path(temp_name)
    try:
        os.fchmod(fd, mode if mode is not None else (existing_mode if existing_mode is not None else 0o600))
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
        _fsync_dir(target.parent)
    except BaseException:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise


@dataclass(frozen=True)
class DirectoryReplacement:
    path: Path
    previous: Path | None
    installed: bool

    def undo(self) -> None:
        if self.path.exists():
            shutil.rmtree(self.path)
        if self.previous and self.previous.exists():
            os.replace(self.previous, self.path)
        _fsync_dir(self.path.parent)


def _check_directory(path: Path) -> None:
    if ".git" in path.parts:
        raise CcError("unsupported_config", f"Refusing Git path: {path}")
    if path.is_symlink() or not no_symlink_components(path):
        raise CcError("unsupported_config", f"Refusing symlinked directory: {path}")
    if path.exists():
        for item in path.rglob("*"):
            if item.is_symlink():
                raise CcError("unsupported_config", f"Refusing directory containing a symlink: {path}")
            if item.name == ".git":
                raise CcError("unsupported_config", f"Refusing Git directory: {path}")


def replace_directory_atomic(path: str | Path, staged_dir: str | Path | None,
                             allow_existing: bool = False) -> DirectoryReplacement:
    target = Path(path)
    _check_directory(target)
    if target.exists() and not target.is_dir():
        raise CcError("unsupported_config", f"Target is not a directory: {target}")
    if target.exists() and not allow_existing:
        raise CcError("unsupported_config", f"Directory already exists: {target}")
    mkdir_durable(target.parent)
    incoming: Path | None = None
    if staged_dir is not None:
        source = Path(staged_dir)
        _check_directory(source)
        if not source.is_dir():
            raise CcError("unsupported_config", f"Staged directory does not exist: {source}")
        incoming = source
        try:
            same_fs = source.stat().st_dev == target.parent.stat().st_dev
        except OSError:
            same_fs = False
        if not same_fs:
            incoming = target.parent / f".{target.name}.incoming-{uuid.uuid4().hex}"
            shutil.copytree(source, incoming, symlinks=False)
            _fsync_tree(incoming)
            _fsync_dir(target.parent)
    previous = target.parent / f".{target.name}.previous-{uuid.uuid4().hex}" if target.exists() else None
    try:
        if previous:
            os.rename(target, previous)
            _fsync_dir(target.parent)
        if incoming:
            try:
                os.rename(incoming, target)
            except OSError as error:
                if error.errno != errno.EXDEV:
                    raise
                copied = target.parent / f".{target.name}.incoming-{uuid.uuid4().hex}"
                shutil.copytree(incoming, copied, symlinks=False)
                _fsync_tree(copied)
                os.rename(copied, target)
            _fsync_dir(target.parent)
        return DirectoryReplacement(target, previous, incoming is not None)
    except BaseException:
        if previous and previous.exists() and not target.exists():
            os.rename(previous, target)
        raise


def remove_file(path: str | Path) -> bool:
    target = Path(path)
    if not no_symlink_components(target):
        raise CcError("unsupported_config", f"Refusing symlinked path: {target}")
    try:
        mode = target.lstat().st_mode
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise CcError("unsupported_config", f"Refusing to remove non-regular file: {target}")
    target.unlink()
    _fsync_dir(target.parent)
    return True
