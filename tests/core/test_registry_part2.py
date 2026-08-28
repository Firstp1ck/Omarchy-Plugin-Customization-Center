from pathlib import Path

from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry


def test_registry_loads_hello_override(isolated_home):
    repo = Path(__file__).resolve().parents[2]
    registry = load_registry(repo, [repo / "tests/fixtures/modules/hello"], Paths.from_env())
    assert registry.module("hello").id == "hello"
    assert registry.warnings == ()
