# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-67: an undecidable `boundary_types` position must surface as coverage UNKNOWN, not PASS
-- except an `external_type` one, which must not.

`inspect_observation` (`archkeel.check.run`) decided the coverage verdict from violations
alone, so a `boundary_type_limit` record naming undecided positions (AD-67) and an empty
`violations` section both read PASS. The vocabulary Archkeel already reports elsewhere
(PASS proven fine, FAIL proven wrong, UNKNOWN could not be decided) never reached this one
verdict. The owner's decision, refined once the first cut of this fix showed its
consequence (a repository whose facade merely takes a `pathlib.Path` or a
`datetime.datetime` reported UNKNOWN forever, PASS unreachable, including for the
purpose-built clean demo fixture):

    all relevant positions decided, no violation                  -> PASS
    at least one violation                                        -> FAIL
    an undecided position whose reason is a checker limit          -> UNKNOWN
    undecided positions whose only reason is `external_type`       -> PASS (not UNKNOWN)

`external_type` (`_boundary_type_verdict`, `violations.py`) fires once a position's type is
resolved to a defining module the contract simply does not own -- stdlib, third party, or an
in-repo module no component claims -- so `boundary_types` has no `public` list to read it
against; the question does not apply, it is not a gap in what the checker could read. The
six other kinds in `_UNDECIDABLE_KINDS` (`missing_annotation`, `forward_reference`,
`dotted_name`, `generic`, `union`, `unresolved_name`, `other`) are real checker limits and do
mean UNKNOWN. Nothing is hidden either way: `external_type`'s count stays in the record's
breakdown; it just does not flip the aggregate verdict.

The current `"FAIL" if violations else "PASS"` already keeps a violation FAIL and a
fully-decided, violation-free run PASS regardless of any `boundary_type_limit` record, so
those two rows on their own are not pinned here as failing tests -- doing so would assert
something already true and prove nothing. Their overlap is different: a run with *both* a
violation and an undecided position has no equivalent today (there is no UNKNOWN verdict
yet), so which one wins is a real constraint on the code this change introduces, and is
pinned below even though it happens to hold against today's violations-only logic too. What
follows also pins the new UNKNOWN row, its `external_type` carve-out, and that this is a
reporting change only: the `report`/`check` exit code and diagnostics for an UNKNOWN run
stay exactly what they are today.
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from hashlib import sha256
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from test_delta import _evidence, _model, _record
from test_expectation import _expectation_payload
from test_git_lock import _lock

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.run import inspect_observation, run_check
from archkeel.check.snapshot import ArchivedSnapshot
from archkeel.ir.codec import canonical_report_bytes, parse_observation
from archkeel.ir.digest import package_digest
from archkeel.ir.model import ObservationResult

# The exact eight kinds `_UNDECIDABLE_KINDS` (`archkeel/analyzer/embedded/violations.py`)
# names, so a record built here carries the same keys a real `boundary_type_limit` does.
# `external_type` is the one kind that does not mean "the checker could not read this."
_UNDECIDABLE_KINDS = (
    "missing_annotation",
    "forward_reference",
    "dotted_name",
    "generic",
    "union",
    "unresolved_name",
    "external_type",
    "other",
)


def _boundary_type_limit(
    identifier: str, *, positions: int, decided: int, **undecided_kinds: int
) -> dict[str, Any]:
    """The exact `data` shape `boundary_type_limits` emits: every kind key present, counting
    zero unless named in `undecided_kinds`. Omitting `undecided_kinds` puts the whole
    undecided count under `other`, a checker limit -- never under `external_type` -- so every
    caller that does not say otherwise still builds a genuine UNKNOWN scenario."""
    undecided = positions - decided
    counts = dict.fromkeys(_UNDECIDABLE_KINDS, 0)
    if undecided_kinds:
        counts.update(undecided_kinds)
        assert sum(counts.values()) == undecided, "undecided_kinds must sum to undecided"
    elif undecided:
        counts["other"] = undecided
    return _record(
        identifier,
        kind="boundary_type_limit",
        evidence_class="UNKNOWN",
        data={"positions": positions, "decided": decided, "undecided": undecided, **counts},
    )


