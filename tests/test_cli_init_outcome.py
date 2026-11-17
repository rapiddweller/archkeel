# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The outcome of the draft step of `validate` and `report` (AD-735).

The shell finds the core before the draft writes a file, a run that fails after a write still
prints what it wrote, `ARCHKEEL_NO_INIT=false` does not opt out, and each stop names its state and
a fix that fits it.
"""

import json
import subprocess
from pathlib import Path

import pytest

from archkeel.cli import core_only
from archkeel.cli.core_binary import CoreBinaryNotFound
from archkeel.cli.core_json import CoreError
from tests.test_cli_init import plant

DRAFT = ("archkeel.toml", "architecture-contract.json", "docs/architecture/architecture.md")


def _repository(root: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=plant(root), check=True)
    return root


def _drafted(root: Path) -> set[str]:
    return {name for name in DRAFT if (root / name).exists()}


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = core_only.run(list(argv))
    return code, capsys.readouterr().out


def _no_core() -> Path:
    raise CoreBinaryNotFound("the core binary is missing")


def _core_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def exchange(*_: object) -> tuple[bytes, int]:
        raise CoreError("the core did not answer in 600 s")

    monkeypatch.setattr(core_only, "locate_core", lambda: tmp_path / "archkeel-core")
    monkeypatch.setattr(core_only, "exchange", exchange)


def test_a_missing_core_is_found_before_the_draft_writes_a_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "p")
    monkeypatch.setattr(core_only, "locate_core", _no_core)
    code, out = _run(capsys, "validate", "--root", str(root), "--json")
    assert code == 2 and _drafted(root) == set()
    assert json.loads(out)["refusal"]["kind"] == "core_binary_not_found"


def test_a_run_that_fails_after_the_draft_still_prints_what_it_wrote(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "p")
    _core_fails(monkeypatch, tmp_path)
    code, text = _run(capsys, "validate", "--root", str(root), "--text")
    assert code == 2 and _drafted(root) == set(DRAFT)
    lines = text.splitlines()
    assert lines[0].startswith("ArchKeel created archkeel.toml and a first contract draft"), text
    # AD-776: the refusal names the root and the configuration of the run.
    assert any(line.startswith("validate: REFUSED -> exit 2 · root ") for line in lines), text
    assert "Problem: the core did not answer in 600 s" in lines


def test_a_json_run_that_fails_after_the_draft_carries_the_init_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "p")
    _core_fails(monkeypatch, tmp_path)
    code, out = _run(capsys, "validate", "--root", str(root), "--json")
    document = json.loads(out)
    assert code == 2 and document["refusal"]["kind"] == "core_error"
    assert document["init"]["state"] == "created"
    assert document["init"]["written"] == list(DRAFT)


@pytest.mark.parametrize("value", ["", "0", "false", "False", "no", "off"])
def test_a_false_value_of_the_variable_does_not_opt_out(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    root = _repository(tmp_path / "p")
    _core_fails(monkeypatch, tmp_path)
    monkeypatch.setenv("ARCHKEEL_NO_INIT", value)
    _run(capsys, "validate", "--root", str(root), "--json")
    assert _drafted(root) == set(DRAFT)


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "anything"])
def test_another_value_of_the_variable_opts_out(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    root = _repository(tmp_path / "p")
    _core_fails(monkeypatch, tmp_path)
    monkeypatch.setenv("ARCHKEEL_NO_INIT", value)
    code, out = _run(capsys, "validate", "--root", str(root), "--json")
    assert code == 2 and _drafted(root) == set()
    assert json.loads(out)["init"] == {"state": "opted_out"}


def test_an_opt_out_names_its_state_and_a_fix_that_fits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "p")
    _core_fails(monkeypatch, tmp_path)
    code, out = _run(capsys, "validate", "--root", str(root), "--json", "--no-init")
    document = json.loads(out)
    assert code == 2 and document["refusal"]["kind"] == "invalid_input"
    assert document["init"] == {"state": "opted_out"}
    code, text = _run(capsys, "validate", "--root", str(root), "--text", "--no-init")
    assert text.splitlines()[-1] == (
        "Fix: run `archkeel init` to write the draft, or run again without --no-init and "
        "ARCHKEEL_NO_INIT."
    )


def test_a_layout_without_a_draft_names_its_state_and_a_fix_that_fits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "p"
    root.mkdir()
    (root / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    _core_fails(monkeypatch, tmp_path)
    code, out = _run(capsys, "validate", "--root", str(root), "--json")
    assert code == 2 and json.loads(out)["init"] == {"state": "nothing_to_draft"}
    _, text = _run(capsys, "validate", "--root", str(root), "--text")
    assert text.splitlines()[-1] == (
        "Fix: write archkeel.toml and a contract by hand (the guide shows how), or name a "
        "configuration with --config PATH."
    )


@pytest.mark.skipif(
    not hasattr(__import__("os"), "geteuid") or __import__("os").geteuid() == 0,
    reason="needs a folder that is read-only",
)
def test_a_folder_that_cannot_be_written_is_an_io_error_with_a_fix_that_fits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path / "p")
    _core_fails(monkeypatch, tmp_path)
    root.chmod(0o555)
    try:
        code, out = _run(capsys, "validate", "--root", str(root), "--json")
        _, text = _run(capsys, "validate", "--root", str(root), "--text")
    finally:
        root.chmod(0o755)
    document = json.loads(out)
    assert code == 2 and document["refusal"]["kind"] == "io_error"
    assert document["init"] == {"state": "cannot_write"}
    assert text.splitlines()[-1] == "Fix: allow writing in the project folder, then run again."
