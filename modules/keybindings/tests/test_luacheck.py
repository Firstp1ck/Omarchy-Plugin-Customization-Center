from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from customization_center.core import CcError, CommandResult


class Commands:
    def __init__(self, available=True, exit_code=0, stderr=""):
        self.available = available; self.exit_code = exit_code; self.stderr = stderr; self.argv = None
    def which(self, name): return "/stub/luac" if self.available and name == "luac" else None
    def run(self, argv, **kwargs):
        self.argv = argv
        return CommandResult(tuple(argv), self.exit_code, "", self.stderr, False, 1, False)


class Paths:
    def __init__(self, root): self.root = root; self.created = None
    def private_tmpfile(self, suffix):
        self.created = self.root / ("candidate" + suffix); self.created.touch(mode=0o600); return self.created


def test_luac_pass_uses_parse_only_and_cleans_temp(keybindings_backend, tmp_path):
    module = __import__("cc_modules.keybindings.luacheck", fromlist=["luacheck"])
    commands = Commands(); paths = Paths(tmp_path)
    assert module.check_candidate(SimpleNamespace(commands=commands, paths=paths), b"return true\n") == (True, "")
    assert commands.argv[:3] == ["luac", "-p", "--"]
    assert not paths.created.exists()


def test_luac_syntax_error_rewrites_path(keybindings_backend, tmp_path):
    module = __import__("cc_modules.keybindings.luacheck", fromlist=["luacheck"])
    paths = Paths(tmp_path); commands = Commands(exit_code=1, stderr=str(tmp_path / "candidate.lua") + ":4: unexpected symbol")
    with pytest.raises(CcError) as raised:
        module.check_candidate(SimpleNamespace(commands=commands, paths=paths), b"broken")
    assert raised.value.code == "keybindings_lua_syntax"
    assert "bindings.lua:4" in raised.value.message
    assert not paths.created.exists()


def test_no_luac_returns_warning_code(keybindings_backend, tmp_path):
    module = __import__("cc_modules.keybindings.luacheck", fromlist=["luacheck"])
    assert module.check_candidate(SimpleNamespace(commands=Commands(False), paths=Paths(tmp_path)), b"ok") == (True, "keybindings_no_lua_check")
