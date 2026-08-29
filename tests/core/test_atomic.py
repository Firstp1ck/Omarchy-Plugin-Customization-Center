import errno
from pathlib import Path

import pytest

from customization_center.core import CcError, remove_file, replace_directory_atomic, write_bytes_atomic


def test_atomic_write_preserves_or_sets_mode(isolated_home):
    path = isolated_home / "file"
    write_bytes_atomic(path, b"one", 0o640)
    write_bytes_atomic(path, b"two", None)
    assert path.read_bytes() == b"two"
    assert path.stat().st_mode & 0o777 == 0o640
    assert not list(path.parent.glob(".file.*"))


def test_directory_swap_and_undo(isolated_home):
    target = isolated_home / "theme"
    target.mkdir(); (target / "old").write_text("old")
    staged = isolated_home / "staged"
    staged.mkdir(); (staged / "new").write_text("new")
    action = replace_directory_atomic(target, staged, True)
    assert (target / "new").is_file()
    action.undo()
    assert (target / "old").read_text() == "old"


def test_refuses_git_symlink_and_remove_non_file(isolated_home):
    directory = isolated_home / "git"
    directory.mkdir(); (directory / ".git").mkdir()
    staged = isolated_home / "next"; staged.mkdir()
    with pytest.raises(CcError): replace_directory_atomic(directory, staged, True)
    link = isolated_home / "link"; link.symlink_to(isolated_home / "missing")
    with pytest.raises(CcError): remove_file(link)


def test_refuses_directory_with_fifo(isolated_home):
    if not hasattr(__import__("os"), "mkfifo"):
        pytest.skip("os.mkfifo is unavailable")
    import os
    staged = isolated_home / "staged-special"; staged.mkdir()
    os.mkfifo(staged / "fifo")
    with pytest.raises(CcError, match="special entry"):
        replace_directory_atomic(isolated_home / "target-special", staged, False)


def test_refuses_git_path_components_for_target_and_staged(isolated_home):
    staged = isolated_home / "ordinary"; staged.mkdir()
    with pytest.raises(CcError):
        replace_directory_atomic(isolated_home / ".git", staged, False)
    git_staged = isolated_home / "staging/.git"; git_staged.mkdir(parents=True)
    with pytest.raises(CcError):
        replace_directory_atomic(isolated_home / "target", git_staged, False)


def test_directory_swap_cross_filesystem_falls_back_to_sibling_copy(isolated_home, monkeypatch):
    import customization_center.core.atomic as atomic

    target = isolated_home / "target"
    staged = isolated_home / "staged-cross"
    staged.mkdir(); (staged / "file").write_text("content")
    real_rename = atomic.os.rename
    attempts = 0

    def rename(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError(errno.EXDEV, "cross-device link")
        return real_rename(source, destination)

    monkeypatch.setattr(atomic.os, "rename", rename)
    action = replace_directory_atomic(target, staged, False)
    assert (target / "file").read_text() == "content"
    assert staged.is_dir()
    assert action.installed and attempts == 2