def test_undecided_boundary_position_with_no_violation_reports_unknown_not_pass() -> None:
    """AD-67's own decision: a relevant position left undecidable for a checker-limit reason
    (`other`, here) is UNKNOWN, never PASS, even though `violations` is empty."""
    raw = _model(
        git_head="a" * 40,
        unknowns=[_boundary_type_limit("UNKNOWN-BOUNDARY", positions=8, decided=6)],
    )
    _, declared = inspect_observation(parse_observation(raw))
    assert declared == "UNKNOWN"


def test_undecided_positions_that_are_all_external_type_still_pass() -> None:
    """The refinement: `external_type` means the position's type belongs to no declared
    component, not that the checker failed to read the code, so it must not turn a
    violation-free run into UNKNOWN. These are Archkeel's own real numbers (one
    `boundary_type_limit` record, 8 positions, 6 decided, the 2 undecided both
    `external_type` -- `pathlib.Path` and `datetime.datetime`, types no component owns), so
    this is the exact case that must resolve to PASS, not a synthetic stand-in for it. A
    version that reads any `undecided > 0` as UNKNOWN regardless of reason fails this: it
    would report `declared_rules` UNKNOWN on Archkeel's own clean self-check forever, which
    is the defect the refinement exists to undo."""
    raw = _model(
        git_head="a" * 40,
        unknowns=[
            _boundary_type_limit("UNKNOWN-BOUNDARY", positions=8, decided=6, external_type=2)
        ],
    )
    _, declared = inspect_observation(parse_observation(raw))
    assert declared == "PASS"


def test_a_proven_violation_outranks_an_undecidable_boundary_position() -> None:
    """Precedence: a proven wrong outranks an undecidable position. UNKNOWN means "could not
    be decided"; a violation is a position that *was* decided, and decided wrong. A plausible
    but incorrect fix checks `undecided > 0` before it checks `violations`, so it reports a
    proven violation as merely UNKNOWN -- the worst failure mode for this change, since it
    would downgrade a proven-wrong finding to "could not tell." This has no equivalent today
    (there is no UNKNOWN verdict at all yet), so it is not an already-true invariant: it is a
    constraint on the implementation this change introduces, pinned before that code exists.
    """
    rule = {
        "id": "RULE",
        "evidence_class": "DECLARED_RULE",
        "area": "architecture",
        "kind": "forbidden_dependency",
        "title": "RULE",
        "subjects": ["datamimic_ee.tasks"],
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": ["architecture-contract.json"],
        "data": {},
    }
    fact = {
        "id": "FACT",
        "evidence_class": "FACT",
        "area": "architecture",
        "kind": "import",
        "title": "FACT",
        "subjects": ["datamimic_ee.tasks"],
        "evidence_ids": ["EVD"],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {},
    }
    violation = {
        "id": "VIO",
        "evidence_class": "VIOLATION",
        "area": "architecture",
        "kind": "forbidden_dependency",
        "title": "VIO",
        "subjects": ["datamimic_ee.tasks", "datamimic_ee.clients"],
        "evidence_ids": [],
        "rule_ids": ["RULE"],
        "fact_ids": ["FACT"],
        "provenance": [],
        "data": {
            "source_module": "datamimic_ee.tasks.sample",
            "target_module": "datamimic_ee.clients.api",
            "symbol": "Client",
            "under_type_checking": False,
        },
    }
    raw = _model(
        git_head="a" * 40,
        declarations=[rule],
        # Not `imports=`: `measure_python_ratchets` reads that section's `source_package`/
        # `target_package`, which this bare FACT record does not carry.
        modules=[fact],
        violations=[violation],
        evidence=[_evidence("EVD", 10)],
        unknowns=[_boundary_type_limit("UNKNOWN-BOUNDARY", positions=8, decided=6)],
    )
    _, declared = inspect_observation(parse_observation(raw))
    assert declared == "FAIL"


