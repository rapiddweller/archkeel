# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Unsupported projects have no partial result and never start a collector."""

import json
import subprocess
from pathlib import Path

import pytest

from archkeel.analyzer.process import ProcessCollector
from archkeel.cli import main
from archkeel.cli.config import parse_config
from archkeel.cli.observe import observer_for
from archkeel.ir.languages import Language


@pytest.mark.parametrize("language", ["python", "dart"])
@pytest.mark.parametrize("command", ["report", "validate", "baseline", "explore", "init", "check"])
def test_unsupported_project_refuses_before_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    language: str,
    command: str,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.py").write_text("VALUE = 1\n")
    (tmp_path / "src/app.ts").write_text("export const value = 1;\n")
    (tmp_path / "src/app.dart").write_text("const value = 1;\n")
    (tmp_path / "archkeel.toml").write_text(
        f'[scan]\nlanguage = "{language}"\nroots = ["src"]\n'
        'namespace = "app"\ncontract = "architecture-contract.json"\n'
        'collector_argv = ["must-not-run"]\n'
    )
    (tmp_path / "architecture-contract.json").write_text("{}")
    for args in [
        ("init", "-q"),
        ("add", "."),
        ("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "test"),
    ]:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()

    def forbidden(*args, **kwargs):
        pytest.fail("collection starts before the unsupported-project refusal")

    monkeypatch.setattr(ProcessCollector, "collect", forbidden)
    options = [command, "--root", str(tmp_path), "--json"]
    if command == "baseline":
        options = [
            "validate",
            "--root",
            str(tmp_path),
            "--json",
            "--write-baseline",
            "--baseline",
            "baseline.json",
            "--accept-new",
        ]
    elif command in {"explore", "init"}:
        options += ["--language", language, "--source", "src", "--namespace", "app"]
    elif command == "check":
        options += ["--baseline", head, "--head", head, "--expectation-commit", head]
        options += [
            "--expected",
            "expectation.json",
            "--expected-digest",
            "0" * 64,
            "--branch",
            "main",
            "--accepted-branch",
            "main",
        ]
    assert main(options) == 2
    result = json.loads(capsys.readouterr().out)
    assert result.get("declared_rules") != "PASS"
    assert (
        f"{language.title()} projects are not supported in this version; use archkeel 4.0.1"
        in str(result)
    )
    assert not (tmp_path / "baseline.json").exists()


@pytest.mark.parametrize("language", [Language.PYTHON, Language.DART])
def test_direct_observer_and_config_have_typed_refusal(language: Language) -> None:
    from archkeel.ir.languages import UnsupportedProjectError

    with pytest.raises(UnsupportedProjectError):
        observer_for(language, collector_argv=("must-not-run",))
    with pytest.raises(UnsupportedProjectError):
        parse_config(
            (
                f'[scan]\nlanguage = "{language}"\nroots = ["src"]\n'
                'namespace = "app"\ncontract = "contract.json"\n'
            ).encode()
        )


@pytest.mark.parametrize(
    "profile,name", [("archkeel-python-analyzer", "Python"), ("archkeel-dart-analyzer", "Dart")]
)
def test_saved_facts_refuse_before_decode(tmp_path, capsys, profile, name):
    saved = tmp_path / "architecture.json"
    saved.write_text(json.dumps({"analyzer": {"name": profile}}))
    assert main(["report", "--input", str(saved), "--json"]) == 2
    assert (
        f"{name} projects are not supported in this version; use archkeel 4.0.1"
        in capsys.readouterr().out
    )
