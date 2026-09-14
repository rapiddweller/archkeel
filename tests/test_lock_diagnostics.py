# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from test_git_lock import _lock, _model

from codekeel.check.ports import ScanConfig
from codekeel.cli import main
from codekeel.ir.lock import LOCK_PATH


@pytest.mark.parametrize("cause", ["json", "schema", "digest", "missing"])
def test_bad_lock_is_exit_two_with_diagnostic_and_never_replaced(
    tmp_path: Path, capsys: pytest.CaptureFixture, cause: str
) -> None:
    lock_path = tmp_path / LOCK_PATH
    if cause != "missing":
        lock_path.write_bytes(
            b"{" if cause == "json" else b"{}" if cause == "schema" else _lock(_model())
        )
    original = lock_path.read_bytes() if lock_path.exists() else None

    def read_blob(root: Path, commit: str, path: str) -> bytes:
        if not lock_path.exists():
            from codekeel.check.git import GitError

            raise GitError("accepted lock is missing")
        return lock_path.read_bytes()

    with (
        patch(
            "codekeel.cli.load_check_config",
            return_value=ScanConfig(("sample",), "sample", "contract.json", "b" * 64),
        ),
        patch("codekeel.check.run.remote_tip", return_value="b" * 40),
        patch("codekeel.check.run.read_blob", side_effect=read_blob),
        patch("codekeel.check.run.parents", return_value=["a" * 40]),
        patch("codekeel.check.run.changed_paths", return_value={LOCK_PATH}),
    ):
        code = main(
            [
                "check",
                "--root",
                str(tmp_path),
                "--producer-root",
                str(tmp_path.parent / "trusted-producer"),
                "--baseline",
                "b" * 40,
                "--expectation-commit",
                "e" * 40,
                "--head",
                "f" * 40,
                "--expected",
                "expectation.json",
                "--expected-digest",
                "d" * 64,
                "--branch",
                "candidate",
                "--accepted-branch",
                "main",
            ]
        )
    result = json.loads(capsys.readouterr().out)
    assert code == result["exit_code"] == 2
    assert result["diagnostics"][0]["kind"] == "parse_error"
    assert result["diagnostics"][0]["subject"] == LOCK_PATH
    assert result["observation_complete"] == result["expectation_fulfilled"] == "UNKNOWN"
    assert (lock_path.read_bytes() if lock_path.exists() else None) == original
