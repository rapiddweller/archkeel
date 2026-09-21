# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Reobserve Archkeel and verify its saved evidence and product quality checks."""

import json
import subprocess
import sys
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

import pytest

from archkeel.check.onboarding import draft_contract
from archkeel.check.validation import (
    COMPONENT_GRAPH_MARKER,
    TARGET_GRAPH_MARKER,
    closed_world_diagnostics,
    graph_diagnostics,
    public_api_diagnostics,
    rationale_diagnostics,
)
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_contract, parse_observation
from archkeel.ir.digest import package_digest
from archkeel.ir.levels import inside_levels
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    BoundaryTypesRule,
    ForbiddenDependencyRule,
    Observation,
    in_scope,
    text_value,
)
from archkeel.ir.structure import oversized_insides

# AD-4: the analyzer's public IR API is exactly these two modules.
ANALYZER_PUBLIC_IR = frozenset({"archkeel.ir.model", "archkeel.ir.codec"})

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures/D-self"
STALE = "fixtures/D-self is stale: run `make self-observation` and commit the result on its own"


def _contract() -> ArchitectureContract:
    return parse_contract(decode_json((ROOT / "architecture-contract.json").read_bytes()))


def _architecture_documents() -> tuple[tuple[str, str], ...]:
    paths = (ROOT / "docs/architecture/archkeel.md", ROOT / "README.md")
    return tuple((str(path.relative_to(ROOT)), path.read_text()) for path in paths)


@dataclass(frozen=True, slots=True)
class SelfRun:
    """One `archkeel report` on this repository: the model it wrote and the result it printed."""

    observation: Observation
    result: str


@pytest.fixture(scope="module")
def self_run(tmp_path_factory: pytest.TempPathFactory) -> SelfRun:
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
    # AD-67: Archkeel's own declared `boundary_types` rule does leave one `boundary_type_limit`
    # record per declared rule. `analyzer`'s 2 undecided are both `external_type` --
    # `pathlib.Path` and `datetime.datetime`, types no declared component owns, so the rule has
    # no `public` list to read them against, and that question never applied. `render` and
    # `check`, declared here (AD-68), leave 16 positions undecided for reasons that ARE gaps in
    # what the checker could read: 15 a union, 1 an unentered generic. So Archkeel's own run
    # says UNKNOWN, which is the honest answer, and says it without gating (AD-72).
    assert result["observation_complete"] == "PASS"
    assert result["declared_rules"] == "UNKNOWN"
    assert result["expectation_fulfilled"] == "n/a"
    observation = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    return SelfRun(observation, run.stdout)


@pytest.fixture(scope="module")
def self_observation(self_run: SelfRun) -> Observation:
    return self_run.observation


def test_self_result_matches_the_saved_run(self_run: SelfRun) -> None:
    """The saved result is what the command printed, or it is decoration that drifts.

    It carried `agent_decisions [0, 24]` and 60 files for several releases while the
    repository had moved on, because nothing read it and the README linked it as evidence.
    `artifact` is dropped from both sides: it records where one run was told to write, which
    is the caller's argument, not a property of this repository.
    """
    saved = json.loads((FIXTURE / "result.json").read_bytes())
    observed = json.loads(self_run.result)
    assert saved.pop("artifact") == "fixtures/D-self/architecture.json"
    assert observed.pop("artifact")
    assert saved == observed, STALE


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
    assert observed.python_version == saved.python_version, STALE
    assert observed.source.source_digest == saved.source.source_digest, STALE
    assert observed.contract.digest == saved.contract.digest, STALE
    assert observed.analyzer.code_digest == saved.analyzer.code_digest, STALE
    assert coverage == saved.coverage, STALE
    # Spelled out, not imported from fixtures/reproduce_self.py: one bug there must not
    # produce both the saved value and the value this test expects.
    assert provenance == {
        "analyzer_digest": saved.analyzer.code_digest,
        "checker_digest": package_digest(),
        "source_digest": saved.source.source_digest,
        "contract_digest": saved.contract.digest,
        "artifact_digest": sha256(artifact).hexdigest(),
        "command": "archkeel report --root . --output fixtures/D-self/architecture.json",
        "exit_code": 0,
        "python_version": saved.python_version,
    }, STALE


