from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
OMARCHY_SHELL = Path("/mnt/SSD_NVME_4TB/GitHub/omarchy-fork/shell")
QT_QML_PATH = Path("/usr/lib/qt6/qml")
TEST_IMPORTS = ROOT / "tests/qml/imports"


def _require_tool(name: str) -> str:
    qt6_binary = Path("/usr/lib/qt6/bin") / name
    if qt6_binary.is_file() and os.access(qt6_binary, os.X_OK):
        return str(qt6_binary)
    binary = shutil.which(name)
    if binary is None:
        pytest.skip(f"{name} is not installed; QML validation cannot run")
    return binary


def _require_fork() -> None:
    if not OMARCHY_SHELL.is_dir():
        pytest.skip(f"Omarchy fork QML import path is absent: {OMARCHY_SHELL}")


def _qml_files() -> list[Path]:
    return sorted(path for path in ROOT.rglob("*.qml") if ".git" not in path.parts)


def _without_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def test_qml_static_boundaries() -> None:
    files = _qml_files()
    backend_client = ROOT / "core/BackendClient.qml"
    process_pattern = re.compile(r"\b(?:Process|FileView)\s*\{")
    violations: list[str] = []
    for path in files:
        if path == backend_client:
            continue
        if process_pattern.search(_without_comments(path.read_text(encoding="utf-8"))):
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, "Process/FileView is restricted to core/BackendClient.qml: " + ", ".join(violations)

    pages = sorted((ROOT / "modules").glob("*/Page.qml")) if (ROOT / "modules").exists() else []
    fixture_page = ROOT / "tests/fixtures/modules/hello/Page.qml"
    assert fixture_page.is_file(), "the hello page contract fixture is required"
    pages.append(fixture_page)
    direct_draft_assignment = re.compile(r"(?<![\w.])draft\s*(?:\.[A-Za-z_$][\w$]*|\[[^\]]+\])?\s*=")
    assigned = [
        str(path.relative_to(ROOT))
        for path in pages
        if direct_draft_assignment.search(_without_comments(path.read_text(encoding="utf-8")))
    ]
    assert not assigned, "pages must emit draftChanged(patch), not assign draft: " + ", ".join(assigned)


def test_qmllint_all_repository_qml() -> None:
    qmllint = _require_tool("qmllint")
    _require_fork()
    failures: list[str] = []
    for path in _qml_files():
        command = [
            qmllint,
            "-I",
            str(OMARCHY_SHELL),
            "-I",
            str(ROOT),
            "-I",
            str(QT_QML_PATH),
            str(path),
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            failures.append(f"{path.relative_to(ROOT)} (exit {completed.returncode})\n{completed.stdout}")
    assert not failures, "qmllint failed:\n\n" + "\n\n".join(failures)


@pytest.mark.skip(reason="PanelWindow, Variants, and Process require the Quickshell runtime; live shell verification is out of scope")
def test_quickshell_runtime_overlay() -> None:
    pass


def test_qmltestrunner_core_suite() -> None:
    qmltestrunner = _require_tool("qmltestrunner")
    _require_fork()
    env = os.environ.copy()
    import_paths = [str(TEST_IMPORTS), str(OMARCHY_SHELL), str(ROOT), str(QT_QML_PATH)]
    existing = env.get("QML2_IMPORT_PATH", "")
    env["QML2_IMPORT_PATH"] = os.pathsep.join(import_paths + ([existing] if existing else []))
    env["QML_IMPORT_PATH"] = env["QML2_IMPORT_PATH"]
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"
    command = [
        qmltestrunner,
        "-input",
        str(Path("tests/qml/tst_core.qml")),
        "-import",
        str(OMARCHY_SHELL),
        "-import",
        str(TEST_IMPORTS),
        "-import",
        str(ROOT),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, f"qmltestrunner exited {completed.returncode}:\n{completed.stdout}"
