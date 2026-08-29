from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tests.qml.test_qml import QT_QML_PATH, TEST_IMPORTS, _require_omarchy_shell, _require_tool


def test_plugins_page_with_qmltestrunner():
    runner = _require_tool("qmltestrunner")
    shell = _require_omarchy_shell()
    test_file = Path(__file__).parent / "qml/tst_page.qml"
    env = dict(os.environ)
    imports = [str(TEST_IMPORTS), str(shell), str(ROOT), str(QT_QML_PATH)]
    env["QML2_IMPORT_PATH"] = os.pathsep.join(imports)
    env["QML_IMPORT_PATH"] = env["QML2_IMPORT_PATH"]
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"
    completed = subprocess.run([runner, "-input", str(test_file), "-import", str(TEST_IMPORTS), "-import", str(ROOT)],
                               cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=60, check=False)
    assert completed.returncode == 0, completed.stdout
