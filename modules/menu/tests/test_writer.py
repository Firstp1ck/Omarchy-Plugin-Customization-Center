import json
from pathlib import Path

from modules.menu.backend.jsonc_menu import document_value, parse_with_parity
from modules.menu.backend.writer import authored_value, render


def _draft():
    return json.loads((Path(__file__).parent / "fixtures/sample-draft.json").read_text())


def test_writer_is_deterministic_and_round_trips():
    draft = _draft()
    first = render(draft)
    golden = (Path(__file__).parent / "fixtures/expected-canonical.jsonc").read_bytes()
    assert first == golden
    assert first == render(draft)
    assert first.endswith(b"\n") and not first.startswith(b"\xef\xbb\xbf")
    document, state, diagnostics = parse_with_parity(first)
    assert state == "ok" and diagnostics == []
    assert document_value(document) == authored_value(draft)


def test_writer_preserves_wrapper_sibling_and_unknown_field():
    draft = _draft()
    draft["shape"] = "wrapper"
    draft["wrapperSiblings"] = [{"key": "future", "value": {"keep": True}}]
    draft["entries"][0]["passthrough"] = {"futureField": 7}
    document, state, _ = parse_with_parity(render(draft))
    assert state == "ok"
    assert document_value(document)["future"] == {"keep": True}
    assert document_value(document)["items"]["personal"]["futureField"] == 7
