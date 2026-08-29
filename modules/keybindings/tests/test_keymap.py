from pathlib import Path


def test_compiled_keymap_parser(keybindings_backend):
    keymap = __import__("cc_modules.keybindings.keymap", fromlist=["keymap"])
    text = (Path(__file__).parent / "fixtures/keymap/us.xkb").read_text()
    assert keymap.parse_compiled_keymap(text) == {10: "1", 23: "Tab"}
    assert keymap.parse_how_to_type("keysym: Tab (0xff09)\n") == {"canonicalName": "Tab", "keysym": 0xff09}
