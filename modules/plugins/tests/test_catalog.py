def test_remote_sanitization_removes_credentials_and_secret_markers(plugins_backend):
    catalog = __import__("cc_modules.plugins.catalog", fromlist=["*"])
    assert catalog.sanitize_remote("https://user:password@example.test/acme/plugin.git") == "https://example.test/acme/plugin.git"
    assert catalog.sanitize_remote("git@example.test:acme/plugin.git") == "example.test:acme/plugin.git"
    assert catalog.sanitize_remote("https://example.test/acme/ghp_secret.git") == "<redacted>"


def test_origin_wording_never_claims_trust(plugins_backend):
    messages = __import__("cc_modules.plugins.messages", fromlist=["*"])
    combined = " ".join(messages.CONFIRMATIONS.values()).lower()
    assert "trusted" not in combined and "verified" not in combined and "safe" not in combined
