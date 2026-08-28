from customization_center.core.errors import CcError, is_shared_code, validate_code


def test_cc_error_shape_and_codes():
    error = CcError("invalid_draft", "bad", {"line": 2}, "/draft", "menu.1")
    assert error.to_json() == {"code": "invalid_draft", "message": "bad", "pointer": "/draft",
                               "operationId": "menu.1", "data": {"line": 2}}
    assert is_shared_code("invalid_draft")
    validate_code("menu_parser", "menu")
