# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Native recorded facts select local Target findings without collecting source."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_result_schema import validator as validator
from test_source_evaluation import _facts

from archkeel.check.observation import assemble_observation
from archkeel.check.observe import observation_diagnostics
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report, run_saved_report
from archkeel.check.uml import assemble_uml
from archkeel.check.uml_evaluation import evaluate_uml
from archkeel.cli import main
from archkeel.ir.baseline import observed_violations
from archkeel.ir.codec import (
    baseline_bytes,
    canonical_report_bytes,
    decode_canonical_model,
    result_bytes,
)
from archkeel.ir.facts import EvidenceClass, FactSection, Record, RecordData
from archkeel.ir.model import ObservationResult


def _component(identifier, label, namespace, inside=None):
    value = {
        "id": identifier,
        "label": label,
        "role": "component",
        "namespace": namespace,
        "packages": [namespace],
        "responsibilities": ["Own this boundary."],
        "forbidden_responsibilities": [],
        "provenance": ["docs/target.md"],
    }
    if inside is not None:
        value["inside"] = inside
    return value


@pytest.fixture
def recorded_native(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Recorded query must not collect or start a process")

    monkeypatch.setattr("archkeel.analyzer.process.ProcessCollector.collect", forbidden)
    monkeypatch.setattr("subprocess.run", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    root = tmp_path / "target"
    root.mkdir()
    (root / "docs").mkdir()
    (root / "docs/target.md").write_text("Own the declared boundary.\n")
    contract = {
        "schema_version": "2.2.0",
        "components": [
            _component("app", "app", "project.app", "app.json"),
            _component("store", "store", "project.store", "store.json"),
            _component("empty", "empty", "project.empty"),
        ],
        "rules": [
            {
                "id": "LAYOUT",
                "kind": "root_layout",
                "root": "project",
                "allowed_children": ["project.store"],
                "rationale": "Only the declared child belongs here.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            },
            {
                "id": "NO-STORE",
                "kind": "forbidden_dependency",
                "source": "project.app",
                "target": "project.store",
                "include_type_checking": True,
                "rationale": "Keep this dependency out of the boundary.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            },
        ],
    }
    (root / "contract.json").write_text(json.dumps(contract))
    for owner in ("app", "store"):
        (root / f"{owner}.json").write_text(
            json.dumps(
                {
                    "schema_version": "2.2.0",
                    "components": [_component("UNIT", "app", f"project.{owner}")],
                    "rules": [],
                }
            )
        )
    facts = _facts()

    def recorded(*, partial=False):
        source = facts
        if partial:
            gap = Record(
                "GAP-partial",
                EvidenceClass.UNKNOWN,
                "coverage",
                "partial_scope",
                "Recorded source selection is partial",
                (),
                (),
                (),
                (),
                (),
                RecordData((("file", "src/app.py"),)),
            )
            source = replace(
                facts,
                coverage=replace(facts.coverage, full_scope=False, gaps=(gap,)),
                sections=tuple(
                    FactSection("unknowns", (gap,)) if section.name == "unknowns" else section
                    for section in facts.sections
                ),
            )
        model, _ = assemble_observation(
            source, contract_root=root, contract_path=root / "contract.json", namespace="project"
        )
        observed = evaluate_uml(
            assemble_uml(
                ObservationResult(
                    model, model.coverage, observation_diagnostics(model, None, "python")
                ),
                root,
                "contract.json",
            )
        )
        assert observed.observation is not None
        assert bool(observed.diagnostics) is partial
        model = observed.observation
        observed = replace(observed, diagnostics=observation_diagnostics(model, None, "python"))
        packet = tmp_path / ("partial.json" if partial else "architecture.json")
        packet.write_bytes(canonical_report_bytes(model))
        return root, observed, packet

    return recorded


@pytest.mark.parametrize("selector", ["app", "app:UNIT", "app:app"])
def test_native_violation_filter_includes_owned_standalone_and_descendant_findings(
    recorded_native, selector
):
    _, observed, packet = recorded_native()
    layout = next(
        row for row in observed.observation.records("violations") if row.kind == "root_layout"
    )
    assert layout.evidence_class == EvidenceClass.VIOLATION
    assert layout.data.get("source_module") is None and layout.data.get("target_module") is None
    result = run_saved_report(packet, only_violations=True, component=selector)
    assert result.exit_code == 0, result.diagnostics
    assert layout.id in {row.record.id for row in result.filtered_violations}
    assert {row.record.kind for row in result.filtered_violations} == {
        "root_layout",
        "forbidden_dependency",
    }


def test_top_level_label_takes_precedence_over_identical_nested_labels(recorded_native):
    _, _, packet = recorded_native()
    native = run_saved_report(packet, only_architecture=True, component="app")
    assert native.exit_code == 2 and native.diagnostics[0].kind == "filter_unknown"
    explicit = run_saved_report(packet, only_violations=True, component="app")
    assert explicit.exit_code == 0 and len(explicit.filtered_violations) == 2
    legacy = run_saved_report(packet, component="app")
    assert legacy.exit_code == 0
    assert [row.record.kind for row in legacy.filtered_violations] == ["forbidden_dependency"]


@pytest.mark.parametrize("selector", ["store", "store:UNIT", "store:app"])
def test_native_component_retains_crossing_target_findings(recorded_native, selector):
    _, _, packet = recorded_native()
    result = run_saved_report(packet, only_violations=True, component=selector)
    assert result.exit_code == 0, result.diagnostics
    assert [row.record.kind for row in result.filtered_violations] == ["forbidden_dependency"]


def test_calls_keep_the_existing_top_level_label_selector(recorded_native):
    _, _, packet = recorded_native()
    calls = run_saved_report(packet, only_calls=True, component="app")
    assert calls.exit_code == 0 and calls.filtered_calls == ()
    nested = run_saved_report(packet, only_calls=True, component="app:UNIT")
    assert nested.exit_code == 2 and nested.diagnostics[0].kind == "filter_unknown"


@pytest.mark.parametrize(
    "rule,kind", [("LAYOUT", "root_layout"), ("NO-STORE", "forbidden_dependency")]
)
def test_native_component_filter_intersects_existing_rule_facet(recorded_native, rule, kind):
    _, _, packet = recorded_native()
    full = run_saved_report(packet, only_violations=True)
    selected = run_saved_report(packet, only_violations=True, component="app:UNIT", rule=rule)
    assert selected.exit_code == 0, selected.diagnostics
    assert [row.record.kind for row in selected.filtered_violations] == [kind]
    assert (
        selected.coverage,
        selected.observation_complete,
        selected.declared_rules,
        selected.violations_by_rule,
        selected.violations_by_component_pair,
    ) == (
        full.coverage,
        full.observation_complete,
        full.declared_rules,
        full.violations_by_rule,
        full.violations_by_component_pair,
    )
    assert selected.filtered_violations[0] in full.filtered_violations


@pytest.mark.parametrize("selector", ["empty"])
def test_native_empty_component_keeps_global_failure(recorded_native, selector):
    _, _, packet = recorded_native()
    result = run_saved_report(packet, only_violations=True, component=selector)
    assert result.exit_code == 0 and result.filtered_violations == ()
    assert result.declared_rules == "FAIL"


@pytest.mark.parametrize("facet", [{"component": "missing"}, {"rule": "MISSING"}])
def test_native_violation_filter_rejects_unknown_selectors(recorded_native, facet):
    _, _, packet = recorded_native()
    result = run_saved_report(packet, only_violations=True, **facet)
    assert result.exit_code == 2 and result.diagnostics[0].kind == "filter_unknown"


@pytest.mark.parametrize("partial", [False, True])
def test_recorded_native_live_and_saved_filters_have_exact_parity(
    recorded_native, monkeypatch, partial
):
    root, observed, packet = recorded_native(partial=partial)
    monkeypatch.setattr(
        "archkeel.check.report.observe_repository", lambda *args, **kwargs: observed
    )
    config = ScanConfig(("src",), "project", "contract.json", "recorded-native")
    live, canonical = run_report(
        root,
        config=config,
        analyzer=lambda *args, **kwargs: observed,
        only_violations=True,
        component="app:UNIT",
        rule="LAYOUT",
    )
    saved = run_saved_report(packet, only_violations=True, component="app:UNIT", rule="LAYOUT")
    assert result_bytes(saved) == result_bytes(live)
    assert canonical == packet.read_bytes()
    assert saved.exit_code == (2 if partial else 0)
    assert [row.record.kind for row in saved.filtered_violations] == ["root_layout"]
    if partial:
        assert saved.observation_complete == "UNKNOWN"
        assert saved.architecture_projection.unknowns


@pytest.mark.parametrize("collision", ["label", "id-scope"])
def test_native_violation_selector_rejects_ambiguity(recorded_native, collision):
    root, _, packet = recorded_native()
    if collision == "label":
        for owner in ("app", "store"):
            path = root / f"{owner}.json"
            contract = json.loads(path.read_text())
            contract["components"][0]["label"] = "shared"
            path.write_text(json.dumps(contract))
        selector = "shared"
    else:
        path = root / "contract.json"
        contract = json.loads(path.read_text())
        contract["components"].append(_component("app:app", "scope-collision", "project.absent"))
        path.write_text(json.dumps(contract))
        selector = "app:app"
    _, _, packet = recorded_native()
    result = run_saved_report(packet, only_violations=True, component=selector)
    assert result.exit_code == 2 and result.diagnostics[0].kind == "filter_unknown"
    assert result.filtered_violations is None


def test_malformed_saved_violation_query_fails_closed(recorded_native):
    _, _, packet = recorded_native()
    packet.write_bytes(b"{")
    result = run_saved_report(packet, only_violations=True, component="app:UNIT", rule="LAYOUT")
    assert result.exit_code == 2 and result.diagnostics[0].kind == "parse_error"
    assert result.filtered_violations is None and result.observation_complete == "UNKNOWN"


def test_saved_cli_uses_the_native_component_and_existing_rule_intersection(
    recorded_native, capsys
):
    _, _, packet = recorded_native()
    expected = run_saved_report(packet, only_violations=True, component="app:app", rule="LAYOUT")
    arguments = [
        "report",
        "--input",
        str(packet),
        "--only",
        "violations",
        "--component",
        "app:app",
        "--rule",
        "LAYOUT",
        "--json",
    ]
    outputs = []
    for _ in range(2):
        assert main(arguments) == 0
        outputs.append(capsys.readouterr().out.encode())
    assert outputs == [result_bytes(expected), result_bytes(expected)]
    payload = json.loads(outputs[0])
    assert [item["kind"] for item in payload["filtered_violations"]] == ["root_layout"]
    assert payload["filtered_violations"][0]["locations"]


@pytest.mark.parametrize("missing", ["target", "source"])
def test_saved_native_filter_requires_target_and_source_facts(recorded_native, missing):
    _, _, packet = recorded_native()
    raw = decode_canonical_model(json.loads(packet.read_bytes()))
    if missing == "target":
        raw["declarations"] = [
            item
            for item in raw["declarations"]
            if item["kind"] not in {"architecture_target", "uml_target"}
        ]
    else:
        raw["imports"] = None
    packet.write_text(json.dumps(raw))
    result = run_saved_report(packet, only_violations=True, component="app:UNIT")
    assert result.exit_code == 2 and result.observation_complete == "UNKNOWN"
    assert result.diagnostics and result.filtered_violations is None


@pytest.mark.parametrize("state", ["known", "new", "resolved"])
def test_compact_architecture_retains_exact_native_baseline_comparisons(
    recorded_native, monkeypatch, state, validator
):
    root, observed, _ = recorded_native()
    if state == "resolved":
        path = root / "contract.json"
        original = path.read_bytes()
        contract = json.loads(original)
        contract["rules"][0]["allowed_children"] = []
        path.write_text(json.dumps(contract))
        _, before, _ = recorded_native()
        path.write_bytes(original)
        _, observed, _ = recorded_native()
        known = observed_violations(before.observation)
    else:
        known = observed_violations(observed.observation) if state == "known" else ()
    baseline = root / "baseline.json"
    baseline.write_bytes(baseline_bytes(known))
    before_bytes = baseline.read_bytes()
    monkeypatch.setattr(
        "archkeel.check.report.observe_repository", lambda *args, **kwargs: observed
    )
    config = ScanConfig(("src",), "project", "contract.json", "recorded-native")
    ordinary, full_packet = run_report(
        root,
        config=config,
        analyzer=lambda *args, **kwargs: observed,
        baseline=Path("baseline.json"),
    )
    focused, selected_packet = run_report(
        root,
        config=config,
        analyzer=lambda *args, **kwargs: observed,
        baseline=Path("baseline.json"),
        only_architecture=True,
        component="app:UNIT",
    )
    assert ordinary.exit_code == focused.exit_code == 0
    assert ordinary.declared_rules == focused.declared_rules == "FAIL"
    assert full_packet == selected_packet and baseline.read_bytes() == before_bytes
    ordinary_payload = json.loads(result_bytes(ordinary))
    focused_payload = json.loads(result_bytes(focused))
    assert {item["status"] for item in ordinary_payload["baseline_comparisons"]} == (
        {"known", "resolved"} if state == "resolved" else {state}
    )
    for field in ("baseline_path", "baseline_comparisons", "baseline_new", "baseline_resolved"):
        assert focused_payload.get(field) == ordinary_payload[field]
    if state == "new":
        assert sum(item["new_count"] for item in focused_payload["baseline_comparisons"]) == 2
    elif state == "resolved":
        assert sum(item["resolved_count"] for item in focused_payload["baseline_comparisons"]) == 1
    validator.validate(focused_payload)


def test_no_baseline_compact_envelope_omits_absent_fields_and_is_deterministic(recorded_native):
    _, _, packet = recorded_native()
    encoded = result_bytes(run_saved_report(packet, only_architecture=True))
    assert not any(key.startswith("baseline_") for key in json.loads(encoded))
    assert encoded == result_bytes(run_saved_report(packet, only_architecture=True))


def test_native_rule_component_intersection_can_be_measured_empty(recorded_native):
    _, _, packet = recorded_native()
    result = run_saved_report(packet, only_violations=True, component="store:UNIT", rule="LAYOUT")
    assert result.exit_code == 0 and result.filtered_violations == ()
    assert result.declared_rules == "FAIL" and result.violations_by_rule


def test_compact_baseline_preserves_measured_empty_and_explicit_zero_counts(
    recorded_native, validator
):
    _, _, packet = recorded_native()
    result = run_saved_report(packet, only_architecture=True)
    result = replace(
        result,
        baseline_path="baseline.json",
        baseline_comparisons=(),
        baseline_new=0,
        baseline_resolved=0,
    )
    payload = json.loads(result_bytes(result))
    assert payload["baseline_path"] == "baseline.json"
    assert payload["baseline_comparisons"] == []
    assert payload["baseline_new"] == payload["baseline_resolved"] == 0
    validator.validate(payload)


def test_partial_observation_does_not_invent_baseline_resolution(recorded_native, monkeypatch):
    root, complete, _ = recorded_native()
    baseline = root / "baseline.json"
    baseline.write_bytes(baseline_bytes(observed_violations(complete.observation)))
    _, observed, _ = recorded_native(partial=True)
    monkeypatch.setattr(
        "archkeel.check.report.observe_repository", lambda *args, **kwargs: observed
    )
    config = ScanConfig(("src",), "project", "contract.json", "recorded-native")
    ordinary, _ = run_report(
        root,
        config=config,
        analyzer=lambda *args, **kwargs: observed,
        baseline=Path("baseline.json"),
    )
    focused, _ = run_report(
        root,
        config=config,
        analyzer=lambda *args, **kwargs: observed,
        baseline=Path("baseline.json"),
        only_architecture=True,
    )
    assert ordinary.exit_code == focused.exit_code == 2
    assert ordinary.coverage == focused.coverage
    assert ordinary.observation_complete == focused.observation_complete == "UNKNOWN"
    for field in ("baseline_path", "baseline_comparisons", "baseline_new", "baseline_resolved"):
        assert json.loads(result_bytes(ordinary))[field] is None
        assert json.loads(result_bytes(focused)).get(field) is None
