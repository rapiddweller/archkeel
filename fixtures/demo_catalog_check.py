# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 protocol rows and the shared check-protocol runner: real `check` demos on the shop
sample.

`build_and_run_check` builds the M (accepted) -> B (lock) -> E (expectation) -> H (candidate)
protocol fresh for each scenario, on a copy of `fixtures/F-architecture`, and runs it through
`run_check` directly so assertions stay on typed `RunResult`/`ArchitectureDelta` values, never
on `failures` prose. This mirrors, but does not import, `fixtures/reproduce_milestone1.py`'s
protocol: that fixture drives the CLI over its own minimal `sample/` repo and renders HTML; this
one drives `run_check` in-process over the shop sample and needs neither. The class_b regression
rows that reuse this runner live in `fixtures/demo_catalog_check_regressions.py`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

from archkeel.analyzer import observe
from archkeel.check.delta import build_architecture_delta
from archkeel.check.expectation import EXPECTATION_SCHEMA_VERSION, GUARDRAIL_KEYS, sha256_bytes
from archkeel.check.ports import ScanConfig
from archkeel.check.ratchets import measure_python_ratchets
from archkeel.check.run import run_check
from archkeel.ir.codec import canonical_report_bytes
from archkeel.ir.digest import package_digest
from archkeel.ir.host_records import HostRecord
from archkeel.ir.lock import LOCK_PATH
from archkeel.ir.model import RunResult
from fixtures.demo_catalog_support import (
    FIXTURE_DIR,
    HEADER,
    CheckExpectation,
    CheckScenario,
    Variant,
    apply_overlay,
)

CONFIG = ScanConfig(("shop",), "shop", "architecture-contract.json", "0" * 64)
_PUBLISHED_FIRST = "2026-09-15T10:00:00Z"
_SUBMITTED_SECOND = "2026-09-15T10:01:00Z"


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "commit.gpgsign=false", *args], cwd=root, stderr=subprocess.PIPE, text=True
    ).strip()


def _write_json(path: Path, value: object) -> bytes:
    payload = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    path.write_bytes(payload)
    return payload


def _unused_host(
    root: Path, *, expectation_sha: str, candidate_sha: str, environ: Mapping[str, str]
) -> tuple[HostRecord, ...]:
    raise AssertionError("check demos always supply host records directly")


def build_and_run_check(
    tmp_path: Path, files: Mapping[str, str | None], scenario: CheckScenario
) -> RunResult:
    """Run the M -> B -> E -> H protocol for one scenario and return the typed check result."""
    root = tmp_path / "root"
    shutil.copytree(FIXTURE_DIR, root)
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-q", str(origin))
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "demo@example.invalid")
    _git(root, "config", "user.name", "Demo")
    _git(root, "remote", "add", "origin", str(origin))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "accepted code")
    accepted_commit = _git(root, "rev-parse", "HEAD")

    accepted_result = observe(
        root,
        roots=CONFIG.roots,
        namespace=CONFIG.namespace,
        contract=CONFIG.contract,
        git_head=accepted_commit,
        dirty=False,
        contract_root=root,
    )
    assert accepted_result.observation is not None, accepted_result.diagnostics
    accepted = accepted_result.observation

    lock = {
        "schema_version": "1.0.0",
        "accepted_commit": accepted_commit,
        "observation_digest": sha256_bytes(canonical_report_bytes(accepted)),
        "config_digest": CONFIG.digest,
        "checker_digest": package_digest(),
        "measurements": asdict(measure_python_ratchets(accepted)),
        "approval_ref": "fixture-only:simulated-host-approval",
    }
    lock_bytes = _write_json(root / LOCK_PATH, lock)
    _git(root, "add", LOCK_PATH)
    _git(root, "commit", "-q", "-m", "CI accepted lock")
    baseline = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "-q", "origin", "main")
    _git(root, "checkout", "-q", "-b", "candidate")

    # Private planning only; the expectation, not the code, is committed and published first.
    preview = tmp_path / "preview"
    shutil.copytree(root / "shop", preview / "shop")
    shutil.copyfile(root / "pyproject.toml", preview / "pyproject.toml")
    apply_overlay(preview, files)
    planned_result = observe(
        preview,
        roots=CONFIG.roots,
        namespace=CONFIG.namespace,
        contract=CONFIG.contract,
        git_head="f" * 40,
        dirty=False,
        contract_root=root,
    )
    assert planned_result.observation is not None, planned_result.diagnostics
    planned = planned_result.observation
    delta = build_architecture_delta(
        accepted,
        planned,
        baseline_digest=lock["observation_digest"],
        head_digest=sha256_bytes(canonical_report_bytes(planned)),
        checker_digest=package_digest(),
    )
    expectation = {
        "schema_version": EXPECTATION_SCHEMA_VERSION,
        "evidence_class": "HYPOTHESIS",
        "accepted_digest": sha256_bytes(lock_bytes),
        "baseline_commit": baseline,
        "checker_digest": package_digest(),
        "analyzer_digest": accepted.analyzer.code_digest,
        "contract_digest": accepted.contract.digest,
        "baseline_digest": lock["observation_digest"],
        # AD-39: "empty_declaration" declares no semantic change at all, rather than the
        # observed delta itself, so the empty list is a real declaration, not an omission.
        "selected_changes": (
            []
            if scenario == "empty_declaration"
            else [
                {
                    "dimension": change.dimension,
                    "change": change.change,
                    "fingerprint": change.fingerprint,
                    "before_count": change.before_count,
                    "after_count": change.after_count,
                }
                for change in delta.semantic_changes
            ]
        ),
        "guardrails": dict.fromkeys(GUARDRAIL_KEYS, True),
    }
    expectation_bytes = _write_json(root / "expectation.json", expectation)
    _git(root, "add", "expectation.json")
    _git(root, "commit", "-q", "-m", "declare candidate")
    declared = _git(root, "rev-parse", "HEAD")

    if scenario == "candidate_changed_expectation":
        # One extra byte after E, still an ancestor of H: check_git_order's predicate 5 alone.
        (root / "expectation.json").write_bytes(expectation_bytes + b"\n")
        _git(root, "add", "expectation.json")
        _git(root, "commit", "-q", "-m", "touch the published expectation")

    apply_overlay(root, files)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "candidate change")
    head = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "-q", "origin", "candidate")

    published = _SUBMITTED_SECOND if scenario == "published_after_candidate" else _PUBLISHED_FIRST
    submitted = _PUBLISHED_FIRST if scenario == "published_after_candidate" else _SUBMITTED_SECOND
    host_path = tmp_path / "host-records.json"
    _write_json(
        host_path,
        [
            {"sha": declared, "event": "expectation_published", "timestamp": published},
            {"sha": head, "event": "candidate_submitted", "timestamp": submitted},
        ],
    )

    return run_check(
        root,
        config=CONFIG,
        baseline=baseline,
        expectation_commit=declared,
        head=head,
        expected_path="expectation.json",
        expected_digest=sha256_bytes(expectation_bytes),
        branch="candidate",
        accepted_branch="main",
        host_records_path=host_path,
        environ={},
        host=_unused_host,
        analyzer=observe,
    )


