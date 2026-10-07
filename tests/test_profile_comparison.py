# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Historical graph evidence cannot grant unavailable profile measurements."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_delta import _evidence, _model, _record
from test_html_report import FAILED_CHECK

from archkeel.check.delta import build_architecture_delta
from archkeel.check.expectation import (
    EXPECTATION_SCHEMA_VERSION,
    GUARDRAIL_KEYS,
    ExpectationError,
    evaluate_expectation,
    parse_expectation,
)
from archkeel.ir.codec import (
    canonical_json_bytes,
    delta_payload,
    parse_delta,
    parse_observation,
)
from archkeel.ir.digest import package_digest
from archkeel.ir.model import DiagnosticError
from archkeel.ir.profiles import PROFILES
from archkeel.render.html import render_check_html

LANGUAGES = ("python", "dart", "typescript")
UNAVAILABLE = ("api_crossings", "private_crossings", "typing_signals")


def _observation(language, *, head="1" * 40, **sections):
    raw = _model(git_head=head)
    raw.update(sections)
    profile = PROFILES[language]
    raw["analyzer"]["name"] = profile.analyzer
    raw["runtime"] = {"name": "python", "version": "3.11.12", "required": ">=3.11"}
    raw["producer"] = {"name": profile.analyzer, "version": "0.3.0", "code_digest": "c" * 64}
    for name in profile.absent_sections:
        raw[name] = None
    for name in profile.optional_sections:
        raw[name] = None
    if profile.unmeasured:
        for name in (
            "calls_analyzed",
            "calls_resolved",
            "calls_partially_resolved",
            "calls_unresolved",
            "call_resolution_percent",
        ):
            raw["coverage"][name] = None
    return parse_observation(raw)


def _delta(language, *, baseline=None, head=None):
    return build_architecture_delta(
        baseline or _observation(language),
        head or _observation(language, head="2" * 40),
        baseline_digest="b" * 64,
        head_digest="d" * 64,
        checker_digest=package_digest(),
    )


def _expectation(delta, selected=()):
    return parse_expectation(
        {
            "schema_version": EXPECTATION_SCHEMA_VERSION,
            "evidence_class": "HYPOTHESIS",
            "checker_digest": delta.provenance.checker_digest,
            "accepted_digest": "e" * 64,
            "baseline_commit": "3" * 40,
            "analyzer_digest": delta.provenance.analyzer_digest,
            "contract_digest": delta.provenance.contract_digest,
            "baseline_digest": delta.provenance.baseline_digest,
            "selected_changes": list(selected),
            "guardrails": dict.fromkeys(GUARDRAIL_KEYS, True),
        }
    )


def _selection(change):
    return {
        "dimension": change.dimension,
        "change": change.change,
        "fingerprint": change.fingerprint,
        "before_count": change.before_count,
        "after_count": change.after_count,
    }


@pytest.mark.parametrize("language", LANGUAGES)
def test_complete_profile_compares_changed_source_without_architecture_change(language):
    delta = _delta(language)
    assert delta.baseline.source_digest != delta.head.source_digest
    assert delta.coverage.status == "PASS"
    assert not evaluate_expectation(delta, _expectation(delta)).failures
    assert delta.schema_version == "2.0.0"
    if language != "python":
        assert set(delta.coverage.unknown_dimensions) == set(UNAVAILABLE)
        for name in UNAVAILABLE:
            dimension = next(item for item in delta.dimensions if item.name == name)
            assert dimension.status == "UNKNOWN"
            assert dimension.before_count is None and dimension.after_count is None
            assert any(
                item.dimension == name and delta.analyzer.name in item.reason
                for item in delta.unknowns
            )
        assert delta.ratchets.head.scalars.private_crossings is None
        assert delta.ratchets.head.scalars.typing_positions is None


