# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures/E-runtime"


def _interpreter(minor: int) -> str:
    if sys.version_info[:2] == (3, minor):
        return sys.executable
    return subprocess.check_output(["uv", "python", "find", f"3.{minor}"], text=True).strip()


def _runtime_command(minor: int) -> list[str]:
    executable = _interpreter(minor)
    if executable == sys.executable:
        return [executable]
    return [
        "uv",
        "run",
        "--isolated",
        "--project",
        str(ROOT),
        "--locked",
        "--python",
        executable,
        "python",
    ]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _fixture(tmp_path: Path, fixture: Path = FIXTURE) -> Path:
    root = tmp_path / "runtime-fixture"
    shutil.copytree(fixture, root)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "Archkeel fixture")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "runtime fixture")
    return root


def _report(minor: int, root: Path) -> tuple[int, dict[str, object]]:
    run = subprocess.run(
        [
            *_runtime_command(minor),
            "-m",
            "archkeel.cli",
            "report",
            "--root",
            str(root),
            "--output",
            str(root / "architecture.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.stdout, run.stderr
    return run.returncode, json.loads(run.stdout)


def test_legacy_invalid_python_requirement_names_metadata_subject() -> None:
    from archkeel.check.runtime import runtime_diagnostic
    from archkeel.ir.facts import RuntimeInfo

    diagnostic = runtime_diagnostic(RuntimeInfo("python", "3.11.12", "invalid"))
    assert diagnostic is not None
    assert diagnostic.subject == "pyproject.toml Python requirement is invalid or unsupported"
    assert "valid PEP 440 range" in diagnostic.remedy


def test_invalid_python_runtime_version_does_not_blame_requirement() -> None:
    from archkeel.check.runtime import runtime_diagnostic
    from archkeel.ir.facts import RuntimeInfo

    diagnostic = runtime_diagnostic(RuntimeInfo("python", "broken", ">=3.11"))
    assert diagnostic is not None
    assert "pyproject.toml [project].requires-python" not in diagnostic.subject
    assert "valid runtime version" in diagnostic.remedy


def test_poetry_caret_runtime_range_includes_lower_and_excludes_next_major() -> None:
    from archkeel.check.runtime import runtime_diagnostic
    from archkeel.ir.facts import RuntimeInfo

    required = ">=3.9,<4.0"
    assert runtime_diagnostic(RuntimeInfo("python", "3.9.0", required)) is None
    assert runtime_diagnostic(RuntimeInfo("python", "3.8.9", required)) is not None
    assert runtime_diagnostic(RuntimeInfo("python", "4.0.0", required)) is not None


def test_python_mismatch_recommends_a_version_matching_the_full_range() -> None:
    from archkeel.check.runtime import runtime_diagnostic
    from archkeel.ir.facts import RuntimeInfo

    diagnostic = runtime_diagnostic(RuntimeInfo("python", "3.12.5", ">3.12.5,<3.13"))

    assert diagnostic is not None
    assert diagnostic.subject == "python 3.12.5 does not satisfy requires-python >3.12.5,<3.13"
    assert "satisfies the full project range" in diagnostic.remedy
    assert "uvx --python <compatible-version> archkeel <command>" in diagnostic.remedy
    assert "--python 3.12 " not in diagnostic.remedy
