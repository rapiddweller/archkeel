# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""First-run guidance must lead to an executable, decided target."""

import json
import subprocess
from pathlib import Path

import pytest

from archkeel.check.onboarding import run_init
from archkeel.cli import main
from archkeel.cli.observe import observe


def repository(root: Path, *, cyclic: bool = False, initialize_git: bool = True) -> Path:
    files = {
        "src/demo/__init__.py": "",
        "src/demo/domain/__init__.py": "",
        "src/demo/domain/api.py": '__all__ = ["VALUE"]\nVALUE = 1\n',
        "src/demo/storage/__init__.py": "",
        "src/demo/storage/api.py": "from demo.domain import api\nVALUE = api.VALUE\n",
        "pyproject.toml": '[project]\nname = "demo"\nrequires-python = ">=3.11"\n',
    }
    if cyclic:
        files["src/demo/domain/api.py"] += "from demo.storage import api\nOTHER = api.VALUE\n"
    for name, source in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    if initialize_git:
        for args in (
            ("init", "-q"),
            ("config", "user.email", "guidance@example.invalid"),
            ("config", "user.name", "Guidance test"),
            ("add", "."),
            ("-c", "commit.gpgsign=false", "commit", "-qm", "source"),
        ):
            subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


@pytest.mark.parametrize("command", ["report", "validate"])
def test_missing_default_config_names_setup_and_restore(
    tmp_path: Path, capsys: pytest.CaptureFixture, command: str
) -> None:
    assert main([command, "--root", str(tmp_path), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    diagnostic = result["diagnostics"][0]
    assert "archkeel init" in diagnostic["remedy"]
    assert "restore" in diagnostic["remedy"].lower()
    assert diagnostic["kind"] == ("contract_invalid" if command == "validate" else "parse_error")
    if command == "validate":
        assert diagnostic["code"] == "contract.invalid"


@pytest.mark.parametrize("command", ["report", "validate"])
@pytest.mark.parametrize("config", ["custom.toml", "archkeel.toml"])
def test_bad_config_does_not_suggest_overwriting_policy(
    tmp_path: Path, capsys: pytest.CaptureFixture, command: str, config: str
) -> None:
    if config == "archkeel.toml":
        (tmp_path / config).write_text("[broken")
    assert main([command, "--root", str(tmp_path), "--config", config, "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert "archkeel init" not in result["diagnostics"][0]["remedy"]
    if config == "custom.toml":
        assert "--config" in result["diagnostics"][0]["remedy"]


@pytest.mark.parametrize("config", ["../archkeel.toml", "archkeel.toml"])
def test_unsafe_config_keeps_corrective_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture, config: str
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "archkeel.toml"
    outside.write_text("[scan]")
    if config == "archkeel.toml":
        (root / config).symlink_to(outside)
    assert main(["report", "--root", str(root), "--config", config, "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert "archkeel init" not in result["diagnostics"][0]["remedy"]
    assert (
        "escapes" in result["diagnostics"][0]["unknown_claim"]
        or "safe" in result["diagnostics"][0]["unknown_claim"]
    )


@pytest.mark.parametrize("agent, invocation", [("codex", "$archkeel"), ("claude", "/archkeel")])
def test_skill_install_names_invocation_only_in_terminal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    agent: str,
    invocation: str,
) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    assert main(["skill", "install", agent, "--root", str(tmp_path)]) == 0
    assert f"Use {invocation} " in capsys.readouterr().out
    assert main(["skill", "install", agent, "--root", str(tmp_path), "--json"]) == 0
    assert set(json.loads(capsys.readouterr().out)) == {"command", "exit_code", "path"}


def test_init_api_returns_the_same_typed_git_remedy(tmp_path: Path) -> None:
    from archkeel.ir.model import DiagnosticError

    root = repository(tmp_path, initialize_git=False)
    assert not (root / ".git").exists()
    with pytest.raises(DiagnosticError) as failure:
        run_init(root, source=None, namespace=None, force=False, analyzer=observe)
    assert failure.value.diagnostic.kind == "parse_error"
    assert "git init" in failure.value.diagnostic.remedy
    assert "commit" in failure.value.diagnostic.remedy
