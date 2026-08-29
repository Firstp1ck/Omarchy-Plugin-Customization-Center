from pathlib import Path
from types import SimpleNamespace

import pytest

from customization_center.core import CommandResult, CommandRunner, Paths

ROOT = Path(__file__).resolve().parents[3]


def test_catalog_reads_package_defaults_without_user_lua(keybindings_backend):
    catalog = __import__("cc_modules.keybindings.catalog", fromlist=["catalog"])
    entries, digest = catalog.read_default_catalog(ROOT / "tests/fixtures/omarchy")
    assert entries
    assert any(item["keys"] == "SUPER + SPACE" and item["module"] == "utilities" for item in entries)
    assert digest.startswith("sha256:")


def test_inert_lua_harness_resolves_table_dispatchers_without_user_lua(keybindings_backend, tmp_path):
    catalog = __import__("cc_modules.keybindings.catalog", fromlist=["catalog"])
    home = tmp_path / "home"; config = home / ".config"; (config / "hypr").mkdir(parents=True)
    (config / "hypr/bindings.lua").write_text('error("USER LUA SENTINEL LOADED")\n')
    base = Paths.from_env()
    paths = type(base)(home, config, tmp_path / "state", tmp_path / "cache", tmp_path / "runtime",
                       ROOT / "tests/fixtures/omarchy")
    commands = CommandRunner("read"); commands.allow_readonly(("lua",))
    if commands.which("lua") is None:
        pytest.skip("lua is required for the inert package catalog harness")
    entries, digest, error = catalog.load_default_catalog(SimpleNamespace(paths=paths, commands=commands))
    assert not error and digest.startswith("sha256:")
    terminal = next(item for item in entries if item["keys"] == "SUPER + RETURN")
    assert terminal["dispatcherKind"] == "exec"
    assert terminal["command"] == "omarchy-launch-terminal"
    assert len([item for item in entries if item["keys"] == "ALT + TAB"]) == 2
    assert {item["phase"] for item in entries if item["keys"] == "F9"} == {"press", "release"}


def test_failed_harness_returns_no_classifiable_defaults(keybindings_backend):
    catalog = __import__("cc_modules.keybindings.catalog", fromlist=["catalog"])
    classify = __import__("cc_modules.keybindings.classify", fromlist=["classify"])
    base = Paths.from_env()
    paths = type(base)(base.home, base.xdg_config_home, base.state, base.cache, base.runtime,
                       ROOT / "tests/fixtures/omarchy")
    class FailedCommands:
        def which(self, name): return "/stub/lua"
        def run(self, argv, **kwargs): return CommandResult(tuple(argv), 1, "", "harness failed", False, 1, False)
    entries, _, error = catalog.load_default_catalog(SimpleNamespace(paths=paths, commands=FailedCommands()))
    assert entries == [] and "harness failed" in error
    record = {"index":0,"domain":"keyboard","identity":"64:keysym:space","phase":"press","description":"Omarchy menu","flagSource":"header","submap":"","flags":{"unknownLetters":[]}}
    rows, _, _ = classify.classify([record], {"bindings":[],"disabled":[]}, entries)
    assert rows[0]["classification"] == "external"
