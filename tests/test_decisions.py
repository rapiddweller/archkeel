# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-15: open_decisions derives undecided component pairs from one observation alone."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.validation import closed_world_diagnostics
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_contract, parse_observation
from archkeel.ir.decisions import (
    RuleUncertaintyCause,
    agent_decisions,
    dependency_rule_ids,
    open_decision_summary,
    open_decisions,
    rule_uncertainty_evidence,
    violation_counts,
)
from archkeel.ir.model import (
    AllowedDependencyRule,
    AnalyzerInfo,
    ContractInfo,
    Coverage,
    EvidenceClass,
    ForbiddenDependencyRule,
    Observation,
    Record,
    RecordData,
    Section,
    SourceInfo,
)
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_support import contract_rule_field, contract_without_rule

CONFIG = ScanConfig(("shop",), "shop", "architecture-contract.json", "0" * 64)
ROOT = Path(__file__).parents[1]

_COVERAGE = Coverage(
    status="PASS",
    files_discovered=0,
    files_read=0,
    files_parsed=0,
    calls_analyzed=0,
    calls_resolved=0,
    calls_partially_resolved=0,
    calls_unresolved=0,
    ast_coverage_percent=100.0,
    call_resolution_percent=100.0,
    failures=(),
)


def _module_edge(source: str, target: str, count: int) -> Record:
    return Record(
        id=f"EDGE-{source}-{target}",
        evidence_class=EvidenceClass.FACT,
        area="module_topology",
        kind="module_dependency",
        title=f"{source} -> {target}",
        subjects=(source, target),
        evidence_ids=(),
        rule_ids=(),
        fact_ids=(),
        provenance=(),
        data=RecordData(
            (("level", "module"), ("source", source), ("target", target), ("count", count))
        ),
    )


def _observation(edges: tuple[Record, ...], declarations: tuple[Record, ...] = ()) -> Observation:
    return Observation(
        schema_version="1.3.0",
        analyzer=AnalyzerInfo("archkeel-python-analyzer", "0.0.0", "0" * 16),
        source=SourceInfo("0" * 40, False, "0" * 16, ()),
        contract=ContractInfo("2.1.0", "0" * 16, "architecture-contract.json"),
        coverage=_COVERAGE,
        sections=(
            Section("declarations", declarations),
            Section("dependency_edges", edges),
        ),
        evidence=(),
    )


def _declaration(item_id: str, kind: str, data: tuple[tuple[str, object], ...]) -> Record:
    return Record(
        id=item_id,
        evidence_class=EvidenceClass.DECLARED_RULE,
        area="components",
        kind=kind,
        title=item_id,
        subjects=(),
        evidence_ids=(),
        rule_ids=(),
        fact_ids=(),
        provenance=(),
        data=RecordData(data),
    )


def test_rule_uncertainty_evidence_groups_only_rule_unknowns_and_ownership_blockers() -> None:
    def record(
        identity: str,
        evidence_class: EvidenceClass,
        kind: str,
        rule_ids: tuple[str, ...],
    ) -> Record:
        return Record(
            identity,
            evidence_class,
            "rules",
            kind,
            identity,
            (),
            (),
            rule_ids,
            (),
            (),
            RecordData(),
        )

    unknowns = (
        record("UNKNOWN-Z", EvidenceClass.UNKNOWN, "type_limit", ("RULE-B",)),
        record("UNKNOWN-A", EvidenceClass.UNKNOWN, "unsupported_rule", ("RULE-B", "RULE-A")),
        record("UNKNOWN-UNRELATED", EvidenceClass.UNKNOWN, "dynamic_limit", ()),
        record("FACT-ONLY", EvidenceClass.FACT, "scope_observation", ("RULE-A",)),
    )
    receipts = (
        record("EVALUATION", EvidenceClass.FACT, "rule_evaluation", ("RULE-A",)),
        record("OTHER-SCOPE", EvidenceClass.UNKNOWN, "scope_unknown", ("RULE-A",)),
        record(
            "BLOCKER-B",
            EvidenceClass.FACT,
            "rule_ownership_blocker",
            ("RULE-B", "RULE-A"),
        ),
    )
    observation = _observation(())
    observation = replace(
        observation,
        sections=(
            *observation.sections,
            Section("unknowns", unknowns),
            Section("scope_observations", receipts),
        ),
    )

    grouped = rule_uncertainty_evidence(observation)

    assert list(grouped) == ["RULE-A", "RULE-B"]
    assert [record.id for record in grouped["RULE-A"].evidence] == [
        "BLOCKER-B",
        "FACT-ONLY",
        "UNKNOWN-A",
    ]
    assert [record.id for record in grouped["RULE-B"].evidence] == [
        "BLOCKER-B",
        "UNKNOWN-A",
        "UNKNOWN-Z",
    ]
    assert grouped["RULE-A"].undecided_positions == 2
    assert [
        (action.cause, action.architect_actionable) for action in grouped["RULE-A"].actions
    ] == [
        (RuleUncertaintyCause.MISSING_OWNERSHIP, True),
        (RuleUncertaintyCause.UNKNOWN, None),
    ]
    reversed_observation = replace(
        observation,
        sections=tuple(
            replace(section, records=tuple(reversed(section.records)))
            if section.name in {"unknowns", "scope_observations"}
            else section
            for section in observation.sections
        ),
    )
    assert rule_uncertainty_evidence(reversed_observation) == grouped


