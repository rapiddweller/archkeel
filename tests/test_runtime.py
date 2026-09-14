# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures/E-runtime"
PRODUCER = Path(os.environ.get("CODEKEEL_PRODUCER_ROOT", str(ROOT.parent / "datamimic-ee")))


def _interpreter(minor: int) -> str:
    executable = (
        sys.executable if sys.version_info[:2] == (3, minor) else shutil.which(f"python3.{minor}")
    )
    assert executable, f"Python 3.{minor} is required for the runtime fixture"
    return executable


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "runtime-fixture"
    shutil.copytree(FIXTURE, root)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "Codekeel fixture")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "runtime fixture")
    return root


def _report(minor: int, root: Path) -> tuple[int, dict[str, object]]:
    run = subprocess.run(
        [
            _interpreter(minor),
            "-m",
            "codekeel.cli",
            "report",
            "--root",
            str(root),
            "--producer-root",
            str(PRODUCER),
            "--output",
            str(root / "architecture.json"),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.stdout, run.stderr
    return run.returncode, json.loads(run.stdout)


@pytest.mark.parametrize("minor", [11, 12])
def test_pep695_fixture_reports_actual_runtime(tmp_path: Path, minor: int) -> None:
    root = _fixture(tmp_path)
    code, result = _report(minor, root)
    version = subprocess.check_output(
        [_interpreter(minor), "-c", "import platform; print(platform.python_version())"], text=True
    ).strip()
    observation = json.loads((root / "architecture.json").read_bytes())
    assert result["python_version"] == observation["python_version"] == version
    if minor == 11:
        assert code == 2
        diagnostic = result["diagnostics"][0]
        assert diagnostic == {
            "kind": "runtime_mismatch",
            "subject": f"python {version} < requires-python >=3.12",
            "unknown_claim": "AST may differ from target runtime; parse errors may be "
            "parser limitations, not source defects",
            "remedy": "Run the producer with a Python matching the target's requires-python.",
        }
        assert observation["coverage"]["files_parsed"] == 0
    else:
        assert code == 0
        assert result["diagnostics"] == []
        assert (
            observation["coverage"]["files_parsed"]
            == observation["coverage"]["files_discovered"]
            == 1
        )


def test_invalid_python_is_parse_error_when_runtime_is_allowed(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "sample/probe.py").write_text("def broken(:\n    pass\n")
    code, result = _report(11, root)
    assert code == 2
    assert result["diagnostics"][0]["kind"] == "parse_error"
    assert "declared target runtime" in result["diagnostics"][0]["remedy"]


@pytest.mark.parametrize("metadata", [None, "", '[project]\nrequires-python = "invalid"\n'])
def test_missing_or_invalid_runtime_metadata_preserves_observation(
    tmp_path: Path, metadata: str | None
) -> None:
    root = _fixture(tmp_path)
    if metadata is None:
        (root / "pyproject.toml").unlink()
    else:
        (root / "pyproject.toml").write_text(metadata)
    (root / "sample/probe.py").write_text("value = 1\n")
    code, result = _report(11, root)
    assert code == 2
    assert result["diagnostics"][0]["kind"] == "runtime_mismatch"
    assert result["coverage"]["files_parsed"] == 1
    assert (root / "architecture.json").is_file()
