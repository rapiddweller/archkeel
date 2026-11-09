# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One command rewrites the stale digests of the amendment a branch adds (epic #880)."""

import json
import subprocess
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_widening import SHOP_CONFIG, _git

from archkeel.check.git import GitError
from archkeel.check.validation import run_validate
from archkeel.cli.observe import observe
from archkeel.ir.codec import baseline_bytes
from fixtures.demo_catalog_support import apply_overlay, contract_rule_field
from tools.against import refresh, validate_command

RULE = "DEP-APP-NO-STORE-SQLITE"
RECORD = "docs/architecture/decisions/shop-change-amendment.json"
MAIN_RECORD = "docs/architecture/decisions/main-owned-amendment.json"
MAIN_BYTES = '{"kept": "byte for byte"}\n'
WIDENED = ["shop.app.maintenance", "shop.app.orders"]


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message)
    return _git(root, "rev-parse", "HEAD")


def _status(root: Path, base: str) -> str:
    result = subprocess.run(
        validate_command(base, RECORD), cwd=root, capture_output=True, text=True
    )
    return str(json.loads(result.stdout).get("amendment_status"))


def _stale_branch(tmp_path: Path) -> tuple[Path, str]:
    """A branch whose amendment binds an older base; the returned base is the newer one."""
    files: dict[str, str | None] = {
        "architecture-baseline.json": baseline_bytes(()).decode(),
        MAIN_RECORD: MAIN_BYTES,
    }
    root = _prepare_repo(tmp_path, files)
    old = _git(root, "rev-parse", "HEAD")
    widened = contract_rule_field(RULE, allowed_sources=WIDENED, rationale="main moved")
    apply_overlay(root, {"architecture-contract.json": widened})
    amendment = root / RECORD
    amendment.parent.mkdir(parents=True, exist_ok=True)
    _, written = run_validate(
        root,
        SHOP_CONFIG,
        observe,
        against=old,
        baseline=root / "architecture-baseline.json",
        amendment=amendment,
        write_amendment=True,
        decided_by="who decided",
        rationale="the stated cause",
    )
    stale = dict(written.entries)[str(amendment)]
    _git(root, "checkout", "-q", "--", ".")
    apply_overlay(
        root, {"architecture-contract.json": contract_rule_field(RULE, rationale="main moved")}
    )
    new = _commit(root, "main moves on")
    _git(root, "checkout", "-q", "-b", "feature")
    apply_overlay(root, {"architecture-contract.json": widened})
    amendment.write_bytes(stale)
    _commit(root, "feature")
    return root, new


def test_a_stale_amendment_becomes_valid_and_only_its_digests_change(tmp_path: Path) -> None:
    root, base = _stale_branch(tmp_path)
    before = json.loads((root / RECORD).read_bytes())
    assert _status(root, base) == "stale"

    assert refresh(root, base) == [RECORD]

    after = json.loads((root / RECORD).read_bytes())
    assert _status(root, base) == "valid"
    for key in ("decided_by", "rationale", "schema_version"):
        assert after[key] == before[key]
    changed = {key for key in after if after[key] != before[key]}
    assert changed
    assert changed <= {
        "before_digest",
        "after_digest",
        "before_baseline_digest",
        "after_baseline_digest",
    }
    assert set(after) == set(before)


def test_a_second_run_changes_nothing_and_main_records_stay_identical(tmp_path: Path) -> None:
    root, base = _stale_branch(tmp_path)
    refresh(root, base)
    _commit(root, "refresh")
    first = (root / RECORD).read_bytes()

    assert refresh(root, base) == []

    assert (root / RECORD).read_bytes() == first
    assert (root / MAIN_RECORD).read_text() == MAIN_BYTES


def test_a_dirty_tree_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    root, base = _stale_branch(tmp_path)
    stale = (root / RECORD).read_bytes()
    (root / "scratch.txt").write_text("not committed")

    with pytest.raises(GitError, match="not clean"):
        refresh(root, base)

    assert (root / RECORD).read_bytes() == stale


def test_a_branch_without_amendments_is_a_no_op(tmp_path: Path) -> None:
    root, base = _stale_branch(tmp_path)
    _git(root, "checkout", "-q", "-b", "plain", base)

    assert refresh(root, base) == []
    assert _git(root, "status", "--porcelain") == ""


def test_a_deleted_amendment_is_skipped(tmp_path: Path) -> None:
    root, base = _stale_branch(tmp_path)
    (root / RECORD).unlink()
    _commit(root, "delete")

    assert refresh(root, base) == []