def test_boundary_route_and_unclassified_record_causes() -> None:
    route = Record(
        "ROUTE",
        EvidenceClass.UNKNOWN,
        "type_architecture",
        "boundary_type_route",
        "route",
        (),
        (),
        ("RULE-ROUTE",),
        (),
        (),
        RecordData((("reason", "unresolved_reexport_route"),)),
    )
    forward = Record(
        "FORWARD",
        EvidenceClass.UNKNOWN,
        "type_architecture",
        "unclassified_future_gap",
        "unclassified",
        (),
        (),
        ("RULE-FORWARD",),
        (),
        (),
        RecordData((("undecided", 2),)),
    )
    observation = replace(
        _observation(()),
        sections=(
            *_observation(()).sections,
            Section("unknowns", (route, forward)),
        ),
    )

    result = rule_uncertainty_evidence(observation)

    assert result["RULE-ROUTE"].undecided_positions == 1
    assert [
        (action.cause, action.architect_actionable) for action in result["RULE-ROUTE"].actions
    ] == [
        (RuleUncertaintyCause.UNSUPPORTED_ANALYSIS, False),
    ]
    assert (
        result["RULE-ROUTE"]
        .actions[0]
        .next_action.startswith("A contract decision cannot resolve this analysis gap")
    )
    assert result["RULE-FORWARD"].undecided_positions == 2
    assert [
        (action.cause, action.architect_actionable) for action in result["RULE-FORWARD"].actions
    ] == [
        (RuleUncertaintyCause.UNKNOWN, None),
    ]

    unsupported_profile = replace(route, id="PROFILE", kind="rule-unsupported-by-profile")
    mixed = replace(observation, sections=(Section("unknowns", (route, unsupported_profile)),))
    actions = rule_uncertainty_evidence(mixed)["RULE-ROUTE"].actions
    assert len(actions) == 2
    assert [action.next_action for action in actions] == sorted(
        action.next_action for action in actions
    )


def test_rule_uncertainty_separates_missing_scope_intent_from_incomplete_execution() -> None:
    missing_intent = Record(
        "SCOPE-INTENT",
        EvidenceClass.UNKNOWN,
        "analysis_coverage",
        "inside_source_domain_incomplete",
        "scope mismatch",
        (),
        (),
        ("RULE-INTENT",),
        (),
        (),
        RecordData(),
    )
    incomplete = Record(
        "SCOPE-FAILED",
        EvidenceClass.UNKNOWN,
        "analysis_coverage",
        "component_scope_assignment_incomplete",
        "source scan failed",
        (),
        (),
        ("RULE-INCOMPLETE",),
        (),
        (),
        RecordData(),
    )
    base = _observation(())
    observation = replace(
        base, sections=(*base.sections, Section("unknowns", (missing_intent, incomplete)))
    )

    result = rule_uncertainty_evidence(observation)

    assert [
        (action.cause, action.architect_actionable) for action in result["RULE-INTENT"].actions
    ] == [
        (RuleUncertaintyCause.MISSING_INTENT, True),
    ]
    assert [
        (action.cause, action.architect_actionable) for action in result["RULE-INCOMPLETE"].actions
    ] == [
        (RuleUncertaintyCause.INCOMPLETE_EXECUTION, False),
    ]

    failed_scope = replace(
        observation,
        coverage=replace(observation.coverage, status="FAIL", failures=(missing_intent,)),
    )
    failed_result = rule_uncertainty_evidence(failed_scope)["RULE-INTENT"]
    assert failed_result.undecided_positions == 0
    assert failed_result.evidence == (missing_intent,)
    assert {action.cause for action in failed_result.actions} == {
        RuleUncertaintyCause.MISSING_INTENT,
        RuleUncertaintyCause.INCOMPLETE_EXECUTION,
    }


