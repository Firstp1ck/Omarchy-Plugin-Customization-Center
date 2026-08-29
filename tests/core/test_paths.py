import os
from pathlib import Path

import pytest

from customization_center.core import CcError, Paths


def test_paths_resolve_and_enforce_allowlist(isolated_home):
    paths = Paths.from_env()
    assert paths.omarchy_path == Path(os.environ["OMARCHY_PATH"])
    assert paths.module_config("menu").is_relative_to(Path(os.environ["XDG_CONFIG_HOME"]))
    assert paths.expand_template("{module_state}/x", "menu").endswith("/menu/x")
    assert paths.is_allowed_write(paths.xdg_config_home / "omarchy/shell.json")
    assert paths.is_allowed_write(paths.xdg_config_home / "xdg-terminals.list")
    assert not paths.is_allowed_write(isolated_home / "outside")


def test_native_and_customization_roots_when_home_differs_from_xdg(isolated_home):
    home = isolated_home / "native-home"
    xdg = isolated_home / "xdg-config"
    paths = Paths.from_env({"HOME": str(home), "XDG_CONFIG_HOME": str(xdg),
                            "XDG_STATE_HOME": str(isolated_home / "xdg-state"),
                            "XDG_CACHE_HOME": str(isolated_home / "xdg-cache"),
                            "XDG_RUNTIME_DIR": str(isolated_home / "runtime"),
                            "OMARCHY_PATH": str(isolated_home / "omarchy")})
    assert paths.is_allowed_write(home / ".config/hypr/monitors.lua")
    assert paths.is_allowed_write(paths.module_config("menu") / "x.json")
    assert not paths.is_allowed_write(xdg / "hypr/x.lua")
    assert paths.is_allowed_write(home / ".config/xdg-terminals.list")


def test_symlink_component_and_private_files(isolated_home):
    paths = Paths.from_env()
    real = paths.xdg_config_home / "real"
    real.mkdir()
    link = paths.xdg_config_home / "omarchy-link"
    link.symlink_to(real, target_is_directory=True)
    assert not paths.symlink_safe(link / "file")
    temp = paths.private_tmpfile(".lua")
    assert temp.parent.name == "tmp" and temp.stat().st_mode & 0o777 == 0o600
    staging = paths.staging_dir("menu", "p1")
    assert staging.stat().st_mode & 0o777 == 0o700


def test_read_regular_is_bounded_and_rejects_symlinks_and_non_regular_files(isolated_home):
    paths = Paths.from_env()
    regular = isolated_home / "asset.bin"
    regular.write_bytes(b"asset-bytes")
    assert paths.read_regular(regular, 11) == b"asset-bytes"
    with pytest.raises(CcError, match="exceeds"):
        paths.read_regular(regular, 10)
    link = isolated_home / "asset-link.bin"
    link.symlink_to(regular)
    with pytest.raises(CcError, match="safe regular"):
        paths.read_regular(link, 100)
    with pytest.raises(CcError, match="safe regular"):
        paths.read_regular(isolated_home, 100)
    with pytest.raises(ValueError):
        paths.read_regular(regular, -1)


def test_cache_json_write_is_atomic_bounded_and_cache_root_only(isolated_home):
    paths = Paths.from_env()
    target = paths.write_cache_json("monitor-inventory.json", {"observedAt": "now", "outputs": []})
    assert target == paths.cache / "monitor-inventory.json"
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.read_text() == '{"observedAt":"now","outputs":[]}\n'
    for unsafe in ("../state.json", "/tmp/cache.json", "."):
        with pytest.raises(CcError, match="Cache path"):
            paths.write_cache_json(unsafe, {})
    outside = isolated_home / "outside"
    outside.mkdir()
    linked = paths.cache / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    with pytest.raises(CcError, match="outside the cache root"):
        paths.write_cache_json("linked/value.json", {})
    with pytest.raises(CcError, match="1 MiB"):
        paths.write_cache_json("large.json", {"value": "x" * (1024 * 1024)})


def test_read_regular_detects_inode_change_between_lstat_and_open(isolated_home, monkeypatch):
    paths = Paths.from_env()
    target = isolated_home / "raced.bin"
    replacement = isolated_home / "replacement.bin"
    target.write_bytes(b"before")
    replacement.write_bytes(b"after")
    original_open = os.open

    def swapped_open(path, flags, *args, **kwargs):
        Path(path).unlink()
        replacement.rename(path)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swapped_open)
    with pytest.raises(CcError, match="changed while opening"):
        paths.read_regular(target, 100)