@pytest.mark.parametrize("language", LANGUAGES)
def test_selected_edge_passes_but_undeclared_edge_fails(language):
    edge = _record(
        "EDGE",
        kind="module_dependency",
        data={"level": "module", "source": "app.a", "target": "app.b"},
    )
    delta = _delta(language, head=_observation(language, head="2" * 40, dependency_edges=[edge]))
    (change,) = delta.semantic_changes
    assert not evaluate_expectation(delta, _expectation(delta, [_selection(change)])).failures
    assert evaluate_expectation(delta, _expectation(delta)).failures


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("section", ["violations", "cycles", "unknowns"])
def test_profile_scope_keeps_real_regressions(language, section):
    record = _record(
        "NEW",
        kind="new_evidence",
        evidence_class="UNKNOWN"
        if section == "unknowns"
        else "VIOLATION"
        if section == "violations"
        else "FACT",
        data={
            "level": "module",
            "members": ["a", "b"],
            "internal_edges": ["a->b", "b->a"],
            "undecided": 1,
        },
    )
    delta = _delta(language, head=_observation(language, head="2" * 40, **{section: [record]}))
    assert evaluate_expectation(delta, _expectation(delta)).failures
    assert evaluate_expectation(
        delta, _expectation(delta, [_selection(item) for item in delta.semantic_changes])
    ).failures


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("selected", [False, True])
def test_changed_unknown_fingerprint_cannot_pass_equal_position_count(language, selected):
    old = _record(
        "OLD",
        kind="blind_spot",
        evidence_class="UNKNOWN",
        data={"reason": "before", "undecided": 1},
    )
    new = copy.deepcopy(old)
    new["data"]["reason"] = "after"
    delta = _delta(
        language,
        baseline=_observation(language, unknowns=[old]),
        head=_observation(language, head="2" * 40, unknowns=[new]),
    )
    assert (
        delta.ratchets.baseline.scalars.unknown_positions
        == delta.ratchets.head.scalars.unknown_positions
        == 1
    )
    (change,) = delta.semantic_changes
    assert change.dimension == "unknowns" and change.change == "changed"
    expectation = _expectation(delta, [_selection(change)] if selected else ())
    assert evaluate_expectation(delta, expectation).failures


@pytest.mark.parametrize("language", LANGUAGES)
def test_selected_unknown_relocation_preserves_existing_unknown(language):
    old = _record(
        "OLD",
        kind="blind_spot",
        evidence_class="UNKNOWN",
        evidence_id="EVD-old",
        data={"reason": "unresolved", "undecided": 1},
    )
    new = copy.deepcopy(old)
    new.update(id="NEW", evidence_ids=["EVD-new"])
    delta = _delta(
        language,
        baseline=_observation(language, unknowns=[old], evidence=[_evidence("EVD-old", 10)]),
        head=_observation(
            language, head="2" * 40, unknowns=[new], evidence=[_evidence("EVD-new", 30)]
        ),
    )
    (change,) = delta.semantic_changes
    assert change.dimension == "unknowns" and change.change == "relocated"
    assert delta.ratchets.baseline.scalars.unknown_positions == 1
    assert delta.ratchets.head.scalars.unknown_positions == 1
    assert not evaluate_expectation(delta, _expectation(delta, [_selection(change)])).failures


