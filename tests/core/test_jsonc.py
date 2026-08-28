import pytest

from customization_center.core import CcError
from customization_center.core.jsonc import dumps_canonical, parse


def test_comments_trailing_commas_duplicates_and_line_map():
    value, diagnostics = parse(b'''{
// comment
"a": 1,
/* block */
"nested": {"x": 1, "x": 2,},
"a": 3,
}''')
    assert value == {"a": 3, "nested": {"x": 2}}
    assert {item.path for item in diagnostics.duplicates} == {"/a", "/nested/x"}
    assert diagnostics.line_map["/a"] == 3


def test_canonical_output_and_string_comma_safety():
    value, _ = parse(b'{"command":"printf ,}",}')
    assert value["command"] == "printf ,}"
    assert dumps_canonical({"b": 1, "a": 2}) == '{\n  "a": 2,\n  "b": 1\n}\n'


def test_nested_repeated_key_line_map_uses_json_paths():
    _, diagnostics = parse(b'''{
  "x": 0,
  "nested": {
    "x": 1,
    "x": 2
  }
}''')
    assert diagnostics.line_map["/x"] == 2
    assert diagnostics.line_map["/nested/x"] == 4
    duplicate = next(item for item in diagnostics.duplicates if item.path == "/nested/x")
    assert duplicate.line == 5


def test_invalid_jsonc_raises():
    with pytest.raises(CcError) as caught:
        parse(b"{ broken }")
    assert caught.value.code == "invalid_draft"
