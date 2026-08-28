from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OMARCHY_SOURCE = Path("/mnt/SSD_NVME_4TB/GitHub/omarchy-fork")
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


def _require_omarchy_shell() -> Path:
    configured = os.environ.get("OMARCHY_SOURCE")
    if configured:
        source = Path(configured).expanduser()
    elif DEFAULT_OMARCHY_SOURCE.is_dir():
        source = DEFAULT_OMARCHY_SOURCE
    else:
        pytest.skip("set OMARCHY_SOURCE to an Omarchy checkout at commit 71b0887c")
    shell = source / "shell"
    if not (shell / "Commons").is_dir() or not (shell / "Ui").is_dir():
        pytest.skip("set OMARCHY_SOURCE to an Omarchy checkout at commit 71b0887c")
    return shell


def _make_lint_imports(tmp_path: Path, shell: Path) -> Path:
    qs = tmp_path / "lint-imports/qs"
    qs.mkdir(parents=True)
    (qs / "Commons").symlink_to(shell / "Commons", target_is_directory=True)
    (qs / "Ui").symlink_to(shell / "Ui", target_is_directory=True)
    return qs.parent


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
    assert not assigned, "pages must emit requestDraftPatch(patch), not assign draft: " + ", ".join(assigned)
    request_patch_signal = re.compile(r"\bsignal\s+requestDraftPatch\s*\(")
    missing_patch_signal = [
        str(path.relative_to(ROOT))
        for path in pages
        if not request_patch_signal.search(_without_comments(path.read_text(encoding="utf-8")))
    ]
    assert not missing_patch_signal, "pages must declare requestDraftPatch(var patch): " + ", ".join(missing_patch_signal)
    legacy_signal = re.compile(r"\bsignal\s+draftPatchChanged\s*\(")
    legacy_pages = [
        str(path.relative_to(ROOT))
        for path in pages
        if legacy_signal.search(_without_comments(path.read_text(encoding="utf-8")))
    ]
    assert not legacy_pages, "pages must declare requestDraftPatch, not draftPatchChanged: " + ", ".join(legacy_pages)


def test_qmllint_all_repository_qml(tmp_path: Path) -> None:
    qmllint = _require_tool("qmllint")
    omarchy_shell = _require_omarchy_shell()
    lint_imports = _make_lint_imports(tmp_path, omarchy_shell)
    failures: list[str] = []
    for path in _qml_files():
        command = [
            qmllint,
            "-I",
            str(lint_imports),
            "-I",
            str(omarchy_shell),
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


def test_qmllint_rejects_unknown_ui_property(tmp_path: Path) -> None:
    qmllint = _require_tool("qmllint")
    omarchy_shell = _require_omarchy_shell()
    lint_imports = _make_lint_imports(tmp_path, omarchy_shell)
    source = "import QtQuick\nimport qs.Ui as Ui\nUi.Button { definitelyNotAProperty: true }\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".qml", encoding="utf-8") as handle:
        handle.write(source)
        handle.flush()
        completed = subprocess.run(
            [qmllint, "--missing-property", "error", "-I", str(lint_imports), "-I", str(QT_QML_PATH), handle.name],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
    assert completed.returncode != 0
    assert "definitelyNotAProperty" in completed.stdout


@pytest.mark.skip(reason="PanelWindow, Variants, and Process require the Quickshell runtime; live shell verification is out of scope")
def test_quickshell_runtime_overlay() -> None:
    pass


def test_qmltestrunner_core_suite() -> None:
    qmltestrunner = _require_tool("qmltestrunner")
    omarchy_shell = _require_omarchy_shell()
    env = os.environ.copy()
    import_paths = [str(TEST_IMPORTS), str(omarchy_shell), str(ROOT), str(QT_QML_PATH)]
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
        str(omarchy_shell),
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
