# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-92: undecided declared evidence is UNKNOWN by default, and it is measured.

`inspect_observation` read `declared_rules` as UNKNOWN only for two named `unknowns` kinds
(`boundary_type_limit`, `api_surface_limit`). A kind a future analyzer profile emits -- a Dart
import whose used symbol cannot be known, say -- read PASS: false safety by default, the defect
AD-67 warns about, one level up. The fix names the exceptions instead of the rules: only the
standing disclaimers and `coverage.failures` records count nothing, so a new kind counts.

These tests pin that one count (`unknown_positions`) and the verdict it drives, and that the
count every Python observation produces today keeps the verdict it had: `api_surface_limit`
counts one, `boundary_type_limit` counts exactly its AD-67 checker-limit positions, the three
disclaimers stay neutral. They also pin that the same count is the `unknown_positions`
regression scalar, so a new UNKNOWN is something `check` and a measurement budget can see.
"""

from __future__ import annotations

from typing import Any

import pytest
from test_boundary_type_unknown_verdict import _boundary_type_limit
from test_delta import _evidence, _model, _record

from archkeel.check.ratchets import compare_ratchets, measure_python_ratchets, unknown_positions
from archkeel.check.run import inspect_observation
from archkeel.ir.codec import parse_observation
from archkeel.ir.measurements import RatchetError
from archkeel.ir.model import Observation

# A kind no analyzer emits today: it stands for whatever the next profile adds.
_NOVEL_KIND = "dart_import_symbol_limit"
_STANDING_DISCLAIMERS = (
    "dynamic_call_limit",
    "context_alias_limit",
    "private_attribute_access_limit",
)


def _unknown(identifier: str, kind: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return _record(identifier, kind=kind, evidence_class="UNKNOWN", data=data)


def _observation(*unknowns: dict[str, Any], **sections: Any) -> Observation:
    return parse_observation(_model(git_head="a" * 40, unknowns=list(unknowns), **sections))


def _verdict(observation: Observation) -> str:
    return inspect_observation(observation)[1]


def test_a_novel_unknowns_kind_reports_unknown_not_pass() -> None:
    """T1: the defect itself. An allow-list of two kinds read this record as PASS."""
    observation = _observation(_unknown("NOVEL", _NOVEL_KIND))

    assert _verdict(observation) == "UNKNOWN"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"undecided": 3}, 3),
        ({"undecided": 0}, 1),
        # A bool is an int in Python, so `False` would otherwise read as "nothing open".
        ({"undecided": True}, 1),
        ({"undecided": False}, 1),
        ({"undecided": -1}, 1),
        ({"undecided": "3"}, 1),
        ({}, 1),
    ],
)
def test_a_novel_kind_counts_its_undecided_field_or_one(
    data: dict[str, Any], expected: int
) -> None:
    """T2: a record that says how many positions it left open is read at its word; one that
    does not, or says it in a shape that is not a count, is still at least one gap."""
    observation = _observation(_unknown("NOVEL", _NOVEL_KIND, data))

    assert unknown_positions(observation) == expected
    assert _verdict(observation) == ("UNKNOWN" if expected else "PASS")


@pytest.mark.parametrize("kind", _STANDING_DISCLAIMERS)
def test_a_standing_disclaimer_alone_counts_nothing_and_passes(kind: str) -> None:
    """T3: these fire on every run regardless of the contract (or carry their own scalar), so
    counting them would make PASS unreachable. An `undecided` field does not change that."""
    observation = _observation(_unknown("DISCLAIMER", kind, {"undecided": 5}))

    assert unknown_positions(observation) == 0
    assert _verdict(observation) == "PASS"


def test_a_record_already_in_coverage_failures_counts_nothing() -> None:
    """T4: it already makes the scan incomplete (exit 2); counting it again would report one
    gap twice. `inspect_observation` refuses an incomplete scan, so the count is read alone."""
    failure = _unknown("GIT", "git_metadata_failure")
    raw = _model(git_head="a" * 40, unknowns=[failure], coverage_status="FAIL")
    raw["coverage"]["failures"] = [failure]

    assert unknown_positions(parse_observation(raw)) == 0


def test_only_the_failing_record_is_excused_by_coverage_failures() -> None:
    """T4, the other side: the exemption is by id, not a blanket for any incomplete scan."""
    failure = _unknown("GIT", "git_metadata_failure")
    raw = _model(
        git_head="a" * 40,
        unknowns=[failure, _unknown("NOVEL", _NOVEL_KIND, {"undecided": 2})],
        coverage_status="FAIL",
    )
    raw["coverage"]["failures"] = [failure]

    assert unknown_positions(parse_observation(raw)) == 2


def test_boundary_type_limit_of_external_type_only_counts_nothing_and_passes() -> None:
    """T5: AD-67's refinement. `external_type` means no component owns the type, not that
    the checker could not read it; the totals are not positions of their own."""
    observation = _observation(
        _boundary_type_limit("BOUNDARY", positions=8, decided=3, external_type=5)
    )

    assert unknown_positions(observation) == 0
    assert _verdict(observation) == "PASS"


def test_boundary_type_limit_with_all_positions_decided_counts_nothing() -> None:
    observation = _observation(_boundary_type_limit("BOUNDARY", positions=3, decided=3))

    assert unknown_positions(observation) == 0
    assert _verdict(observation) == "PASS"


def test_boundary_type_limit_counts_only_its_checker_limit_kinds() -> None:
    """T5: `union=2, external_type=5` is two open positions, not seven (`undecided`) nor
    fourteen (every numeric field), so the record is not read as a novel kind."""
    observation = _observation(
        _boundary_type_limit("BOUNDARY", positions=9, decided=2, union=2, external_type=5)
    )

    assert unknown_positions(observation) == 2
    assert _verdict(observation) == "UNKNOWN"


def test_boundary_position_records_are_counted_once_and_must_match_aggregate() -> None:
    detail = {
        "module": "sample.api",
        "qualified_name": "sample.api.fetch",
        "position": "stamp",
        "annotation": "datetime.datetime",
        "reason": "dotted_name",
        "occurrence": 0,
    }
    aggregate = _boundary_type_limit("BOUNDARY", positions=1, decided=0, dotted_name=1)
    aggregate["rule_ids"] = ["BOUNDARY"]
    aggregate["data"]["undecidable_positions"] = [detail]
    position = _unknown("POSITION", "boundary_type_position", detail)
    position["rule_ids"] = ["BOUNDARY"]

    assert unknown_positions(_observation(aggregate, position)) == 1
    with pytest.raises(RatchetError, match="missing or inconsistent"):
        unknown_positions(_observation(aggregate))
    duplicate = _unknown("POSITION-2", "boundary_type_position", detail)
    duplicate["rule_ids"] = ["BOUNDARY"]
    with pytest.raises(RatchetError, match="missing or inconsistent"):
        unknown_positions(_observation(aggregate, position, duplicate))


def test_legacy_boundary_aggregate_without_details_remains_countable() -> None:
    assert (
        unknown_positions(
            _observation(_boundary_type_limit("BOUNDARY", positions=3, decided=1, union=2))
        )
        == 2
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("positions", True), ("decided", -1), ("undecided", 1), ("union", True)],
)
def test_malformed_boundary_type_limit_is_rejected(field: str, value: object) -> None:
    record = _boundary_type_limit("BOUNDARY", positions=3, decided=1, union=2)
    record["data"][field] = value
    observation = _observation(record)

    with pytest.raises(RatchetError, match="incoherent aggregate counts"):
        unknown_positions(observation)


def test_each_api_surface_limit_counts_one() -> None:
    """Python parity: the record names one `public_api` entry and carries no counter."""
    observation = _observation(
        _unknown("API-1", "api_surface_limit", {"module": "a", "name": "x"}),
        _unknown("API-2", "api_surface_limit", {"module": "a", "name": "y"}),
    )

    assert unknown_positions(observation) == 2
    assert _verdict(observation) == "UNKNOWN"


def test_a_proven_violation_outranks_an_undecided_novel_kind() -> None:
    """T6: a violation was decided, and decided wrong; downgrading it to "could not tell"
    because some other position is open would be the worst reading of this change."""
    rule = _record("DEP-TASKS-NO-CLIENTS", kind="forbidden_dependency")
    rule["evidence_class"] = "DECLARED_RULE"
    rule["provenance"] = ["architecture-contract.json"]
    fact = _record("FACT", kind="import", evidence_id="EVD")
    violation = _record("VIO", kind="forbidden_dependency", evidence_class="VIOLATION")
    violation.update(
        fact_ids=["FACT"],
        data={
            "source_module": "datamimic_ee.tasks.sample",
            "target_module": "datamimic_ee.clients.api",
            "symbol": "Client",
            "under_type_checking": False,
        },
    )
    observation = _observation(
        _unknown("NOVEL", _NOVEL_KIND, {"undecided": 3}),
        declarations=[rule],
        modules=[fact],
        violations=[violation],
        evidence=[_evidence("EVD", 10)],
    )

    assert _verdict(observation) == "FAIL"


def test_the_regression_scalar_is_the_same_count() -> None:
    """T7: one count, two readers. A scalar computed on its own would drift from the verdict."""
    observation = _observation(
        _unknown("NOVEL", _NOVEL_KIND, {"undecided": 3}),
        _unknown("API", "api_surface_limit", {"module": "a", "name": "x"}),
        _boundary_type_limit("BOUNDARY", positions=9, decided=2, union=2, external_type=5),
        *(_unknown(kind, kind, {"undecided": 4}) for kind in _STANDING_DISCLAIMERS),
    )

    assert unknown_positions(observation) == 6
    assert measure_python_ratchets(observation).scalars.unknown_positions == 6


def test_a_new_unknown_position_fails_the_regression_check() -> None:
    """T10: `check` compares the new scalar like every other one, so a rise fails."""
    accepted = measure_python_ratchets(_observation())
    candidate = measure_python_ratchets(_observation(_unknown("NOVEL", _NOVEL_KIND)))

    assert compare_ratchets(accepted, candidate) == (
        "regression check failed in unknown_positions: 0->1",
    )