def test_self_contract_covers_modules_and_analyzer_interface(
    self_observation: Observation,
) -> None:
    """AD-4 lives in the contract (AD-42): the analyzer's `requires` entry for `ir` goes
    through exactly the two modules, and the observed imports stay inside them."""
    contract = _contract()
    analyzer = next(item for item in contract.components if item.label == "analyzer")
    entry = next(item for item in analyzer.requires or () if item.component == "ir")
    assert frozenset(entry.through) == ANALYZER_PUBLIC_IR
    for record in self_observation.records("imports") or ():
        source = record.data.get("source_module")
        target = record.data.get("target_module")
        assert isinstance(source, str) and isinstance(target, str)
        if in_scope(source, "archkeel.analyzer") and in_scope(target, "archkeel.ir"):
            assert target in ANALYZER_PUBLIC_IR, (source, target)


def test_self_facades_record_the_ten_types_they_expose(self_observation: Observation) -> None:
    """AD-65 on this repository: the ten positions AD-63 measured in `check` and `render` are
    recorded as reached, so declaring them no longer collides with `interface.unused`
    (issue #57), and AD-68 declares all three types and scopes the rule to both components."""
    exposed: dict[str, tuple[str, ...]] = {}
    for record in self_observation.records("symbols") or ():
        name = text_value(record.data.get("qualified_name"))
        types = record.data.get("facade_types")
        if name and isinstance(types, tuple):
            exposed[name] = tuple(item for item in types if isinstance(item, str))
    assert "archkeel.check.ports.Analyzer" in exposed["archkeel.check.report.run_report"]
    assert "archkeel.check.ports.Host" in exposed["archkeel.check.run.run_check"]
    for name in ("check_summary", "init_summary", "report_summary"):
        assert "archkeel.render.summary.Summary" in exposed[f"archkeel.render.summary.{name}"]
    contract = _contract()
    declared = {entry for item in contract.components for entry in item.public or ()}
    assert {
        "archkeel.check.ports:Analyzer",
        "archkeel.check.ports:Host",
        "archkeel.render.summary:Summary",
    } <= declared
    scoped = {rule.source for rule in contract.rules if isinstance(rule, BoundaryTypesRule)}
    assert scoped == {"archkeel.analyzer", "archkeel.check", "archkeel.render"}


def test_self_contract_public_matches_drafted_proposal(self_observation: Observation) -> None:
    """AD-9 `public` entries come from `draft_contract`, not hand edits (SPOT guard).

    AD-65 gave an entry a second way of being reached, and `_drafted_public` proposes only the
    first: it reads inbound crossing imports, so a type no consumer imports but a declared
    facade signature exposes is never proposed. AD-68 declares three of those. The guard keeps
    its teeth by checking both readings instead of one: nothing the drafter proposes may be
    edited away, and every extra entry has to be a type the observation records some facade
    signature as exposing, which is not something a hand edit can invent.
    """
    contract = _contract()
    drafted, _, _ = draft_contract(self_observation, "archkeel")
    proposed = {component.label: component.public for component in drafted.components}
    exposed = {
        item
        for record in self_observation.records("symbols") or ()
        for item in (record.data.get("facade_types") or ())
        if isinstance(item, str)
    }
    for component in contract.components:
        entries = set(component.public or ())
        assert set(proposed.get(component.label) or ()) <= entries, component.label
        extra = entries - set(proposed.get(component.label) or ())
        assert {item.replace(":", ".") for item in extra} <= exposed, (component.label, extra)


def test_self_analyzer_inside_covers_its_modules(self_observation: Observation) -> None:
    """AD-45: `analyzer` declares an inside too, the same shape `check`'s (AD-34) already
    carries. Both parents are named because a second declared inside is one more entry in the
    same map, not a new derivation; a stale count here would mean a sub-component silently
    stopped owning a module it used to."""
    levels = {level.parent: level for level in inside_levels(self_observation)}
    assert set(levels) == {"analyzer", "check"}
    analyzer = levels["analyzer"]
    assert [(item.label, len(item.modules)) for item in analyzer.components] == [
        ("collectors", 10),
        ("foundation", 5),
        ("orchestration", 5),
    ]
    assert analyzer.unassigned == ("archkeel.analyzer", "archkeel.analyzer.embedded")


def test_self_oversized_components_claim_still_counts_analyzer(
    self_observation: Observation,
) -> None:
    """AD-45's limit: `oversized_insides` (AD-33) compares a component's raw module and edge
    count against the top level's own, not against whether it has a declared inside, so
    `analyzer` joins `check` on this claim instead of leaving it once its inside is declared."""
    sizes = oversized_insides(self_observation)
    assert {item.scope for item in sizes.candidates} == {"analyzer", "check", "ir"}