@pytest.mark.parametrize(
    "contract_path",
    [
        ROOT / "architecture-contract.json",
        ROOT / "fixtures/F-architecture/architecture-contract.json",
    ],
)
def test_component_level_dependency_rule_ids_match_dependency_rule_ids(
    contract_path: Path,
) -> None:
    """AD-15: `dependency_rule_ids` is the only owner of the `DEP-*` id scheme."""
    contract = parse_contract(decode_json(contract_path.read_bytes()))
    owners = {
        package: component.label
        for component in contract.components
        for package in component.packages
    }
    for rule in contract.rules:
        if not isinstance(rule, ForbiddenDependencyRule | AllowedDependencyRule):
            continue
        # Same exact-package-match criterion as validation's `_decided_pairs`: a rule
        # scoped to a submodule or a `target_symbol` narrows a rule rather than deciding
        # the component pair, so it is exempt from this id scheme.
        if rule.source not in owners or rule.target not in owners:
            continue
        if isinstance(rule, ForbiddenDependencyRule) and rule.target_symbol is not None:
            continue
        forbidden_id, allowed_id = dependency_rule_ids(owners[rule.source], owners[rule.target])
        expected = forbidden_id if isinstance(rule, ForbiddenDependencyRule) else allowed_id
        assert rule.id == expected


def test_open_decisions_reports_the_pair_left_undecided_by_a_removed_allowed_rule(
    tmp_path: Path,
) -> None:
    root = _prepare_repo(
        tmp_path, {"architecture-contract.json": contract_without_rule("DEP-STORE-ALLOWS-MODEL")}
    )
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))

    decisions = open_decisions(observation)

    assert [(item.source, item.target) for item in decisions] == [("store", "model")]
    assert decisions[0].observed is True
    # repository imports Order; codec imports Order and OrderPayload.
    assert decisions[0].import_sites == 3


def test_open_decision_summary_counts_all_pairs_but_materializes_observed_only() -> None:
    components = tuple((f"module_{index}", (f"sample.module_{index}",)) for index in range(100))
    observation = _observation((_module_edge("sample.module_0.a", "sample.module_1.b", 2),))

    decisions, count = open_decision_summary(observation, components)

    assert count == 100 * 99
    assert [(item.source, item.target, item.import_sites) for item in decisions] == [
        ("module_0", "module_1", 2)
    ]

    small_components = components[:3]
    full = open_decisions(observation, small_components)
    summary, total = open_decision_summary(observation, small_components)
    assert total == len(full)
    assert summary == tuple(item for item in full if item.observed)


def test_validation_and_open_decisions_agree_on_undecided_pairs(tmp_path: Path) -> None:
    root = _prepare_repo(
        tmp_path, {"architecture-contract.json": contract_without_rule("DEP-STORE-ALLOWS-MODEL")}
    )
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    contract = parse_contract(decode_json((root / "architecture-contract.json").read_bytes()))

    decisions = open_decisions(observation)
    diagnostics = closed_world_diagnostics(contract, observation)
    open_diagnostics = [item for item in diagnostics if item.code == "decision.open"]
    assert [(item.source, item.target) for item in decisions] == [("store", "model")]
    assert len(open_diagnostics) == 1
    assert open_diagnostics[0].subject == "1 open dependency decision"
    assert open_diagnostics[0].pointer == "/components"
    assert "requires" in open_diagnostics[0].remedy
    assert "complete_requires" in open_diagnostics[0].remedy


def test_agent_decisions_counts_one_flipped_rule_from_the_observation(tmp_path: Path) -> None:
    """AD-16: a mixed contract's count comes from the observation, not a second contract read."""
    root = _prepare_repo(
        tmp_path,
        {
            "architecture-contract.json": contract_rule_field(
                "DEP-MODEL-NO-STORE", decided_by="agent"
            )
        },
    )
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))

    # 39 rules above the level (AD-11, issue #47) plus the one store's inside declares
    # (AD-36); 8 declared public lists and the inside's 3 requires entries are decisions too
    # (AD-50).
    assert agent_decisions(observation) == (1, 51)


