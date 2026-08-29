def test_external_row_remains_read_only(keybindings_backend):
    classify = __import__("cc_modules.keybindings.classify", fromlist=["classify"])
    record = {"index":0,"domain":"keyboard","identity":"64:keysym:x","phase":"press","description":"Dynamic","flagSource":"header","submap":"","flags":{"unknownLetters":[]}}
    rows, disabled, orphaned = classify.classify([record], {"bindings":[],"disabled":[]}, [])
    assert rows[0]["classification"] == "external"
    assert rows[0]["readOnlyReason"] == "unknown_exact_source"
    assert not disabled and not orphaned


def test_alt_tab_stack_and_f9_phases_classify_independently(keybindings_backend):
    classify = __import__("cc_modules.keybindings.classify", fromlist=["classify"])
    records = [
        {"index":0,"domain":"keyboard","identity":"8:keysym:tab","phase":"press","description":"Focus on next window","flagSource":"json","submap":"","flags":{"unknownLetters":[]}},
        {"index":1,"domain":"keyboard","identity":"8:keysym:tab","phase":"press","description":"Reveal active window on top","flagSource":"json","submap":"","flags":{"unknownLetters":[]}},
        {"index":2,"domain":"keyboard","identity":"0:keysym:f9","phase":"press","description":"Start dictation (push-to-talk)","flagSource":"json","submap":"","flags":{"unknownLetters":[]}},
        {"index":3,"domain":"keyboard","identity":"0:keysym:f9","phase":"release","description":"Stop dictation (push-to-talk)","flagSource":"json","submap":"","flags":{"unknownLetters":[]}}
    ]
    catalog = [
        {"identity":row["identity"],"phase":row["phase"],"description":row["description"],"module":"tiling","sourceFile":"x.lua","sourceLine":row["index"]+1,"keys":"ALT + TAB" if row["index"]<2 else "F9","dispatcherKind":"native","command":None}
        for row in records
    ]
    rows, _, _ = classify.classify(records, {"bindings":[],"disabled":[]}, catalog)
    assert all(row["classification"] == "omarchy_default" for row in rows)
    assert rows[0]["stackSize"] == rows[1]["stackSize"] == 2
    assert rows[2]["stackSize"] == rows[3]["stackSize"] == 1
