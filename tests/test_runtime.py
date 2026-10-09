# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "runtime-fixture"
    shutil.copytree(FIXTURE, root)
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
            "remedy": "Run Archkeel with a matching Python, for example: "
            "uvx --python 3.12 archkeel <command>",
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


@pytest.mark.parametrize(
    ("metadata", "remedy"),
    [
        (None, "Add [project].requires-python to pyproject.toml"),
        ("", "Add [project].requires-python to pyproject.toml"),
        ("[project]\n", "Add [project].requires-python to pyproject.toml"),
        ("[project]\nrequires-python = 7\n", "PEP 440 range"),
        ("[project\n", "Repair pyproject.toml as valid TOML"),
        ('[project]\nrequires-python = "invalid"\n', "PEP 440 range"),
    ],
)
def test_missing_or_invalid_runtime_metadata_preserves_observation(
    tmp_path: Path, metadata: str | None, remedy: str
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
    assert remedy in result["diagnostics"][0]["remedy"]
    assert result["coverage"]["files_parsed"] == 1
    assert (root / "architecture.json").is_file()
    if metadata == '[project]\nrequires-python = "invalid"\n':
        from archkeel.ir.codec import decode_canonical_model, parse_observation

        artifact = json.loads((root / "architecture.json").read_bytes())
        assert artifact["runtime"]["requirement_state"] == "requirement_invalid"
        observation = parse_observation(decode_canonical_model(artifact))
        assert observation.runtime.requirement_state == "requirement_invalid"
        diagnostic = result["diagnostics"][0]
        assert (
            diagnostic["subject"] == "pyproject.toml Python requirement is invalid or unsupported"
        )
        assert "valid PEP 440 range" in diagnostic["remedy"]


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


@pytest.mark.parametrize(
    ("poetry", "normalized"),
    [
        ("^3.9", ">=3.9,<4.0"),
        ("^3.9.1", ">=3.9.1,<4.0"),
        ("^3", ">=3,<4.0"),
        ("^9", ">=9,<10.0"),
        (">=3.9", ">=3.9"),
        ("~=3.9", "~=3.9"),
    ],
)
def test_poetry_caret_normalization_and_pep440_passthrough(
    tmp_path: Path, poetry: str, normalized: str
) -> None:
    from archkeel.analyzer.runtime import python_requirement

    (tmp_path / "pyproject.toml").write_text(
        f'[tool.poetry.dependencies]\npython = "{poetry}"\n', encoding="utf-8"
    )
    assert python_requirement(tmp_path) == (normalized, "declared")


def test_pinned_realworld_poetry_runtime_is_read_without_rewriting_source() -> None:
    from archkeel.analyzer.runtime import python_requirement

    original = (ROOT / "fixtures/K-python-realworld/pyproject.toml").read_bytes()
    assert python_requirement(ROOT / "fixtures/K-python-realworld") == (">=3.9,<4.0", "declared")
    assert (ROOT / "fixtures/K-python-realworld/pyproject.toml").read_bytes() == original


def test_poetry_caret_runtime_range_includes_lower_and_excludes_next_major() -> None:
    from archkeel.check.runtime import runtime_diagnostic
    from archkeel.ir.facts import RuntimeInfo

    required = ">=3.9,<4.0"
    assert runtime_diagnostic(RuntimeInfo("python", "3.9.0", required)) is None
    assert runtime_diagnostic(RuntimeInfo("python", "3.8.9", required)) is not None
    assert runtime_diagnostic(RuntimeInfo("python", "4.0.0", required)) is not None


@pytest.mark.parametrize(
    ("project", "expected"),
    [
        ('requires-python = ">=3.10"', (">=3.10", "declared")),
        ("requires-python = 7", (None, "requirement_invalid")),
        ('requires-python = "not a range"', ("not a range", "declared")),
    ],
)
def test_project_requirement_has_precedence_over_poetry_fallback(
    tmp_path: Path, project: str, expected: tuple[str | None, str]
) -> None:
    from archkeel.analyzer.runtime import python_requirement

    (tmp_path / "pyproject.toml").write_text(
        f'[project]\n{project}\n\n[tool.poetry.dependencies]\npython = "^3.9"\n',
        encoding="utf-8",
    )
    assert python_requirement(tmp_path) == expected


def test_absent_project_requirement_falls_back_to_valid_poetry_pep440(tmp_path: Path) -> None:
    from archkeel.analyzer.runtime import python_requirement

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\n\n[tool.poetry.dependencies]\npython = ">=3.9"\n',
        encoding="utf-8",
    )
    assert python_requirement(tmp_path) == (">=3.9", "declared")


