# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""An approval binds policy contents, not just totals or the contract."""

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from test_measurement_budgets import _contract_with_budgets
from test_widening import SHOP_CONFIG, _git, _repo_at_two_revisions

from archkeel.check.git import GitError
from archkeel.check.validation import run_validate
from archkeel.cli.observe import observe
from archkeel.ir.baseline import KnownViolation, ViolationFingerprint
from archkeel.ir.codec import (
    absent_baseline_digest,
    amendment_bytes,
    baseline_bytes,
    baseline_digest,
    parse_amendment,
    parse_validation_baseline,
)
from archkeel.ir.measurements import MeasurementBudget
from archkeel.ir.widening import Amendment, verify_amendment
from tools.against import select_amendment


def test_canonical_policy_identity_covers_roles_counts_names_and_absence() -> None:
    debt = KnownViolation(ViolationFingerprint(("R",), ("a", "b")), 1, (("a", "b"),))
    budgets = (
        MeasurementBudget("calls_unresolved", 682),
        MeasurementBudget("facade_names", 1, "x", ("a",)),
    )
    digest = baseline_digest((debt,), budgets)
    raw = json.loads(baseline_bytes((debt,), budgets))
    parsed = parse_validation_baseline(raw)
    assert digest == baseline_digest(parsed.violations, parsed.budgets)
    assert digest != baseline_digest((replace(debt, count=2),), budgets)
    assert digest != baseline_digest((replace(debt, roles=(("b", "a"),)),), budgets)
    assert digest != baseline_digest((debt,), (budgets[0], replace(budgets[1], names=("b",))))
    assert baseline_digest((), ()) != absent_baseline_digest("baseline.json")
    assert absent_baseline_digest("a") != absent_baseline_digest("b")


def test_v2_strict_and_legacy_contract_only() -> None:
    record = Amendment("a" * 64, "b" * 64, "who", "why", "c" * 64, "d" * 64)
    raw = json.loads(amendment_bytes(record))
    assert parse_amendment(raw) == record
    for key in ("before_baseline_digest", "after_baseline_digest"):
        missing = dict(raw)
        del missing[key]
        with pytest.raises(ValueError):
            parse_amendment(missing)
        with pytest.raises(ValueError):
            parse_amendment({**raw, key: "bad"})
    legacy = parse_amendment(
        {
            key: value
            for key, value in {**raw, "schema_version": "1.0.0"}.items()
            if "baseline" not in key
        }
    )
    assert verify_amendment(legacy, before_digest="a" * 64, after_digest="b" * 64)
    assert not verify_amendment(
        legacy, before_digest="a" * 64, after_digest="b" * 64, before_baseline_digest="c" * 64
    )


def test_baseline_amendment_exact_replay_and_stale_without_widening(tmp_path: Path) -> None:
    root, _ = _repo_at_two_revisions(
        tmp_path, {"architecture-contract.json": _contract_with_budgets("cycle_edges")}
    )
    baseline = root / "baseline.json"
    baseline.write_bytes(baseline_bytes((), (MeasurementBudget("cycle_edges", 0),)))
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "baseline")
    base = _git(root, "rev-parse", "HEAD")
    baseline.write_bytes(baseline_bytes((), (MeasurementBudget("cycle_edges", 2),)))
    (root / "shop/model/alpha.py").write_text("from shop.model import beta\nVALUE = beta.VALUE\n")
    (root / "shop/model/beta.py").write_text("from shop.model import alpha\nVALUE = 1\n")
    amendment = root / "amendment.json"
    result, files = run_validate(
        root,
        SHOP_CONFIG,
        observe,
        against=base,
        baseline=baseline,
        amendment=amendment,
        write_amendment=True,
        decided_by="who",
        rationale="why",
    )
    assert result.exit_code == 0
    amendment.write_bytes(files[str(amendment)])
    assert (
        run_validate(
            root, SHOP_CONFIG, observe, against=base, baseline=baseline, amendment=amendment
        )[0].exit_code
        == 0
    )
    for value in (9, 0):
        baseline.write_bytes(baseline_bytes((), (MeasurementBudget("cycle_edges", value),)))
        stale, _ = run_validate(
            root, SHOP_CONFIG, observe, against=base, baseline=baseline, amendment=amendment
        )
        assert stale.exit_code == 1
        assert any(
            "measurement budget widened" in item or "amendment does not bind" in item
            for item in stale.failures
        )


def test_selector_spaces_multiple_deleted_and_nonregular(tmp_path: Path) -> None:
    root, base = _repo_at_two_revisions(tmp_path, {})
    assert select_amendment(root, base, base) is None
    directory = root / "docs/architecture/decisions"
    directory.mkdir(parents=True, exist_ok=True)
    record = directory / "one space-amendment.json"
    record.write_text("{}")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "one")
    head = _git(root, "rev-parse", "HEAD")
    assert select_amendment(root, base, head) == record.relative_to(root).as_posix()
    record.unlink()
    record.symlink_to(directory / "missing")
    with pytest.raises(GitError):
        select_amendment(root, base, head)
    record.unlink()
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "delete")
    with pytest.raises(GitError):
        select_amendment(root, head, _git(root, "rev-parse", "HEAD"))
    for name in ("a", "b"):
        (directory / f"{name}-amendment.json").write_text("{}")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "two")
    with pytest.raises(GitError):
        select_amendment(root, base, _git(root, "rev-parse", "HEAD"))


