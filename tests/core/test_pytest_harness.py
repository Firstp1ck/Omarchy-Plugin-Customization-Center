from pathlib import Path

from customization_center.modules import MODULES


ROOT = Path(__file__).resolve().parents[2]


def test_canonical_pytest_paths_include_every_registered_module(pytestconfig):
    configured = set(pytestconfig.getini("testpaths"))
    expected = {f"modules/{module_id}/tests" for module_id in MODULES}
    assert expected.issubset(configured)
    assert all((ROOT / path).is_dir() for path in expected)
