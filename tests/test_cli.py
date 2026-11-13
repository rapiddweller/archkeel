# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.cli import main
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_dart import DART_FIXTURE_DIR
from fixtures.demo_catalog_support import apply_overlay

ROOT = Path(__file__).parents[1]
PLANNED_COMPONENT_FIXTURE = ROOT / "fixtures" / "planned-component"
_PROBE = (
    "# Archkeel\n# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.\n"
    "# SPDX-License-Identifier: MIT\n"
    '"""Getattr probe for the baseline demo."""\n\n'
    "from __future__ import annotations\n\n\n"
    "def read(box: object) -> object:\n"
    '    return getattr(box, "value")\n'
)


def _sparse_init_repository(root: Path, modules: int) -> Path:
    package = root / "src" / "sample"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    for index in range(modules):
        imports = "from sample.module_1 import VALUE\n" if index == 0 else ""
        (package / f"module_{index}.py").write_text(f"{imports}VALUE = 1\n")
    (root / "pyproject.toml").write_text('[project]\nname = "sample"\nrequires-python = ">=3.11"\n')
    for args in (
        ("init", "-q"),
        ("config", "user.email", "init@example.invalid"),
        ("config", "user.name", "Archkeel init"),
        ("add", "."),
        ("commit", "-qm", "snapshot"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


def test_json_stdout_preserves_unicode_on_a_legacy_encoded_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project-↔-🚀"
    output = io.BytesIO()
    stream = io.TextIOWrapper(output, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)
    assert main(["report", "--root", str(root), "--json"]) == 2
    stream.flush()
    result = json.loads(output.getvalue().decode("utf-8"))
    assert str(root) in result["diagnostics"][0]["subject"]


def test_check_requires_explicit_inputs(capsys: pytest.CaptureFixture) -> None:
    assert main(["check"]) == 2
    assert (
        json.loads(capsys.readouterr().out)["diagnostics"][0]["subject"] == "command-line arguments"
    )


def test_report_has_no_external_analyzer_option() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "archkeel.cli", "report", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--analyzer-root" not in result.stdout


def test_skill_install_writes_the_packaged_instructions(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert main(["skill", "install", "claude", "--root", str(tmp_path), "--json"]) == 0
    path = Path(json.loads(capsys.readouterr().out)["path"])
    assert path == tmp_path / ".claude/skills/archkeel/SKILL.md"
    assert "archkeel validate --json" in path.read_text()


@pytest.mark.parametrize(
    "command", ["init", "report", "validate", "check", "skill", "guide", "view"]
)
def test_every_command_help_explains_purpose_and_exit_codes(command: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "archkeel.cli", command, "--help"],
        capture_output=True,
        text=True,
        env={"NO_COLOR": "1", "COLUMNS": "100", "PATH": ""},
    )
    assert result.returncode == 0
    assert "Exit codes:" in result.stdout
    assert "Example" in result.stdout


def test_no_arguments_prints_the_command_overview(capsys: pytest.CaptureFixture) -> None:
    assert main([]) == 0
    overview = capsys.readouterr().out
    assert all(name in overview for name in ("report", "validate", "check", "--version"))


def test_report_missing_config_is_unknown(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["report", "--root", str(tmp_path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["observation_complete"] == "UNKNOWN"
    assert result["declared_rules"] == "UNKNOWN"
    assert result["expectation_fulfilled"] == "UNKNOWN"


def _two_code_bases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> Path:
    """#149's repository: the shop sample at the root and the Dart app in mobile/, each with
    the baseline of its own debt, a getattr probe in one and dart:io in the other."""
    repo = _prepare_repo(tmp_path, {"shop/model/probe.py": _PROBE})
    app = repo / "mobile"
    shutil.copytree(DART_FIXTURE_DIR, app)
    apply_overlay(app, next(item for item in CATALOG if item.id == "dart-forbidden-dart-io").files)
    for root in (repo, app):
        monkeypatch.chdir(root)
        assert (
            main(["validate", "--baseline", "architecture-baseline.json", "--write-baseline"]) == 0
        )
    capsys.readouterr()
    monkeypatch.chdir(repo)
    for args in (["add", "-A"], ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "mobile"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    return repo


_BASELINE_CLAIM = "The validation baseline cannot be read: "
_AMENDMENT_CLAIM = "The contract-widening amendment cannot be read: "


def _refusals(capsys: pytest.CaptureFixture) -> list[tuple[str, str, str]]:
    diagnostics = json.loads(capsys.readouterr().out)["diagnostics"]
    return [(item["code"], item["subject"], item["unknown_claim"]) for item in diagnostics]


def _prefixed(repo: Path, value: str) -> str:
    """Why a root-prefixed `value` under `--root mobile`, run from `repo`, names nothing."""
    root = repo / "mobile"
    return (
        f"{value} is relative to --root {root}: it names {root / value}, which does not exist, "
        f"not {repo / value}; pass {value.removeprefix('mobile/')}"
    )


def _planned_component_repository(tmp_path: Path) -> Path:
    return _prepare_repo(tmp_path, {}, fixture=PLANNED_COMPONENT_FIXTURE)


def test_validate_configuration_error_has_pointer(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert main(["validate", "--root", str(tmp_path), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    diagnostic = result["diagnostics"][0]
    assert diagnostic["kind"] == "contract_invalid"
    assert diagnostic["pointer"] == ""


@pytest.fixture(scope="module")
def heading_check_repository(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[str]]:
    import shlex

    from fixtures.reproduce_milestone1 import reproduce

    output = tmp_path_factory.mktemp("heading-protocol")
    reproduce(output)
    command = next(
        item["command"]
        for item in json.loads((output / "commands.json").read_text())
        if "C-host-records.json" in item["command"]
    )
    return output / "C", shlex.split(command)[1:]


@pytest.mark.parametrize("command", ["report", "check"])
@pytest.mark.parametrize(
    "metadata,heading",
    [
        ('[project]\nname = "Declared-Project"\nrequires-python = ">=3.11"\n', "Declared-Project"),
        ('[project]\nname = "<unsafe>"\n', "sample"),
        ("[project]\nname = 42\n", "sample"),
        ("[project] broken", "sample"),
        (None, "sample"),
    ],
)
def test_html_heading_uses_valid_project_name_with_namespace_fallback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    command: str,
    metadata: str | None,
    heading: str,
    heading_check_repository: tuple[Path, list[str]],
) -> None:
    root, check_args = heading_check_repository
    metadata_path = root / "pyproject.toml"
    if metadata is not None:
        metadata_path.write_text(metadata)
    else:
        metadata_path.unlink(missing_ok=True)
    output = tmp_path / "result.json"
    args = ["report", "--root", str(root)] if command == "report" else check_args
    exit_code = main([*args, "--output", str(output), "--json"])
    assert exit_code in (0, 2)
    result = json.loads(capsys.readouterr().out)
    assert result["command"] == command
    html = (tmp_path / f"result.{command}.html").read_text()
    assert f"<h1>{heading}</h1>" in html
    assert "<unsafe>" not in html


_FULL_ERROR = "--full requires --only architecture"
_RULE_ERROR = "--rule narrows violations; --only calls or architecture cannot select a rule"


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (("--full",), _FULL_ERROR),
        (("--only", "violations", "--full"), _FULL_ERROR),
        (("--only", "calls", "--rule", "R"), _RULE_ERROR),
        (("--only", "architecture", "--rule", "R"), _RULE_ERROR),
        # Several errors at once: one priority for live and saved reports.
        (("--only", "calls", "--rule", "R", "--full"), _FULL_ERROR),
    ],
)
@pytest.mark.parametrize("source", ["live", "saved"])
def test_report_option_errors_are_one_rule_set(tmp_path, capsys, source, options, message):
    # The live root has no archkeel.toml: option errors come before reading configuration.
    subject = tmp_path if source == "live" else tmp_path / "architecture.json"
    where = ("--root" if source == "live" else "--input", str(subject))
    assert main(["report", *where, *options, "--json"]) == 2
    [diagnostic] = json.loads(capsys.readouterr().out)["diagnostics"]
    assert diagnostic["unknown_claim"].endswith(message)
    assert diagnostic["subject"] == str(subject)
