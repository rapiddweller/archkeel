import hashlib
import json
import subprocess
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest
from test_delta import _model as _base_model

from pledge.check.git import GitError, check_git_order
from pledge.check.ratchets import measure_python_ratchets
from pledge.check.snapshot import SnapshotError
from pledge.ir.codec import canonical_report_bytes, parse_lock, parse_observation
from pledge.ir.lock import LockError, verify_observation


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _repo(tmp_path: Path) -> tuple[Path, str, str, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Pledge Test")
    (root / "expectation.json").write_text("{}\n", encoding="utf-8")
    (root / "code.py").write_text("value = 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "baseline")
    baseline = _git(root, "rev-parse", "HEAD")
    (root / "expectation.json").write_text('{"expected": true}\n', encoding="utf-8")
    _git(root, "add", "expectation.json")
    _git(root, "commit", "-q", "-m", "expectation")
    expectation = _git(root, "rev-parse", "HEAD")
    (root / "code.py").write_text("value = 2\n", encoding="utf-8")
    _git(root, "add", "code.py")
    _git(root, "commit", "-q", "-m", "candidate")
    head = _git(root, "rev-parse", "HEAD")
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-q", str(origin))
    _git(root, "remote", "add", "origin", str(origin))
    _git(root, "push", "-q", "origin", "HEAD:main")
    return root, baseline, expectation, head


def test_git_order_accepts_expectation_child_before_candidate(tmp_path: Path) -> None:
    root, baseline, expectation, head = _repo(tmp_path)
    assert (
        check_git_order(
            root,
            baseline=baseline,
            expectation=expectation,
            head=head,
            expected_path="expectation.json",
            branch="main",
        )
        == ()
    )


def test_git_order_rejects_extra_expectation_change_and_wrong_parent(tmp_path: Path) -> None:
    root, baseline, _, _ = _repo(tmp_path)
    (root / "extra.txt").write_text("extra\n", encoding="utf-8")
    _git(root, "add", "extra.txt")
    _git(root, "commit", "-q", "-m", "unrelated parent")
    (root / "expectation.json").write_text('{"expected": false}\n', encoding="utf-8")
    (root / "extra.txt").write_text("changed\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "bad expectation")
    expectation = _git(root, "rev-parse", "HEAD")
    failures = check_git_order(
        root,
        baseline=baseline,
        expectation=expectation,
        head=expectation,
        expected_path="expectation.json",
        branch="main",
    )
    assert "expectation commit must have exactly baseline as parent" in failures
    assert "expectation commit must change only the expectation file" in failures


def test_git_order_rejects_expectation_mutation_at_candidate(tmp_path: Path) -> None:
    root, baseline, expectation, head = _repo(tmp_path)
    (root / "expectation.json").write_text('{"expected": "mutated"}\n', encoding="utf-8")
    _git(root, "add", "expectation.json")
    _git(root, "commit", "-q", "-m", "mutate expectation")
    mutated = _git(root, "rev-parse", "HEAD")
    failures = check_git_order(
        root,
        baseline=baseline,
        expectation=expectation,
        head=mutated,
        expected_path="expectation.json",
        branch="main",
    )
    assert "candidate changed the published expectation" in failures


def test_git_order_requires_supplied_remote_ref(tmp_path: Path) -> None:
    root, baseline, expectation, head = _repo(tmp_path)
    with pytest.raises((GitError, SnapshotError)):
        check_git_order(
            root,
            baseline=baseline,
            expectation=expectation,
            head=head,
            expected_path="expectation.json",
            branch="missing",
        )


def _model() -> dict[str, Any]:
    return _base_model(git_head="a" * 40)


def _lock(model: dict[str, Any]) -> bytes:
    measurements = measure_python_ratchets(parse_observation(model))
    return json.dumps(
        {
            "schema_version": "1.0.0",
            "accepted_commit": "a" * 40,
            "observation_digest": hashlib.sha256(canonical_report_bytes(model)).hexdigest(),
            "config_digest": "b" * 64,
            "checker_digest": "c" * 64,
            "measurements": asdict(measurements),
            "approval_ref": "ci:accepted",
        }
    ).encode()


@pytest.mark.parametrize("mutation", [{"measurements": True}, {"approval_ref": None}])
def test_lock_rejects_boolean_or_missing_fields(mutation: dict[str, object]) -> None:
    model = _model()
    raw = json.loads(_lock(model))
    raw.update(mutation)
    with pytest.raises(LockError):
        parse_lock(json.dumps(raw).encode())


def test_lock_accepts_matching_observation() -> None:
    model = _model()
    lock = parse_lock(_lock(model))
    verify_observation(
        lock,
        observation_digest=hashlib.sha256(canonical_report_bytes(model)).hexdigest(),
        measurements=measure_python_ratchets(parse_observation(model)),
    )


def test_lock_rejects_observation_digest_mismatch() -> None:
    model = _model()
    lock = parse_lock(_lock(model))
    with pytest.raises(LockError, match="differs from the CI lock"):
        verify_observation(
            lock,
            observation_digest="d" * 64,
            measurements=measure_python_ratchets(parse_observation(model)),
        )


def test_lock_rejects_measurement_mismatch() -> None:
    model = _model()
    lock = parse_lock(_lock(model))
    measurements = measure_python_ratchets(parse_observation(model))
    measurements = replace(measurements, scalars=replace(measurements.scalars, violations=1))
    with pytest.raises(LockError, match="differs from the CI lock"):
        verify_observation(
            lock,
            observation_digest=hashlib.sha256(canonical_report_bytes(model)).hexdigest(),
            measurements=measurements,
        )


def test_lock_rejects_unbound_measurement_fields() -> None:
    raw = json.loads(_lock(_model()))
    raw["measurements"]["extra"] = 1
    with pytest.raises(LockError, match="measurement fields"):
        parse_lock(json.dumps(raw).encode())
