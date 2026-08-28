import json

import pytest

from customization_center.core import CcError, Result, Warning, emit, is_shared_code, validate_code


def test_emit_is_exactly_one_json_line():
    text = emit(Result(False, "status", "menu", errors=(CcError("invalid_draft", "bad"),)))
    assert text.count("\n") == 1 and text.endswith("\n")
    value = json.loads(text)
    assert value["schemaVersion"] == 1 and not value["ok"]


def test_error_code_validation():
    assert is_shared_code("timeout")
    validate_code("menu_bad_guard", "menu")
    with pytest.raises(ValueError):
        emit(Result(True, "status", "menu", warnings=(Warning("typo", "bad"),)))
    with pytest.raises(ValueError):
        validate_code("bar_problem", "menu")