def test_joint_write_replays_and_refused_rewrite_emits_no_approval(tmp_path: Path) -> None:
    root, _ = _repo_at_two_revisions(
        tmp_path, {"architecture-contract.json": _contract_with_budgets("cycle_edges")}
    )
    baseline = root / "baseline.json"
    baseline.write_bytes(baseline_bytes((), (MeasurementBudget("cycle_edges", 0),)))
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "baseline")
    base = _git(root, "rev-parse", "HEAD")
    (root / "shop/model/alpha.py").write_text("from shop.model import beta\nVALUE = beta.VALUE\n")
    (root / "shop/model/beta.py").write_text("from shop.model import alpha\nVALUE = 1\n")
    contract_path = root / "architecture-contract.json"
    contract = json.loads(contract_path.read_text())
    rule = next(item for item in contract["rules"] if item["id"] == "DEP-APP-NO-STORE-SQLITE")
    rule["allowed_sources"].append("shop.app.orders")
    contract_path.write_text(json.dumps(contract))
    amendment = root / "amendment.json"
    arguments = dict(
        against=base,
        baseline=baseline,
        amendment=amendment,
        write_baseline=True,
        write_amendment=True,
        decided_by="who",
        rationale="why",
    )
    refused, files = run_validate(root, SHOP_CONFIG, observe, **arguments)
    assert refused.exit_code == 1
    assert (
        "rule DEP-APP-NO-STORE-SQLITE.allowed_sources gained 'shop.app.orders'" in refused.failures
    )
    assert refused.widenings
    assert refused.amendment_status is None
    assert refused.artifact is None
    assert not files
    accepted, files = run_validate(root, SHOP_CONFIG, observe, accept_new=True, **arguments)
    assert accepted.exit_code == 0
    for path, data in files.items():
        Path(path).write_bytes(data)
    assert (
        run_validate(
            root, SHOP_CONFIG, observe, against=base, baseline=baseline, amendment=amendment
        )[0].exit_code
        == 0
    )
    replay = subprocess.run(
        [
            sys.executable,
            "-m",
            "archkeel.cli",
            "validate",
            "--root",
            str(root),
            "--against",
            base,
            "--baseline",
            "baseline.json",
            "--amendment",
            "amendment.json",
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert replay.returncode == 0, replay.stdout + replay.stderr
    record = json.loads(amendment.read_bytes())
    assert record["after_baseline_digest"] == baseline_digest(
        (), (MeasurementBudget("cycle_edges", 2),)
    )
    legacy = {key: value for key, value in record.items() if "baseline" not in key}
    legacy["schema_version"] = "1.0.0"
    amendment.write_text(json.dumps(legacy))
    assert (
        run_validate(
            root, SHOP_CONFIG, observe, against=base, baseline=baseline, amendment=amendment
        )[0].exit_code
        == 1
    )


def test_present_empty_and_absent_before_policies_cannot_share_approval(tmp_path: Path) -> None:
    root, absent = _repo_at_two_revisions(tmp_path, {})
    baseline = root / "baseline.json"
    baseline.write_bytes(baseline_bytes(()))
    amendment = root / "amendment.json"
    _, files = run_validate(
        root,
        SHOP_CONFIG,
        observe,
        against=absent,
        baseline=baseline,
        amendment=amendment,
        write_amendment=True,
        decided_by="who",
        rationale="why",
    )
    amendment.write_bytes(files[str(amendment)])
    assert (
        run_validate(
            root, SHOP_CONFIG, observe, against=absent, baseline=baseline, amendment=amendment
        )[0].exit_code
        == 0
    )
    _git(root, "add", "baseline.json")
    _git(root, "commit", "-qm", "present empty")
    present = _git(root, "rev-parse", "HEAD")
    result, _ = run_validate(
        root, SHOP_CONFIG, observe, against=present, baseline=baseline, amendment=amendment
    )
    assert result.exit_code == 1
    assert "amendment does not bind" in result.failures[0]


def test_selector_git_failure_is_not_no_amendment(tmp_path: Path) -> None:
    with pytest.raises(GitError):
        select_amendment(tmp_path, "bad", "HEAD")


def test_selector_main_pins_base_and_calls_existing_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import against

    root, base = _repo_at_two_revisions(tmp_path, {})
    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "argv", ["against", "--base", "main"])
    commands: list[list[str]] = []

    def run(command: list[str]) -> int:
        commands.append(command)
        return 1

    monkeypatch.setattr(against.subprocess, "call", run)
    assert against.main() == 1
    assert commands == [
        [
            sys.executable,
            "-m",
            "archkeel.cli",
            "validate",
            "--root",
            ".",
            "--baseline",
            "architecture-baseline.json",
            "--json",
            "--against",
            base,
        ]
    ]
    monkeypatch.setattr(sys, "argv", ["against", "--base", "missing-ref"])
    assert against.main() == 2
    assert len(commands) == 1


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("baseline.json", b"\0no baseline at baseline.json"),
        ("docs/maß.json", b"\0no baseline at docs/ma\xc3\x9f.json"),
    ],
)
def test_absent_baseline_digest_preserves_canonical_bytes(path: str, payload: bytes) -> None:
    assert absent_baseline_digest(path) == hashlib.sha256(payload).hexdigest()
