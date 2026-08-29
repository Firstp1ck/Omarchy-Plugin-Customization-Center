from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def test_monitors_qml_view_and_patch_contract():
    qt_runner = Path("/usr/lib/qt6/bin/qmltestrunner")
    runner = str(qt_runner) if qt_runner.is_file() else shutil.which("qmltestrunner")
    if not runner or not Path(runner).is_file(): pytest.skip("qmltestrunner is unavailable")
    env = dict(os.environ)
    imports = [ROOT / "tests/qml/imports", ROOT, Path("/usr/lib/qt6/qml")]
    env["QML2_IMPORT_PATH"] = os.pathsep.join(str(item) for item in imports)
    env["QML_IMPORT_PATH"] = env["QML2_IMPORT_PATH"]
    env["QT_QPA_PLATFORM"] = "offscreen"; env["QT_QUICK_BACKEND"] = "software"
    completed = subprocess.run([runner, "-input", str(Path(__file__).parent / "tst_monitors.qml"), "-import", str(ROOT / "tests/qml/imports"), "-import", str(ROOT)], cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    assert completed.returncode == 0, completed.stdout
