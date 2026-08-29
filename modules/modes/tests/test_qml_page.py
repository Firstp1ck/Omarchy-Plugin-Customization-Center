from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]

def test_page_contract_and_no_direct_side_effects():
    text=(ROOT/"modules/modes/Page.qml").read_text()
    for token in ("property string moduleId", "function focusFirst()", "function handlePayload(payload)", "signal requestPlan()", "signal requestApply()", "signal requestNavigate"):
        assert token in text
    assert "Process {" not in text and "FileView {" not in text and ".applyMode(" not in text
    assert 'root.requestApply()' in text

def test_components_use_host_tokens_without_palette_literals():
    for path in (ROOT/"modules/modes/components").glob("*.qml"):
        text=path.read_text(); assert "#fff" not in text.lower() and "#000" not in text.lower()