def test_report_command_keeps_exit_code_and_diagnostics_when_coverage_is_unknown(
    tmp_path: Path,
) -> None:
    """UNKNOWN is reported, not gated (this decision is separate from AD-67): `report`'s exit
    code and diagnostics for an otherwise-clean run must be unchanged by an undecided
    boundary position, even though `declared_rules` now reads UNKNOWN instead of PASS."""
    raw = _model(
        git_head="a" * 40,
        unknowns=[_boundary_type_limit("UNKNOWN-BOUNDARY", positions=8, decided=6)],
    )
    model = parse_observation(raw)

    def analyzer(*args: object, **kwargs: object) -> ObservationResult:
        return ObservationResult(model, model.coverage, ())

    with (
        patch("archkeel.check.report.resolve_commit", return_value="a" * 40),
        patch("archkeel.check.report.git_bytes", return_value=b""),
    ):
        result, _architecture = run_report(
            tmp_path,
            config=ScanConfig((".",), "sample", "contract.json", "d" * 64),
            analyzer=analyzer,
        )
    assert result.exit_code == 0
    assert result.diagnostics == ()
    assert result.declared_rules == "UNKNOWN"


def test_check_command_keeps_exit_code_and_diagnostics_when_coverage_is_unknown(
    tmp_path: Path,
) -> None:
    """The same guard as above, through `check`'s own gate (`1 if failures or declared ==
    "FAIL" else 0`, `archkeel.check.run.run_check`): an undecided boundary position must not
    move `check`'s exit code away from 0, proven end to end rather than assumed from reading
    the formula."""
    raw = _model(
        git_head="a" * 40,
        unknowns=[_boundary_type_limit("UNKNOWN-BOUNDARY", positions=8, decided=6)],
    )
    lock_bytes = _lock(raw)
    lock_payload = json.loads(lock_bytes)
    lock_payload["checker_digest"] = package_digest()
    lock_bytes = json.dumps(lock_payload).encode()
    observation = parse_observation(raw)
    observed = ObservationResult(observation, observation.coverage, ())
    analyzer = Mock(side_effect=[observed, observed])

    expected = _expectation_payload()
    expected.update(
        checker_digest=package_digest(),
        accepted_digest=sha256(lock_bytes).hexdigest(),
        baseline_commit="b" * 40,
        contract_digest="b" * 64,
        baseline_digest=sha256(canonical_report_bytes(raw)).hexdigest(),
        selected_changes=[],
    )
    expected_bytes = json.dumps(expected).encode()

    def read_blob(root: Path, commit: str, path: str) -> bytes:
        return expected_bytes if path == "expectation.json" else lock_bytes

    with (
        patch("archkeel.check.run.remote_tip", return_value="b" * 40),
        patch("archkeel.check.run.read_blob", side_effect=read_blob),
        patch("archkeel.check.run.parents", return_value=["a" * 40]),
        patch("archkeel.check.run.changed_paths", return_value={"architecture-accepted.json"}),
        patch("archkeel.check.run.check_git_order", return_value=()),
        patch("archkeel.check.run.check_order", return_value=()),
        patch("archkeel.check.run.materialize_declarations"),
        patch(
            "archkeel.check.run.materialize_git_snapshot",
            side_effect=lambda *args, **kwargs: nullcontext(ArchivedSnapshot(tmp_path, "a" * 40)),
        ),
    ):
        result = run_check(
            tmp_path,
            config=ScanConfig((".",), "sample", "contract.json", "b" * 64),
            baseline="b" * 40,
            expectation_commit="e" * 40,
            head="f" * 40,
            expected_path="expectation.json",
            expected_digest=sha256(expected_bytes).hexdigest(),
            branch="candidate",
            accepted_branch="main",
            host_records_path=None,
            environ={},
            host=Mock(return_value=()),
            analyzer=analyzer,
        )
    assert result.exit_code == 0
    assert result.diagnostics == ()
    assert result.failures == ()
    assert result.declared_rules == "UNKNOWN"