@pytest.mark.parametrize("language", ["dart", "typescript"])
@pytest.mark.parametrize("name", UNAVAILABLE)
@pytest.mark.parametrize("forged", [False, True])
def test_unavailable_selection_rejected_even_with_forged_supported_label(language, name, forged):
    delta = _delta(language)
    if forged:
        delta = replace(
            delta,
            dimensions=tuple(
                replace(item, status="SUPPORTED", before_count=0, after_count=0)
                if item.name == name
                else item
                for item in delta.dimensions
            ),
        )
    selected = {
        "dimension": name,
        "change": "added",
        "fingerprint": "fake",
        "before_count": 0,
        "after_count": 1,
    }
    with pytest.raises(ExpectationError):
        evaluate_expectation(delta, _expectation(delta, [selected]))


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize(
    "corruption",
    [
        "missing",
        "unknown",
        "lists",
        "snapshot",
        "unavailable_supported",
        "change_unavailable",
        "header",
        "receipt",
        "count",
        "duplicate",
    ],
)
def test_supplied_delta_cannot_borrow_capabilities_or_invent_coverage(language, corruption):
    delta = _delta(language)
    if corruption == "missing":
        delta = replace(
            delta,
            dimensions=tuple(item for item in delta.dimensions if item.name != "dependency_edges"),
        )
    elif corruption == "unknown":
        delta = replace(
            delta,
            dimensions=tuple(
                replace(item, status="UNKNOWN") if item.name == "dependency_edges" else item
                for item in delta.dimensions
            ),
        )
    elif corruption == "lists":
        delta = replace(delta, coverage=replace(delta.coverage, supported_dimensions=()))
    elif corruption == "snapshot":
        delta = replace(delta, baseline=replace(delta.baseline, coverage_status="FAIL"))
    elif corruption == "unavailable_supported":
        if language == "python":
            return
        delta = replace(
            delta,
            dimensions=tuple(
                replace(item, status="SUPPORTED", before_count=0, after_count=0)
                if item.name == "private_crossings"
                else item
                for item in delta.dimensions
            ),
        )
        delta = replace(
            delta,
            coverage=replace(
                delta.coverage,
                supported_dimensions=delta.coverage.supported_dimensions + ("private_crossings",),
                unknown_dimensions=tuple(
                    name
                    for name in delta.coverage.unknown_dimensions
                    if name != "private_crossings"
                ),
            ),
        )
    elif corruption == "header":
        delta = replace(delta, analyzer=replace(delta.analyzer, code_digest="d" * 64))
    elif corruption == "receipt":
        from archkeel.ir.model import DeltaUnknown

        delta = replace(
            delta,
            unknowns=()
            if language != "python"
            else (DeltaUnknown("forged", "violations", "incomplete"),),
        )
    elif corruption == "count":
        delta = replace(
            delta,
            dimensions=tuple(
                replace(item, before_count=None) if item.name == "coverage" else item
                for item in delta.dimensions
            ),
        )
    elif corruption == "duplicate":
        delta = replace(delta, dimensions=delta.dimensions + (delta.dimensions[0],))
    else:
        if language == "python":
            return
        from archkeel.ir.model import SemanticChange

        delta = replace(
            delta,
            semantic_changes=(
                SemanticChange("private_crossings", "added", "forged", 0, 1, None, None),
            ),
        )
    with pytest.raises(ExpectationError):
        evaluate_expectation(delta, _expectation(delta))


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("section", ["violations", "dependency_edges", "cycles", "unknowns"])
def test_missing_supported_section_never_produces_complete_comparison(language, section):
    head = _observation(language, head="2" * 40)
    head = replace(head, sections=tuple(item for item in head.sections if item.name != section))
    delta = _delta(language, head=head)
    assert delta.coverage.status == "FAIL"
    with pytest.raises(ExpectationError):
        evaluate_expectation(delta, _expectation(delta))


def test_current_nullable_counts_roundtrip_and_legacy_unavailable_counts_never_decide():
    delta = _delta("dart")
    raw = delta_payload(delta)
    assert delta_payload(parse_delta(raw)) == raw
    assert delta_payload(parse_delta(json.loads(canonical_json_bytes(raw)))) == raw
    legacy = copy.deepcopy(raw)
    legacy["schema_version"] = "1.3.0"
    for name in UNAVAILABLE:
        legacy["dimensions"][name].update(before_count=0, after_count=0)
    for side in ("baseline", "head"):
        legacy["ratchets"][side]["calls_total"] = 0
    assert parse_delta(legacy).schema_version == "1.3.0"
    with pytest.raises(ExpectationError):
        evaluate_expectation(parse_delta(legacy), _expectation(delta))
    page = render_check_html(
        replace(FAILED_CHECK, delta=delta), repository="app", result_href="result.json"
    ).decode()
    assert "Unavailable dimensions" in page
    assert "api_crossings" in page and "unavailable" in page
    assert "None → None" not in page


