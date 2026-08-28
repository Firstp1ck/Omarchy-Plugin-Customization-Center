import pytest

from customization_center.core.toml_writer import dumps, reparse


def test_toml_fixed_schema_round_trip():
    value = {"name": "ocean", "enabled": True, "count": 2, "ratio": 1.5,
             "items": ["a", "b"], "shell": {"bar": {"position": "top"}}}
    text = dumps(value)
    assert reparse(text, value) == value
    assert "[shell.bar]" in text


def test_toml_control_escaping_quoted_keys_and_empty_string():
    value = {"key with space": "", "low": "\x01", "delete": "\x7f",
             "nested key": {"control\x01": "\b\f\n\r\t"}}
    text = dumps(value)
    assert '"key with space" = ""' in text
    assert "\\u0001" in text and "\\u007F" in text
    assert reparse(text, value) == value


def test_toml_rejects_complex_arrays():
    with pytest.raises(TypeError):
        dumps({"bad": [{"x": 1}]})