def test_self_contract_closes_every_component_pair(self_observation: Observation) -> None:
    assert closed_world_diagnostics(_contract(), self_observation) == ()


def test_self_public_api_declares_every_type_it_hands_out(self_observation: Observation) -> None:
    """AD-70: `archkeel.api`, the boundary the invariant was written for, must clear whatever
    guard closes tests/test_public_api_boundary.py's red tests -- a green regression guard, not
    proof the guard exists. It already passes today, for the narrower reason that
    `public_api_diagnostics` does not yet look at a declared entry's signature at all."""
    assert public_api_diagnostics(_contract(), self_observation) == ()


def test_contract_rationales_explain_more_than_the_rule() -> None:
    assert rationale_diagnostics(_contract()) == ()


def test_component_graph_matches_observed_edges(self_observation: Observation) -> None:
    assert graph_diagnostics(_contract(), self_observation, _architecture_documents()) == ()


def test_self_architecture_page_draws_both_the_observed_and_target_graph() -> None:
    """AD-57 leaves the target marker optional for every project but this one.

    Archkeel's own target is derivable from `architecture-contract.json`'s `requires` entries
    at no cost, so the repository that ships `--write-graph` should be seen using it on itself;
    nothing but this test would notice the marker quietly going missing again. Whether the
    target block's edges actually match `target_component_edges` is not re-checked here:
    `test_component_graph_matches_observed_edges` above already calls `graph_diagnostics` on
    this same page, and `graph_diagnostics` walks both markers (AD-57), so a drifted target
    graph already fails there as a `graph.drift` diagnostic naming the target marker.
    """
    page = (ROOT / "docs/architecture/archkeel.md").read_text()
    assert COMPONENT_GRAPH_MARKER in page and TARGET_GRAPH_MARKER in page, (
        "Archkeel's own architecture page must carry both the observed graph marker and the "
        "target graph marker: this repository dogfoods archkeel-target-graph (AD-57), so its "
        "own page cannot silently fall back to only the observed graph."
    )


def test_closed_world_check_detects_a_conflicting_rule(self_observation: Observation) -> None:
    """closed_world_diagnostics reads decisions from the live contract, not just observation."""
    contract = _contract()
    # AD-32 moved every component pair into `requires`, so no rule in the live contract decides
    # one any more. The probe states both decisions itself, for a pair that really exists.
    provenance = contract.components[0].provenance
    forbidden = ForbiddenDependencyRule(
        "DEP-IR-NO-CHECK-PROBE",
        "forbidden_dependency",
        "archkeel.ir",
        "archkeel.check",
        True,
        "Conflict probe.",
        provenance,
        "architect",
    )
    conflict = AllowedDependencyRule(
        "DEP-IR-ALLOWS-CHECK-PROBE",
        "allowed_dependency",
        "archkeel.ir",
        "archkeel.check",
        "Conflict probe.",
        provenance,
        "architect",
    )
    broken = replace(contract, rules=(*contract.rules, forbidden, conflict))
    diagnostics = closed_world_diagnostics(broken, self_observation)
    assert diagnostics and diagnostics[0].code == "decision.conflict"
    assert diagnostics[0].pointer == "/rules"


def test_rationale_check_detects_a_repeated_rule() -> None:
    contract = _contract()
    # AD-42 left no forbidden rule in the live contract, so the probe brings its own.
    repeated = ForbiddenDependencyRule(
        "DEP-IR-NO-CHECK-PROBE",
        "forbidden_dependency",
        "archkeel.ir",
        "archkeel.check",
        True,
        "archkeel.ir does not depend on archkeel.check.",
        contract.components[0].provenance,
        "architect",
    )
    index = len(contract.rules)
    broken = replace(contract, rules=(*contract.rules, repeated))
    assert rationale_diagnostics(broken)[0].pointer == f"/rules/{index}/rationale"


def test_graph_check_detects_a_missing_edge(self_observation: Observation) -> None:
    documents = tuple(
        (path, content.replace("    cli --> render\n", ""))
        for path, content in _architecture_documents()
    )
    diagnostic = graph_diagnostics(_contract(), self_observation, documents)[0]
    assert diagnostic.pointer == "/components"
    assert "cli->render" in diagnostic.unknown_claim
    assert COMPONENT_GRAPH_MARKER in _architecture_documents()[0][1]
