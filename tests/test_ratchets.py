# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import copy
from typing import Any

import pytest
from test_delta import _delta, _evidence, _model, _record, _violation
from test_expectation import (
    _delta_payload,
    _expectation_payload,
    _measurements,
    _projection,
    _typed_delta,
)

from archkeel.check.expectation import (
    ExpectationError,
    ExpectationResult,
    evaluate_expectation,
    parse_expectation,
)
from archkeel.check.ratchets import compare_ratchets, measure_python_ratchets
from archkeel.ir.codec import parse_measurements, parse_observation
from archkeel.ir.measurements import Measurements, RatchetError, RatchetScalars


def _calls(model: dict[str, Any], unresolved: int, total: int) -> None:
    model["coverage"].update(
        calls_analyzed=total,
        calls_unresolved=unresolved,
        calls_resolved=total - unresolved,
        calls_partially_resolved=0,
    )


def _snapshots() -> tuple[dict[str, Any], dict[str, Any]]:
    accepted = _model(
        git_head="1" * 40,
        violations=[_violation("VIO-1", "EVD-1")],
        evidence=[_evidence("EVD-1", 10)],
    )
    candidate = copy.deepcopy(accepted)
    candidate["source"]["git_head"] = "2" * 40
    candidate["evidence"][0]["line"] = 20
    candidate["evidence"][0]["end_line"] = 20
    return accepted, candidate


def _evaluate(delta: dict[str, Any]) -> ExpectationResult:
    payload = _expectation_payload()
    for key in ("checker_digest", "analyzer_digest", "contract_digest", "baseline_digest"):
        payload[key] = delta["provenance"][key]
    selected = next(
        (item for item in delta["semantic_changes"] if item["dimension"] == "violations"), None
    )
    if selected is not None:
        payload["selected_changes"] = [
            {
                key: selected[key]
                for key in ("dimension", "change", "fingerprint", "before_count", "after_count")
            }
        ]
    return evaluate_expectation(_typed_delta(delta), parse_expectation(payload))


def test_all_six_extents_preserve_raw_measurements() -> None:
    model = _model(git_head="1" * 40, violations=[_violation("v", "e")])
    model["cycles"] = [_record("c", kind="module_scc", data={"internal_edges": ["a", "b"]})]
    model["imports"] = [
        _record(
            "i", kind="import", data={"source_package": "a", "target_package": "b", "symbol": "_x"}
        )
    ]
    model["typing_signals"] = [
        _record("t", kind="missing_cross_package_annotation", data={"positions": ["x", "return"]}),
        _record("u", kind="any_annotation"),
    ]
    _calls(model, 2, 5)
    model["coverage"]["call_resolution_percent"] = 100.0
    assert measure_python_ratchets(parse_observation(model)) == Measurements(
        RatchetScalars(1, 2, 1, 3, 2, 0), 5, "measured"
    )


@pytest.mark.parametrize(
    ("before_u", "before_t", "after_u", "after_t", "failures"),
    [
        (1, 2, 2, 4, ("calls_unresolved",)),
        (1, 4, 1, 2, ("unresolved_ratio",)),
        (2, 4, 1, 2, ()),
        (2, 3, 1, 4, ()),
        (0, 0, 0, 5, ()),
        (0, 0, 1, 5, ("calls_unresolved",)),
        (1, 5, 0, 0, ()),
        (0, 0, 0, 0, ()),
        (1, 10**20, 1, 10**20 - 1, ("unresolved_ratio",)),
    ],
)
def test_unresolved_count_and_ratio_are_independent_exact_ratchets(
    before_u: int, before_t: int, after_u: int, after_t: int, failures: tuple[str, ...]
) -> None:
    accepted, candidate = _snapshots()
    _calls(accepted, before_u, before_t)
    _calls(candidate, after_u, after_t)
    delta = _delta(accepted, candidate)
    assert delta["ratchets"]["baseline"]["resolution"] == ("measured" if before_t else "n/a")
    assert delta["ratchets"]["head"]["resolution"] == ("measured" if after_t else "n/a")
    result = _evaluate(delta)
    assert len(result.failures) == len(failures)
    for name in failures:
        assert any(f"regression check failed in {name}:" in failure for failure in result.failures)


