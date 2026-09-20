# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-15: open_decisions derives undecided component pairs from one observation alone."""

import json
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.validation import closed_world_diagnostics
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_contract, parse_observation
from archkeel.ir.decisions import agent_decisions, dependency_rule_ids, open_decisions
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
        analyzer=AnalyzerInfo("test-analyzer", "0.0.0", "0" * 16),
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
    open_subjects = {item.subject for item in diagnostics if item.code == "decision.open"}

    assert open_subjects == {f"{item.source} -> {item.target}" for item in decisions}
    assert open_subjects == {"store -> model"}

    open_decision = next(item for item in diagnostics if item.code == "decision.open")
    assert open_decision.unknown_claim == "3 import site(s) use this pair, and no rule decides it."
    assert open_decision.remedy == (
        "Allow or forbid the pair: add an allowed_dependency or forbidden_dependency rule "
        "with a rationale."
    )


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

    # 34 rules above the level plus the one store's inside declares (AD-36); 8 declared
    # public lists and the inside's 3 requires entries are decisions too (AD-50).
    assert agent_decisions(observation) == (1, 46)


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
    (`archkeel.analyzer.embedded.source.package_for`), which never equals a component
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
