from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry
from tests.qml.test_qml import QT_QML_PATH, _require_omarchy_shell, _require_tool

ROOT = Path(__file__).resolve().parents[2]


def _pages():
    registry = load_registry(ROOT, [ROOT / "tests/fixtures/modules/hello"], Paths.from_env())
    return [(entry.id, entry.directory / entry.metadata["page"]) for entry in registry.view]


@pytest.mark.parametrize("module_id,page", _pages(), ids=lambda value: str(value))
def test_module_page_contract_with_qmltestrunner(module_id: str, page: Path, tmp_path: Path):
    runner = _require_tool("qmltestrunner")
    shell = _require_omarchy_shell()
    module_dir = page.parent.as_uri().replace('"', '\\"')
    test = tmp_path / "tst_page.qml"
    test.write_text(f'''import QtQuick\nimport QtTest\nimport "{module_dir}" as Module\nTestCase {{
 name: "PageContract"
 Component {{ id: component; Module.Page {{}} }}
 function test_contract() {{
  var page = createTemporaryObject(component, this)
  verify(page !== null)
  compare(typeof page.focusFirst, "function")
  compare(typeof page.handlePayload, "function")
  compare(page.moduleId, "{module_id}")
 }}
}}\n''')
    env = dict(os.environ)
    env["QML2_IMPORT_PATH"] = os.pathsep.join([str(shell), str(QT_QML_PATH)])
    completed = subprocess.run([runner, "-input", str(test)], env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
    assert completed.returncode == 0, completed.stdout
