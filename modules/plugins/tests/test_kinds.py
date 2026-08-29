def test_bar_ownership_and_deep_link_payloads(plugins_backend):
    kinds = __import__("cc_modules.plugins.kinds", fromlist=["*"])
    assert kinds.ownership(["service"]) == "plugins"
    assert kinds.ownership(["menu", "bar-widget"]) == "bar"
    assert kinds.bar_payload({"id": "acme.bar", "kinds": ["bar"], "instances": []}) == {"selectBar": "acme.bar"}
    assert kinds.bar_payload({"id": "acme.widget", "kinds": ["bar-widget"], "instances": [{"section": "right", "index": 2}]}) == {"select": {"section": "right", "index": 2}}
    assert kinds.bar_payload({"id": "acme.widget", "kinds": ["bar-widget"], "instances": []}) == {"addWidget": "acme.widget"}


def test_storage_only_reports_owned_shell_lists(plugins_backend):
    kinds = __import__("cc_modules.plugins.kinds", fromlist=["*"])
    config = {"plugins": [{"id": "acme.service", "interval": 5}], "disabledPlugins": ["omarchy.nightlight"]}
    assert kinds.storage({"id": "acme.service", "kinds": ["service"]}, config) == "plugins[]"
    assert kinds.storage({"id": "omarchy.nightlight", "kinds": ["service"]}, config) == "disabledPlugins[]"
    assert kinds.storage({"id": "omarchy.clock", "kinds": ["bar-widget"]}, config) == "bar.layout"
