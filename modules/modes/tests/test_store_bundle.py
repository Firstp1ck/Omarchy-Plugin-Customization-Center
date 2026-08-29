from __future__ import annotations
import copy
import json
import pytest
from customization_center.core import CcError

MODE={"version":1,"id":"presentation","name":"Presentation","description":"","icon":"","members":{"themes":{"slug":"tokyo-night"},"defaults":{"browser":"firefox"}},"triggers":[]}

def test_mode_canonical_round_trip_and_rejections(modes_backend):
    store=__import__("cc_modules.modes.store",fromlist=["store"])
    issues,normalized=store.validate_mode(MODE)
    assert not issues and json.loads(store.canonical(normalized))==normalized
    cases=[({**MODE,"version":2},"modes_unsupported_version"),({**MODE,"id":"../bad"},"modes_invalid_id"),({**MODE,"members":{}},"modes_empty"),({**MODE,"members":{"menu":{"x":1}}},"modes_member_field_refused"),({**MODE,"triggers":[{}]},"modes_triggers_unsupported")]
    for value,code in cases:
        found,_=store.validate_mode(value); assert found[0].code==code

def test_bar_partial_layout_and_absolute_setting_are_rejected(modes_backend):
    store=__import__("cc_modules.modes.store",fromlist=["store"])
    partial=copy.deepcopy(MODE); partial["members"]={"bar":{"layout":{"left":[],"center":[]}}}
    assert store.validate_mode(partial)[0][0].code=="modes_section_invalid"
    unsafe=copy.deepcopy(MODE); unsafe["members"]={"bar":{"layout":{"left":[{"id":"x","path":"/tmp/x"}],"center":[],"right":[]}}}
    assert store.validate_mode(unsafe)[0][0].code=="modes_section_invalid"

def test_bundle_bounds_digests_and_commands(modes_backend):
    bundle=__import__("cc_modules.modes.bundle",fromlist=["bundle"]); store=__import__("cc_modules.modes.store",fromlist=["store"])
    mode=copy.deepcopy(MODE); mode["members"]={"keybindings":{"document":{"schemaVersion":1,"bindings":[{"chord":"SUPER + P","action":{"type":"exec","command":"obs --startrecording"}}],"disabled":[]}}}
    profile={"schemaVersion":1,"id":"desk"}
    value={"bundleVersion":1,"exportedBy":{},"exportedAt":"2026-01-01T00:00:00Z","mode":mode,"artifacts":[{"module":"monitors","kind":"monitor-profile","id":"desk","digest":store.digest(profile),"data":profile}],"externalReferences":[]}
    parsed=bundle.check(value); assert bundle.commands(parsed["mode"])[0]["command"]=="obs --startrecording"
    bad=copy.deepcopy(value); bad["artifacts"][0]["digest"]="sha256:bad"
    with pytest.raises(CcError): bundle.check(bad)
    deep={"bundleVersion":1}; cursor=deep
    for _ in range(14): cursor["x"]={}; cursor=cursor["x"]
    with pytest.raises(CcError,match="nesting"): bundle.check(deep)
    huge=copy.deepcopy(value); huge["externalReferences"]=["x"*(1024*1024)]
    with pytest.raises(CcError): bundle.check(huge)
