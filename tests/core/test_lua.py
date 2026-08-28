from customization_center.core.lua import lua_string, luac_check
from customization_center.core.commands import CommandRunner


def test_lua_escaping_numeric_adjacency_and_marker_text():
    value = lua_string("\x012 -- BEGIN OMARCHY CUSTOMIZATION CENTER X v1\n\"\\é")
    assert value.startswith('"\\0012 -- BEGIN')
    assert "\\n\\\"\\\\\\195\\169" in value


def test_luac_check_argv(stub_command):
    stub_command("luac", {"stdout": "", "exit_code": 0})
    result = luac_check(CommandRunner(), "/tmp/generated.lua")
    assert result.exit_code == 0
    assert stub_command.calls("luac") == [["luac", "-p", "/tmp/generated.lua"]]
