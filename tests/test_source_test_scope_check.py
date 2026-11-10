# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-313: `check` names the test files of the revision it reads, not those of the worktree."""

import json
import shutil
from pathlib import Path

import pytest

from archkeel.cli import main
from archkeel.cli.config import parse_config
from archkeel.cli.observe import observer_for
from fixtures import demo_catalog_check


def test_check_names_the_test_files_of_the_revision_and_not_those_of_the_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = tmp_path / "fixture"
    shutil.copytree(demo_catalog_check.FIXTURE_DIR, fixture)
    payload = (
        b'[scan]\nroots=["shop"]\nnamespace="shop"\ncontract="architecture-contract.json"\n'
        b"exclude_test_sources=true\n"
    )
    (fixture / "archkeel.toml").write_bytes(payload)
    monkeypatch.setattr(demo_catalog_check, "FIXTURE_DIR", fixture)
    monkeypatch.setattr(demo_catalog_check, "CONFIG", parse_config(payload))
    files = {
        **demo_catalog_check._COMMENT_ONLY_FILES,
        "shop/model/test_in_revision.py": "VALUE = 1\n",
    }
    prepared = demo_catalog_check.build_and_run_check(
        tmp_path / "protocol",
        files,
        "empty_declaration",
        analyzer=observer_for("python", exclude_test_sources=True),
    )
    source = prepared.provenance
    assert source is not None
    root = tmp_path / "protocol/root"
    (root / "shop/model/test_worktree_only.py").write_text("VALUE = 2\n")
    code = main(
        [
            "check",
            "--root",
            str(root),
            "--baseline",
            source.baseline,
            "--expectation-commit",
            source.expectation,
            "--head",
            source.head,
            "--expected",
            "expectation.json",
            "--expected-digest",
            source.expected_digest,
            "--branch",
            "candidate",
            "--accepted-branch",
            "main",
            "--host-records",
            str(tmp_path / "protocol/host-records.json"),
            "--json",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 0, result
    claim = result["notes"][0]["unknown_claim"]
    assert "shop/model/test_in_revision.py" in claim
    assert "test_worktree_only" not in claim
