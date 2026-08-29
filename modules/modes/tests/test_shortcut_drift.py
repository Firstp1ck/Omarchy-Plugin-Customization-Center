from __future__ import annotations
import json, shlex

def test_shortcut_is_five_argv_tokens_and_review_only(modes_backend):
    shortcut=__import__("cc_modules.modes.shortcut",fromlist=["shortcut"])
    argv=shlex.split(shortcut.command("presentation")); assert argv[:4]==["omarchy-shell","shell","summon","firstpick.customization-center"]
    assert json.loads(argv[4])=={"module":"modes","modeId":"presentation","action":"review"}
