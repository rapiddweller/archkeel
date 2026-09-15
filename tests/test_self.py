# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Reobserve Archkeel and verify its saved evidence and product quality checks."""

import json
import subprocess
import sys
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from archkeel.check.onboarding import draft_contract
from archkeel.check.validation import (
    COMPONENT_GRAPH_MARKER,
    closed_world_diagnostics,
    graph_diagnostics,
    rationale_diagnostics,
)
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_contract, parse_observation
from archkeel.ir.digest import package_digest
from archkeel.ir.model import (
    ArchitectureContract,
    ForbiddenDependencyRule,
    Observation,
    in_scope,
)

# AD-4: the analyzer's public IR API is exactly these two modules.
ANALYZER_PUBLIC_IR = frozenset({"archkeel.ir.model", "archkeel.ir.codec"})

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures/D-self"


def _contract() -> ArchitectureContract:
    return parse_contract(decode_json((ROOT / "architecture-contract.json").read_bytes()))


def _architecture_documents() -> tuple[tuple[str, str], ...]:
    paths = (ROOT / "docs/architecture/archkeel.md", ROOT / "README.md")
    return tuple((str(path.relative_to(ROOT)), path.read_text()) for path in paths)


@pytest.fixture(scope="module")
def self_observation(tmp_path_factory: pytest.TempPathFactory) -> Observation:
    output = tmp_path_factory.mktemp("self-report") / "architecture.json"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "archkeel.cli",
            "report",
            "--root",
            str(ROOT),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, (run.stdout, run.stderr)
    assert output.with_name("architecture.report.html").is_file()
    result = json.loads(run.stdout)
    assert result["diagnostics"] == []
    assert result["observation_complete"] == result["declared_rules"] == "PASS"
    assert result["expectation_fulfilled"] == "n/a"
    return parse_observation(decode_canonical_model(json.loads(output.read_bytes())))


def test_self_report_is_complete_and_matches_saved_evidence(self_observation: Observation) -> None:
    observed = self_observation
    artifact = (FIXTURE / "architecture.json").read_bytes()
    provenance = json.loads((FIXTURE / "provenance.json").read_bytes())
    saved = parse_observation(decode_canonical_model(json.loads(artifact)))
    assert observed.records("violations") == ()
    assert all(record.kind != "rule-without-subjects" for record in observed.records("unknowns"))
    coverage = observed.coverage
    assert coverage.status == coverage.rules == "PASS"
    assert coverage.files_discovered == coverage.files_read == coverage.files_parsed > 0
    assert coverage.failures == ()
    assert observed.python_version == saved.python_version
    assert observed.source.source_digest == saved.source.source_digest
    assert observed.contract.digest == saved.contract.digest
    assert observed.analyzer.code_digest == saved.analyzer.code_digest
    assert coverage == saved.coverage
    assert provenance == {
        "analyzer_digest": saved.analyzer.code_digest,
        "checker_digest": package_digest(),
        "source_digest": saved.source.source_digest,
        "contract_digest": saved.contract.digest,
        "artifact_digest": sha256(artifact).hexdigest(),
        "command": "archkeel report --root . --output fixtures/D-self/architecture.json",
        "exit_code": 0,
        "python_version": saved.python_version,
    }


def test_self_contract_covers_modules_and_analyzer_interface(
    self_observation: Observation,
) -> None:
    contract = _contract()
    forbidden_ir = {
        rule.target
        for rule in contract.rules
        if isinstance(rule, ForbiddenDependencyRule) and rule.source == "archkeel.analyzer"
    }
    for module in self_observation.records("modules") or ():
        name = module.data.get("qualified_name")
        assert isinstance(name, str)
        if name.startswith("archkeel.ir.") and name not in ANALYZER_PUBLIC_IR:
            assert any(in_scope(name, prefix) for prefix in forbidden_ir), name
    for record in self_observation.records("imports") or ():
        source = record.data.get("source_module")
        target = record.data.get("target_module")
        assert isinstance(source, str) and isinstance(target, str)
        if in_scope(source, "archkeel.analyzer") and in_scope(target, "archkeel.ir"):
            assert target in ANALYZER_PUBLIC_IR, (source, target)


def test_self_contract_public_matches_drafted_proposal(self_observation: Observation) -> None:
    """AD-9 `public` entries come from `draft_contract`, not hand edits (SPOT guard)."""
    contract = _contract()
    drafted, _ = draft_contract(self_observation, "archkeel")
    actual = {component.label: component.public for component in contract.components}
    proposed = {component.label: component.public for component in drafted.components}
    assert actual == proposed


def test_self_contract_closes_every_component_pair(self_observation: Observation) -> None:
    assert closed_world_diagnostics(_contract(), self_observation) == ()


def test_contract_rationales_explain_more_than_the_rule() -> None:
    assert rationale_diagnostics(_contract()) == ()


def test_component_graph_matches_observed_edges(self_observation: Observation) -> None:
    assert graph_diagnostics(_contract(), self_observation, _architecture_documents()) == ()


def test_closed_world_check_detects_a_removed_rule(self_observation: Observation) -> None:
    contract = _contract()
    rule = next(
        item
        for item in contract.rules
        if isinstance(item, ForbiddenDependencyRule)
        and item.source == "archkeel.ir"
        and item.target == "archkeel.check"
    )
    broken = replace(contract, rules=tuple(item for item in contract.rules if item != rule))
    assert closed_world_diagnostics(broken, self_observation)[0].pointer == "/rules"


def test_rationale_check_detects_a_repeated_rule() -> None:
    contract = _contract()
    rule = contract.rules[0]
    assert isinstance(rule, ForbiddenDependencyRule)
    repeated = replace(rule, rationale=f"{rule.source} does not depend on {rule.target}.")
    broken = replace(contract, rules=(repeated, *contract.rules[1:]))
    assert rationale_diagnostics(broken)[0].pointer == "/rules/0/rationale"


def test_graph_check_detects_a_missing_edge(self_observation: Observation) -> None:
    documents = tuple(
        (path, content.replace("    cli --> accept\n", ""))
        for path, content in _architecture_documents()
    )
    diagnostic = graph_diagnostics(_contract(), self_observation, documents)[0]
    assert diagnostic.pointer == "/components"
    assert "cli->accept" in diagnostic.unknown_claim
    assert COMPONENT_GRAPH_MARKER in _architecture_documents()[0][1]
