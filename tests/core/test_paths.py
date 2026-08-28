import os
from pathlib import Path

from customization_center.core import Paths


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
