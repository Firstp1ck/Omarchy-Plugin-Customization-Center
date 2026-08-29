import pytest


def test_normalization_and_aliases(keybindings_backend):
    chords = __import__("cc_modules.keybindings.chords", fromlist=["chords"])
    value = chords.normalize("win + control + comma")
    assert value["sourceKeys"] == "SUPER + CTRL + comma"
    assert value["display"] == "SUPER + CTRL + ,"
    assert chords.normalize("TAB")["identity"] == chords.normalize("Tab")["identity"]


@pytest.mark.parametrize("value,code", [("SUPER + + A", "keybindings_chord_grammar"), ("CAPS + A", "keybindings_unsupported_modifier"), ("mouse:272", "keybindings_unsupported_key"), ("code:7", "keybindings_chord_grammar")])
def test_rejected_chords(keybindings_backend, value, code):
    chords = __import__("cc_modules.keybindings.chords", fromlist=["chords"])
    with pytest.raises(chords.ChordError) as raised:
        chords.normalize(value)
    assert raised.value.code == code
