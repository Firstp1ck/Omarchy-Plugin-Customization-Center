from __future__ import annotations

MODEL_VERSIONS = {
    "e75faf23e1c4bdd341689c49f236cdbfa7144267bd9aa65186e339a9240137d1": {
        "overrideSemantics": "full-shadow",
        "providers": ["apps", "fonts", "power-profiles"],
        "guardReaders": ["omarchy-channel-current", "omarchy-default-agent", "omarchy-default-browser",
                         "omarchy-default-editor", "omarchy-default-terminal", "omarchy-dns"],
    }
}


def describe(model_hash: str) -> dict:
    found = MODEL_VERSIONS.get(model_hash)
    if found:
        return {**found, "modelRecognized": True}
    return {"overrideSemantics": "full-shadow", "providers": ["apps", "fonts", "power-profiles"],
            "guardReaders": ["omarchy-channel-current", "omarchy-default-agent", "omarchy-default-browser",
                             "omarchy-default-editor", "omarchy-default-terminal", "omarchy-dns"],
            "modelRecognized": False}
