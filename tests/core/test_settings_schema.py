import json
from pathlib import Path

from customization_center.core.settings_schema import adapter, fingerprint, normalize, validate


def test_aliases_options_defaults_and_validation():
    manifest = {"barWidget": {"defaults": {"count": 3}, "schema": [
        {"key": "count", "type": "integer", "label": "Count", "minimum": "1", "maximum": 5, "step": 1},
        {"key": "mode", "type": "enum", "options": ["a", {"value": "b", "label": "Bee"}], "default": "a"},
    ]}}
    schema = normalize(manifest)
    assert schema["support"] == "schema"
    assert schema["fields"][0]["defaultSource"] == "barWidget.defaults"
    assert {problem["code"] for problem in schema["problems"]} == {"plugins_field_alias_used"}
    result = validate({"count": 5, "mode": "b"}, schema)
    assert result.ok and result.normalized_draft == {"count": 5, "mode": "b"}
    assert fingerprint(schema).startswith("sha256:")


def test_customization_center_extension_fixture_is_normalized_read_only():
    fixture = Path("tests/fixtures/settings/extension-block.json")
    settings = normalize(json.loads(fixture.read_text()))
    extension = settings["extension"]
    assert settings["support"] == "none"
    assert extension["version"] == 1 and extension["scope"] == "shell-entry"
    assert extension["support"] == "schema" and extension["readOnly"] is True
    assert extension["fields"] == [{"key": "interval", "type": "integer", "label": "Refresh interval",
                                     "defaultValue": 60, "defaultSource": "field", "min": 5, "max": 3600}]
    assert extension["fingerprint"].startswith("sha256:")
    assert {item["code"] for item in extension["problems"]} == {"plugins_field_alias_used"}
    assert all(item["path"].startswith("/customizationCenter/schema") for item in extension["problems"])


def test_invalid_partial_schema_and_adapters():
    assert normalize({"barWidget": {"schema": {}}})["support"] == "invalid"
    spacer = normalize({"barWidget": {"settingsForm": "spacerSettings"}})
    assert spacer["adapterId"] == "spacerSettings@1" and spacer["fields"][0]["defaultValue"] == 12
    weather = adapter("weatherSettings")
    assert [option["value"] for option in weather["fields"][0]["options"]] == ["", "metric", "imperial"]
    assert weather["external"]["ownership"] == "external"
