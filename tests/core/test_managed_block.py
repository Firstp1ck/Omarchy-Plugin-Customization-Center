import pytest

from customization_center.core import CcError
from customization_center.core.managed_block import extract, inspect, markers, replace


def test_insert_replace_extract_remove():
    original = b"print('user')\n"
    inserted = replace(original, "bindings", 1, "hl.bind('x')", "--")
    assert b"\n\n-- BEGIN" in inserted
    assert inspect(inserted, "bindings", 1)["state"] == "present"
    assert extract(inserted, "bindings", 1) == "hl.bind('x')"
    changed = replace(inserted, "bindings", 1, "new", "--")
    assert extract(changed, "bindings", 1) == "new"
    assert replace(changed, "bindings", 1, None, "--") == original


@pytest.mark.parametrize(("data", "state"), [
    (b"-- BEGIN OMARCHY CUSTOMIZATION CENTER X v1\n", "unterminated"),
    (b"-- END OMARCHY CUSTOMIZATION CENTER X v1\n-- BEGIN OMARCHY CUSTOMIZATION CENTER X v1\n", "reversed"),
    (b"-- BEGIN OMARCHY CUSTOMIZATION CENTER X v1\n-- BEGIN OMARCHY CUSTOMIZATION CENTER X v1\n-- END OMARCHY CUSTOMIZATION CENTER X v1\n", "duplicate"),
    (b"-- BEGIN OMARCHY CUSTOMIZATION CENTER X v1\n// BEGIN OMARCHY CUSTOMIZATION CENTER Y v1\n// END OMARCHY CUSTOMIZATION CENTER Y v1\n-- END OMARCHY CUSTOMIZATION CENTER X v1\n", "nested"),
])
def test_collision_shapes(data, state):
    assert inspect(data, "x", 1)["state"] == state
    with pytest.raises(CcError): replace(data, "x", 1, "body", "--")


def test_jsonc_markers():
    assert markers("menu", 2, "//")[0] == "// BEGIN OMARCHY CUSTOMIZATION CENTER MENU v2"