def test_same_unknown_record_with_larger_unresolved_extent_fails() -> None:
    accepted, candidate = _snapshots()
    _calls(accepted, 0, 2)
    _calls(candidate, 1, 1)
    for model in (accepted, candidate):
        model["unknowns"] = [
            _record(
                "dynamic",
                kind="dynamic_call_limit",
                evidence_class="UNKNOWN",
                data={"unresolved_calls": model["coverage"]["calls_unresolved"]},
            )
        ]
    delta = _delta(accepted, candidate)
    unknowns = delta["dimensions"]["unknowns"]
    assert unknowns["before_count"] == unknowns["after_count"] == 1
    assert unknowns["added"] == []
    assert len(unknowns["changed"]) == 1
    assert _evaluate(delta).failures == (
        "regression check failed in calls_unresolved: 0->1",
        "regression check failed in unresolved_ratio: 0/2->1/1",
    )


def test_denser_cycle_with_same_members_and_fingerprints_fails() -> None:
    accepted, candidate = _snapshots()
    for model, edges in [(accepted, ["ab", "ba"]), (candidate, ["ab", "ba", "aa"])]:
        model["cycles"] = [
            _record(
                "cycle",
                kind="module_scc",
                data={"level": "module", "members": ["a", "b"], "internal_edges": edges},
            )
        ]
    delta = _delta(accepted, candidate)
    cycles = delta["dimensions"]["cycles"]
    assert cycles["before_count"] == cycles["after_count"] == 1
    assert cycles["added"] == cycles["removed"] == cycles["changed"] == []
    assert _evaluate(delta).failures == ("regression check failed in cycle_edges: 2->3",)


def test_more_missing_annotations_in_same_signal_fails() -> None:
    accepted, candidate = _snapshots()
    for model, positions in [(accepted, ["x"]), (candidate, ["x", "return"])]:
        model["typing_signals"] = [
            _record(
                "typing",
                kind="missing_cross_package_annotation",
                data={
                    "owner": "a.f",
                    "signal": "missing_cross_package_annotation",
                    "positions": positions,
                },
            )
        ]
    delta = _delta(accepted, candidate)
    assert delta["dimensions"]["typing_signals"]["added"] == []
    assert _evaluate(delta).failures == ("regression check failed in typing_positions: 1->2",)


@pytest.mark.parametrize(
    "dimension", ["violations", "cycles", "private_crossings", "typing_signals", "unknowns"]
)
def test_equal_scalars_do_not_allow_fingerprint_replacement(dimension: str) -> None:
    delta = _delta_payload()
    delta["semantic_changes"].append(
        {
            "dimension": dimension,
            "change": "added",
            "fingerprint": "replacement",
            "before_count": 0,
            "after_count": 1,
            "before": None,
            "after": _projection("new", {"level": "module", "members": ["new_a", "new_b"]}),
        }
    )
    delta["semantic_changes"].append(
        {
            "dimension": dimension,
            "change": "removed",
            "fingerprint": "previous",
            "before_count": 1,
            "after_count": 0,
            "after": None,
            "before": _projection("old", {"level": "module", "members": ["old_a", "old_b"]}),
        }
    )
    assert evaluate_expectation(
        _typed_delta(delta), parse_expectation(_expectation_payload())
    ).failures == (f"guardrail added {dimension} fingerprint replacement",)


@pytest.mark.parametrize(
    "scalar",
    [
        "violations",
        "cycle_edges",
        "private_crossings",
        "typing_positions",
        "calls_unresolved",
        "coverage_failures",
    ],
)
def test_missing_scalar_is_unverifiable(scalar: str) -> None:
    delta = _delta_payload()
    del delta["ratchets"]["head"]["scalars"][scalar]
    with pytest.raises(RatchetError, match="scalars must contain exactly"):
        evaluate_expectation(_typed_delta(delta), parse_expectation(_expectation_payload()))


def test_legacy_measurements_default_new_private_access_scalar_to_zero() -> None:
    measurements = parse_measurements(_measurements(), "legacy")
    assert measurements.scalars.untyped_private_accesses == 0


@pytest.mark.parametrize("older", [{}, {"untyped_private_accesses": 0}])
def test_measurements_written_before_unknown_positions_read_it_as_zero(
    older: dict[str, int],
) -> None:
    """AD-92: a lock or delta written before the scalar existed stays readable, both shapes."""
    payload = _measurements()
    payload["scalars"] = {**payload["scalars"], **older}
    assert parse_measurements(payload, "legacy").scalars.unknown_positions == 0