def test_agent_decisions_counts_requires_entries_and_public_lists() -> None:
    """AD-50: a rule, a `requires` edge and a declared `public` list each count as one decision.

    A component that declares no `public` recorded no interface decision, so it adds nothing;
    an entry nobody attributed is a decision all the same, and counts in the total alone.
    """
    observation = _observation(
        (),
        (
            _declaration("RULE-1", "no_component_cycles", (("decided_by", "architect"),)),
            _declaration(
                "COMP-CLI",
                "component_responsibility",
                (
                    (
                        "requires",
                        (
                            RecordData((("component", "api"),)),
                            RecordData((("component", "core"), ("decided_by", "agent"))),
                        ),
                    ),
                ),
            ),
            _declaration(
                "COMP-CORE",
                "component_responsibility",
                (("public", ("sample.core",)), ("decided_by", "agent")),
            ),
            _declaration("COMP-API", "component_responsibility", (("public", ("sample.api",)),)),
        ),
    )

    assert agent_decisions(observation) == (2, 5)


def test_open_decisions_counts_import_sites_for_components_with_split_or_nested_packages() -> None:
    """Regression: a component package nested past the namespace's first two segments, or
    split across several packages, must still accumulate its observed import sites.

    The analyzer's own `package_dependency` edges truncate every module to `pkg.sub`
    (`archkeel.analyzer.python.source.package_for`), which never equals a component
    package like `x.shared.a`; only module-level edges, matched by prefix like
    `ArchitectureContract.component_for`, count correctly.
    """
    components = (("alpha", ("x.shared.a", "x.shared.b")), ("beta", ("x.shared.c",)))
    observation = _observation(
        (
            _module_edge("x.shared.c.m1", "x.shared.a.m2", 3),
            _module_edge("x.shared.c.m3", "x.shared.b.m4", 2),
            _module_edge("x.shared.a.m5", "x.shared.b.m6", 10),  # both alpha: not a pair
            _module_edge("x.shared.b.m7", "x.shared.c.m8", 1),
        )
    )

    decisions = open_decisions(observation, components)

    assert [(item.source, item.target, item.import_sites) for item in decisions] == [
        ("beta", "alpha", 5),
        ("alpha", "beta", 1),
    ]
    assert all(item.observed for item in decisions)


def test_violation_counts_group_the_report_by_rule_and_by_crossing_pair(tmp_path: Path) -> None:
    """AD-51: both breakdowns come from the violation records the report already carries."""
    tour = next(variant for variant in CATALOG if variant.id == "tour")
    root = _prepare_repo(tmp_path, dict(tour.files))
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))

    counts = violation_counts(observation)

    violations = observation.records("violations") or ()
    assert sum(count for _, count in counts.by_rule) == len(violations)
    assert counts.by_rule == (
        ("CONSTRUCT-NO-DYNAMIC", 2),
        ("APP-TYPES-NOT-DICT", 1),
        ("ASSIGNMENT-COMPLETE", 1),
        ("COMPONENT-NO-CYCLES", 1),
        ("CONSTRUCT-NO-ANY", 1),
        ("CONSTRUCT-NO-ASSERT", 1),
        ("CONSTRUCT-NO-BROAD-EXCEPT", 1),
        ("DEP-APP-NO-STORE-BACKEND", 1),
        ("DEP-APP-NO-STORE-SQLITE", 1),
        ("DEP-MODEL-NO-RENDER", 1),
        ("DEP-RENDER-NO-STORE", 1),
        ("DEP-STORE-NO-MONEY", 1),
        ("EXTERNAL-COMPLETE", 1),
        ("EXTERNAL-JSON-STORE", 1),
        ("INTERFACE-BOUNDARY", 1),
        ("LAYERS-MODEL", 1),
        ("MODEL-TYPES-IN-ENTITIES", 1),
        ("ROOT-LAYOUT", 1),
        ("STORE-PEERS-ISOLATED", 1),
        ("store:STORE-REQUIRES-COMPLETE", 1),
    )
    # Direction comes from each record's source_module/target_module: `subjects` is sorted,
    # so DEP-STORE-NO-MONEY would otherwise read as model -> store.
    assert counts.by_component_pair == (
        ("app", "store", 2),
        ("cli", "render", 1),
        ("model", "render", 1),
        ("render", "store", 1),
        ("store", "model", 1),
    )
    assert (result.violations_by_rule, result.violations_by_component_pair) == (
        counts.by_rule,
        counts.by_component_pair,
    )