_HARMLESS_FILES: Mapping[str, str | None] = {
    "shop/render/order_summary.py": HEADER
    + (
        '"""Harmless probe reusing the already-allowed render -> model edge."""\n\n'
        "from __future__ import annotations\n\n"
        "from shop.model.entities import Order\n\n\n"
        "def order_reference(order: Order) -> Order:\n"
        "    return order\n"
    )
}
# A comment adds no import, no call, no typed position: every dimension's before/after
# records stay byte-identical, so the delta this produces is genuinely empty (AD-39).
_COMMENT_ONLY_FILES: Mapping[str, str | None] = {
    "shop/model/entities.py": (FIXTURE_DIR / "shop/model/entities.py").read_text()
    + "\n# Pure refactor note: no behavior changes in this revision.\n"
}
_ORDERED = CheckExpectation(
    scenario="ordered",
    exit_code=0,
    expectation_fulfilled="PASS",
    git_predicate="PASS",
    host_order="PASS",
)
_PUBLISHED_AFTER = CheckExpectation(
    scenario="published_after_candidate",
    exit_code=1,
    expectation_fulfilled="FAIL",
    git_predicate="PASS",
    host_order="FAIL",
)
_EXPECTATION_CHANGED = CheckExpectation(
    scenario="candidate_changed_expectation",
    exit_code=1,
    expectation_fulfilled="FAIL",
    git_predicate="FAIL",
    host_order="PASS",
)
_EMPTY_DECLARATION = CheckExpectation(
    scenario="empty_declaration",
    exit_code=0,
    expectation_fulfilled="PASS",
    git_predicate="PASS",
    host_order="PASS",
)
_PROTOCOL_ROWS: tuple[Variant, ...] = (
    Variant(
        id="protocol-ordered",
        section="protocol",
        item="ordered",
        summary="A harmless candidate, declared and submitted in order on a real Git history, "
        "passes: exit 0, every verdict PASS.",
        files=_HARMLESS_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_ORDERED,
    ),
    Variant(
        id="protocol-published-after-candidate",
        section="protocol",
        item="host_order",
        summary="check_order's ordering predicate: the host's expectation_published timestamp "
        "is later than candidate_submitted, so host_order fails though the code and Git shape "
        "are unchanged.",
        files=_HARMLESS_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_PUBLISHED_AFTER,
    ),
    Variant(
        id="protocol-candidate-changed-expectation",
        section="protocol",
        item="git_order",
        summary="check_git_order's fifth predicate: one extra commit rewrites the published "
        "expectation blob before the candidate commit, so git_predicate fails though host "
        "ordering is correct.",
        files=_HARMLESS_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_EXPECTATION_CHANGED,
    ),
    Variant(
        id="protocol-empty-declaration",
        section="protocol",
        item="empty_declaration",
        summary="A comment-only edit declares `selected_changes: []`, the legal move for a "
        "candidate with nothing architectural to select (AD-39); the delta it produces is "
        "genuinely empty, so the declaration holds and every verdict passes.",
        files=_COMMENT_ONLY_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_EMPTY_DECLARATION,
    ),
)

VARIANTS: tuple[Variant, ...] = _PROTOCOL_ROWS