def test_empty_poetry_python_requirement_is_invalid(tmp_path: Path) -> None:
    from archkeel.analyzer.runtime import python_requirement

    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry.dependencies]\npython = ""\n', encoding="utf-8"
    )
    assert python_requirement(tmp_path) == (None, "requirement_invalid")


@pytest.mark.parametrize("unsupported", ["~3.9", "^0.4", "^0.0.4"])
def test_unsupported_poetry_constraints_remain_blocking(tmp_path: Path, unsupported: str) -> None:
    from archkeel.analyzer.runtime import python_requirement
    from archkeel.check.runtime import runtime_diagnostic
    from archkeel.ir.facts import RuntimeInfo

    (tmp_path / "pyproject.toml").write_text(
        f'[tool.poetry.dependencies]\npython = "{unsupported}"\n', encoding="utf-8"
    )
    required, state = python_requirement(tmp_path)
    assert required == unsupported
    assert state == "declared"
    diagnostic = runtime_diagnostic(RuntimeInfo("python", "3.11.0", required, state))
    assert diagnostic is not None
    assert "invalid or unsupported" in diagnostic.subject
    assert "supported positive-major Poetry caret" in diagnostic.remedy


def test_poetry_runtime_gate_accepts_supported_caret_and_blocks_unsupported(tmp_path: Path) -> None:
    supported = _fixture(tmp_path / "supported")
    (supported / "pyproject.toml").write_text(
        '[tool.poetry.dependencies]\npython = "^3.9"\n', encoding="utf-8"
    )
    (supported / "sample/probe.py").write_text("value = 1\n", encoding="utf-8")
    code, report = _report(11, supported)
    assert code == 0
    assert report["diagnostics"] == []
    assert report["coverage"]["files_parsed"] == 1

    invalid_project = _fixture(tmp_path / "invalid-project")
    (invalid_project / "pyproject.toml").write_text(
        '[project]\nrequires-python = "not a range"\n\n'
        '[tool.poetry.dependencies]\npython = "^3.9"\n',
        encoding="utf-8",
    )
    (invalid_project / "sample/probe.py").write_text("value = 1\n", encoding="utf-8")
    code, report = _report(11, invalid_project)
    assert code == 2
    assert report["diagnostics"][0]["kind"] == "runtime_mismatch"
    assert "invalid or unsupported" in report["diagnostics"][0]["subject"]

    unsupported = _fixture(tmp_path / "unsupported")
    (unsupported / "pyproject.toml").write_text(
        '[tool.poetry.dependencies]\npython = "~3.9"\n', encoding="utf-8"
    )
    (unsupported / "sample/probe.py").write_text("value = 1\n", encoding="utf-8")
    code, report = _report(11, unsupported)
    assert code == 2
    assert report["diagnostics"][0]["kind"] == "runtime_mismatch"
    assert "invalid or unsupported" in report["diagnostics"][0]["subject"]
    assert "supported positive-major Poetry caret" in report["diagnostics"][0]["remedy"]
    artifact = json.loads((unsupported / "architecture.json").read_bytes())
    assert artifact["runtime"]["requirement_state"] == "requirement_invalid"


@pytest.mark.parametrize("part", ["major", "minor", "patch"])
def test_extreme_poetry_caret_is_classified_by_core_without_crashing(
    tmp_path: Path, part: str
) -> None:
    from archkeel.analyzer.runtime import python_requirement

    digits = "9" * 5_000
    required = {
        "major": f"^{digits}.9",
        "minor": f"^3.{digits}",
        "patch": f"^3.9.{digits}",
    }[part]
    root = _fixture(tmp_path)
    (root / "pyproject.toml").write_text(
        f'[tool.poetry.dependencies]\npython = "{required}"\n', encoding="utf-8"
    )
    (root / "sample/probe.py").write_text("value = 1\n", encoding="utf-8")

    assert python_requirement(root) == (required, "declared")
    code, report = _report(11, root)
    assert code == 2
    assert report["diagnostics"][0]["kind"] == "runtime_mismatch"
    assert "invalid or unsupported" in report["diagnostics"][0]["subject"]
    artifact = json.loads((root / "architecture.json").read_bytes())
    assert artifact["runtime"]["requirement_state"] == "requirement_invalid"