def test_unknown_positions_round_trips_through_the_delta_codec() -> None:
    accepted, candidate = _snapshots()
    candidate["unknowns"] = [
        _record("NOVEL", kind="dart_import_symbol_limit", evidence_class="UNKNOWN")
    ]
    head = _delta(accepted, candidate)["ratchets"]["head"]
    assert head["scalars"]["unknown_positions"] == 1
    assert parse_measurements(head, "head").scalars.unknown_positions == 1


@pytest.mark.parametrize("invalid", [None, True, -1, 1.0, "1"])
def test_invalid_integer_measurement_is_unverifiable(invalid: object) -> None:
    accepted = _measurements()
    candidate = _measurements()
    candidate["scalars"]["calls_unresolved"] = invalid
    with pytest.raises(RatchetError, match="non-negative integer"):
        compare_ratchets(
            parse_measurements(accepted, "accepted"), parse_measurements(candidate, "candidate")
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_calls",
        "inconsistent_calls",
        "missing_files",
        "incomplete_files",
        "failures",
        "missing_cycle_edges",
        "missing_typing_positions",
        "invalid_import",
    ],
)
def test_invalid_source_measurements_remain_unknown(mutation: str) -> None:
    accepted, candidate = _snapshots()
    if mutation == "missing_calls":
        del candidate["coverage"]["calls_analyzed"]
    elif mutation == "inconsistent_calls":
        candidate["coverage"]["calls_unresolved"] = 1
    elif mutation == "missing_files":
        del candidate["coverage"]["files_discovered"]
    elif mutation == "incomplete_files":
        candidate["coverage"]["files_parsed"] = 0
    elif mutation == "failures":
        candidate["coverage"]["failures"] = [_record("failure", kind="parse_failure")]
    elif mutation == "missing_cycle_edges":
        candidate["cycles"] = [
            _record("cycle", kind="module_scc", data={"level": "module", "members": ["a", "b"]})
        ]
    elif mutation == "missing_typing_positions":
        candidate["typing_signals"] = [_record("typing", kind="missing_cross_package_annotation")]
    else:
        candidate["imports"] = [_record("import", kind="import", data={"symbol": "_x"})]
    if mutation in {"missing_calls", "missing_files"}:
        with pytest.raises(ValueError, match="coverage fields mismatch"):
            _delta(accepted, candidate)
        return
    delta = _delta(accepted, candidate)
    assert delta["ratchets"]["status"] == "UNKNOWN"
    with pytest.raises(ExpectationError, match="coverage status must be PASS"):
        _evaluate(delta)


@pytest.mark.parametrize("change", ["scope", "schema", "analyzer"])
def test_ratchets_require_same_measurement_profile(change: str) -> None:
    accepted, candidate = _snapshots()
    payload = _expectation_payload()
    valid_delta = _delta(accepted, candidate)
    for key in ("checker_digest", "analyzer_digest", "contract_digest", "baseline_digest"):
        payload[key] = valid_delta["provenance"][key]
    if change == "scope":
        candidate["source"]["scope"] = ["another/**/*.py"]
    elif change == "schema":
        candidate["schema_version"] = "next"
    else:
        candidate["analyzer"]["code_digest"] = "e" * 64
    delta = _delta(accepted, candidate)
    assert delta["ratchets"]["status"] == "UNKNOWN"
    with pytest.raises(ExpectationError):
        evaluate_expectation(_typed_delta(delta), parse_expectation(payload))


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_accepted",
        "missing_ratchets",
        "invalid_total",
        "u_exceeds_t",
        "fake_na",
        "failed_scan",
    ],
)
def test_invalid_delta_measurements_are_unverifiable(mutation: str) -> None:
    delta = _delta_payload()
    candidate = delta["ratchets"]["head"]
    if mutation == "missing_accepted":
        del delta["ratchets"]["baseline"]
    elif mutation == "missing_ratchets":
        del delta["ratchets"]
    elif mutation == "invalid_total":
        candidate["calls_total"] = True
    elif mutation == "u_exceeds_t":
        candidate["scalars"]["calls_unresolved"] = 1
    elif mutation == "fake_na":
        candidate["resolution"] = "measured"
    else:
        candidate["scalars"]["coverage_failures"] = 1
    with pytest.raises(ValueError):
        evaluate_expectation(_typed_delta(delta), parse_expectation(_expectation_payload()))