@pytest.mark.parametrize("language", ["dart", "typescript"])
def test_real_non_python_snapshot_null_alias_roundtrips(language):
    before = replace(_observation(language), python_version=None)
    after = replace(_observation(language, head="2" * 40), python_version=None)
    raw = delta_payload(_delta(language, baseline=before, head=after))
    assert raw["baseline"]["python_version"] is None
    assert delta_payload(parse_delta(raw)) == raw
    assert delta_payload(parse_delta(json.loads(canonical_json_bytes(raw)))) == raw


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize(
    "field", ["profile", "analyzer", "producer", "runtime", "scope", "contract"]
)
def test_profile_scope_preserves_comparability_gates(language, field):
    before = _observation(language)
    after = _observation(language, head="2" * 40)
    if field == "profile":
        after = replace(
            after,
            analyzer=replace(
                after.analyzer, name=PROFILES["dart" if language == "python" else "python"].analyzer
            ),
        )
    elif field == "analyzer":
        after = replace(after, analyzer=replace(after.analyzer, code_digest="d" * 64))
    elif field == "producer":
        after = replace(after, producer=replace(after.producer, code_digest="d" * 64))
    elif field == "runtime":
        after = (
            replace(after, python_version="3.12.10")
            if language == "python"
            else replace(after, runtime=replace(after.runtime, version="3.12.10"))
        )
    elif field == "scope":
        after = replace(after, source=replace(after.source, scope=("elsewhere/**/*.py",)))
    else:
        after = replace(after, contract=replace(after.contract, digest="d" * 64))
    try:
        delta = _delta(language, baseline=before, head=after)
    except DiagnosticError:
        return
    assert delta.coverage.status == "FAIL"
    with pytest.raises(ExpectationError):
        evaluate_expectation(delta, _expectation(delta))


@pytest.mark.parametrize("language", LANGUAGES)
def test_emitted_delta_schema_accepts_nullable_unknowns_only(language):
    from referencing import Registry, Resource

    folder = Path(__file__).parents[1] / "schema"
    registry = Registry()
    for name in (
        "architecture-ir-common",
        "architecture-ir-python-decoded",
        "architecture-ir-decoded",
    ):
        resource = json.loads((folder / (name + ".schema.json")).read_bytes())
        registry = registry.with_resource(resource["$id"], Resource.from_contents(resource))
    schema = json.loads((folder / "command-result.schema.json").read_bytes())
    validator = Draft202012Validator(
        {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": "#/$defs/delta"},
        registry=registry,
    )
    raw = delta_payload(_delta(language))
    assert not list(validator.iter_errors(raw))
    if language != "python":
        legacy = copy.deepcopy(raw)
        legacy["schema_version"] = "1.3.0"
        assert list(validator.iter_errors(legacy))
        with pytest.raises(ValueError):
            parse_delta(legacy)
    broken = copy.deepcopy(raw)
    broken["dimensions"]["dependency_edges"]["before_count"] = None
    assert list(validator.iter_errors(broken))
    with pytest.raises(ValueError):
        parse_delta(broken)


def test_old_python_delta_retains_complete_measurement_policy():
    delta = _delta("python")
    raw = delta_payload(delta)
    raw["schema_version"] = "1.3.0"
    legacy = parse_delta(raw)
    assert not evaluate_expectation(legacy, _expectation(legacy)).failures
    raw["schema_version"] = "1.5.0"
    with pytest.raises(ValueError):
        parse_delta(raw)


@pytest.mark.parametrize("section", ["imports", "typing_signals"])
def test_missing_python_only_measurement_still_fails(section):
    head = _observation("python", head="2" * 40)
    head = replace(head, sections=tuple(item for item in head.sections if item.name != section))
    assert _delta("python", head=head).coverage.status == "FAIL"


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("field", ["analyzer", "contract"])
@pytest.mark.parametrize("value", ["", " ", "unknown", "UNKNOWN", " unknown "])
def test_equal_missing_code_or_contract_identity_never_grants_coverage(language, field, value):
    before = _observation(language)
    after = _observation(language, head="2" * 40)
    if field == "analyzer":
        before = replace(before, analyzer=replace(before.analyzer, code_digest=value))
        after = replace(after, analyzer=replace(after.analyzer, code_digest=value))
    else:
        before = replace(before, contract=replace(before.contract, digest=value))
        after = replace(after, contract=replace(after.contract, digest=value))
    if language == "python":
        before = replace(before, runtime=None, producer=None)
        after = replace(after, runtime=None, producer=None)
    delta = _delta(language, baseline=before, head=after)
    assert delta.coverage.status == "FAIL"
    assert delta.ratchets.status == "UNKNOWN"
