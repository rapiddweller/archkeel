# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Reobserve Archkeel and verify its saved evidence and product quality checks."""

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from conftest import SelfRun

from archkeel.check.onboarding import (
    _crossing_targets,
    draft_contract,
    interface_entries,
    module_all_exports,
)
from archkeel.check.validation import (
    COMPONENT_GRAPH_MARKER,
    TARGET_GRAPH_MARKER,
    closed_world_diagnostics,
    graph_diagnostics,
    public_api_diagnostics,
    rationale_diagnostics,
)
from archkeel.ir.codec import canonical_report_bytes, decode_json, parse_contract
from archkeel.ir.digest import package_digest
from archkeel.ir.interfaces import interface_profile
from archkeel.ir.levels import inside_levels
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    BoundaryTypesRule,
    ForbiddenDependencyRule,
    Observation,
    in_scope,
    module_in_ownership,
    text_value,
)
from archkeel.ir.structure import oversized_insides

# Adapters share source facts, record builders, protocol and language-specific fact values.
# Governance models, metrics and rule policy stay behind the Core boundary.
ANALYZER_PUBLIC_IR = frozenset(
    {
        "archkeel.ir.facts",
        "archkeel.ir.facts_codec",
        "archkeel.ir.protocol",
        "archkeel.ir.state_facts",
        "archkeel.ir.type_shapes",
        "archkeel.ir.reexports",
        "archkeel.ir.source_records",
    }
)
ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures/D-self"
STALE = "fixtures/D-self is stale: run `make self-observation` and commit the result on its own"


def _contract() -> ArchitectureContract:
    return parse_contract(decode_json((ROOT / "architecture-contract.json").read_bytes()))


def _assert_cli_resolver_publication(inside: ArchitectureContract) -> None:
    public = "archkeel.check.snapshot:resolve_commit"
    contract = _contract()
    check = next(component for component in contract.components if component.label == "check")
    owners = [
        component
        for component in inside.components
        if module_in_ownership(
            "archkeel.check.snapshot", component.packages, component.exact_modules or ()
        )
    ]
    assert len(owners) == 1
    assert contract.declarations is not None
    coupling = next(
        item
        for item in contract.declarations.coupling_budgets
        if (item.source, item.target) == ("cli", "check")
    )
    baseline = json.loads((ROOT / "architecture-baseline.json").read_bytes())

    assert public in (check.public or ()) and public in (owners[0].public or ())
    # AD-207 adds the saved-query workflow to the existing typed CLI seam.
    assert coupling.max_names == 15
    assert public in baseline["budgets"]["coupling_names"]["cli -> check"]
    assert (
        "archkeel.check.report:run_saved_report"
        in baseline["budgets"]["coupling_names"]["cli -> check"]
    )


def _check_inside() -> ArchitectureContract:
    check = next(component for component in _contract().components if component.label == "check")
    assert check.inside is not None
    return parse_contract(decode_json((ROOT / check.inside).read_bytes()))


def test_cli_resolver_is_published_and_the_coupling_ceiling_tracks_it() -> None:
    _assert_cli_resolver_publication(_check_inside())


def test_cli_resolver_guard_rejects_missing_active_inside_publication() -> None:
    inside = _check_inside()
    public = "archkeel.check.snapshot:resolve_commit"
    changed = replace(
        inside,
        components=tuple(
            replace(
                component,
                public=tuple(entry for entry in component.public or () if entry != public),
            )
            for component in inside.components
        ),
    )
    with pytest.raises(AssertionError):
        _assert_cli_resolver_publication(changed)


def test_cli_check_measure_counts_named_shared_type_reexports(
    self_observation: Observation,
) -> None:
    """AD-148: shared types stay named members of the Core seam, not an open module grant."""
    profile = interface_profile(self_observation)
    width = next(
        item for item in profile.coupling if item.source == "cli" and item.target == "check"
    )
    check = next(item for item in _contract().components if item.label == "check")

    assert {
        "archkeel.check.ports:Language",
        "archkeel.check.ports:ObservationResult",
    } <= set(width.names)
    assert len(width.names) == 15
    assert width.uncounted == ()
    assert "archkeel.check.ports" not in (check.public or ())
    assert "archkeel.check.observe" not in (check.public or ())


def _architecture_documents() -> tuple[tuple[str, str], ...]:
    paths = (ROOT / "docs/architecture/archkeel.md", ROOT / "README.md")
    return tuple((str(path.relative_to(ROOT)), path.read_text()) for path in paths)


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


def _assert_self_provenance(observed: Observation, provenance: dict[str, object]) -> None:
    # A commit or unrelated edit does not change the observed source.
    normalized = replace(observed, source=replace(observed.source, git_head=None, dirty=False))
    assert provenance == {
        "checker_digest": package_digest(),
        "observation_digest": sha256(canonical_report_bytes(normalized)).hexdigest(),
    }, STALE


def test_self_report_is_complete_and_matches_saved_evidence(self_observation: Observation) -> None:
    observed = self_observation
    provenance = json.loads((FIXTURE / "provenance.json").read_bytes())
    assert observed.records("violations") == ()
    assert all(record.kind != "rule-without-subjects" for record in observed.records("unknowns"))
    coverage = observed.coverage
    assert coverage.status == coverage.rules == "PASS"
    assert coverage.files_discovered == coverage.files_read == coverage.files_parsed > 0
    assert coverage.failures == ()
    _assert_self_provenance(observed, provenance)


def test_self_contract_covers_modules_and_analyzer_interface(
    self_observation: Observation,
) -> None:
    """AD-4 lives in the contract (AD-42): the analyzer's `requires` entry for `ir` goes
    through exactly the named modules, and the observed imports stay inside them."""
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


def test_self_facades_record_the_declared_types_they_expose(self_observation: Observation) -> None:
    """AD-65 on this repository: the facade positions measured in `check` and `render` are
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
        "archkeel.render.summary:Badge",
        "archkeel.render.summary:Summary",
        "archkeel.render.summary:VerdictRow",
    } <= declared
    scoped = {rule.source for rule in contract.rules if isinstance(rule, BoundaryTypesRule)}
    assert scoped == {"archkeel.analyzer", "archkeel.check", "archkeel.render"}


def _assert_public_surface(contract: ArchitectureContract, observation: Observation) -> None:
    drafted, _, _ = draft_contract(observation, "archkeel")
    proposed = {component.label: component.public for component in drafted.components}
    all_exports = module_all_exports(observation.records("modules") or ())
    required: dict[str, set[str]] = {}
    for module, (label, whole_module, names) in _crossing_targets(observation, contract).items():
        required.setdefault(label, set()).update(
            interface_entries(module, names, whole_module, all_exports.get(module, False), set())
        )
    exposed = {
        item
        for record in observation.records("symbols") or ()
        for item in (record.data.get("facade_types") or ())
        if isinstance(item, str)
    }
    for component in contract.components:
        entries = set(component.public or ())
        needed = required.get(component.label, set())
        for entry in needed:
            assert entry in entries or (":" in entry and entry.partition(":")[0] in entries), (
                component.label,
                entry,
            )
        extra = entries - set(proposed.get(component.label) or ()) - needed
        assert {item.replace(":", ".") for item in extra} <= exposed, (component.label, extra)


def test_self_contract_public_matches_drafted_proposal(self_observation: Observation) -> None:
    """Named exports may narrow the draft's half-use heuristic without dropping actual uses."""
    _assert_public_surface(_contract(), self_observation)


@pytest.mark.parametrize("remove_used", [True, False], ids=["missing-used", "unexposed-extra"])
def test_self_public_guard_rejects_unsupported_surface(
    self_observation: Observation, remove_used: bool
) -> None:
    contract = _contract()
    public = "archkeel.ir.identity:module_identity"
    modified = replace(
        contract,
        components=tuple(
            replace(
                component,
                public=tuple(entry for entry in component.public or () if entry != public)
                if remove_used
                else (*(component.public or ()), "archkeel.ir.identity:_segments"),
            )
            if component.label == "ir"
            else component
            for component in contract.components
        ),
    )
    with pytest.raises(AssertionError):
        _assert_public_surface(modified, self_observation)


def test_self_analyzer_inside_covers_its_modules(self_observation: Observation) -> None:
    """AD-148: the process host and each language adapter own the modules they observe."""
    levels = {level.parent: level for level in inside_levels(self_observation)}
    assert set(levels) == {"analyzer", "analyzer:dart", "analyzer:python", "check", "ir", "render"}
    analyzer = levels["analyzer"]
    modules_by_component = {item.label: set(item.modules) for item in analyzer.components}
    assert set(modules_by_component) == {"dart", "process", "python"}
    assert modules_by_component["process"] == {
        "archkeel.analyzer",
        "archkeel.analyzer.process",
        "archkeel.analyzer.runtime",
        "archkeel.analyzer.windows_job",
    }
    assert modules_by_component["python"] == {
        "archkeel.analyzer.python",
        "archkeel.analyzer.python.bindings",
        "archkeel.analyzer.python.calls",
        "archkeel.analyzer.python.collect",
        "archkeel.analyzer.python.constructs",
        "archkeel.analyzer.python.entry",
        "archkeel.analyzer.python.imports",
        "archkeel.analyzer.python.private_attributes",
        "archkeel.analyzer.python.receiver_types",
        "archkeel.analyzer.python.references",
        "archkeel.analyzer.python.resolve",
        "archkeel.analyzer.python.scopes",
        "archkeel.analyzer.python.source",
        "archkeel.analyzer.python.state",
        "archkeel.analyzer.python.symbols",
        "archkeel.analyzer.python.type_shapes",
        "archkeel.analyzer.python.typing_signals",
    }
    assert modules_by_component["dart"] == {
        "archkeel.analyzer.dart",
        "archkeel.analyzer.dart.collect",
        "archkeel.analyzer.dart.directives",
        "archkeel.analyzer.dart.entry",
        "archkeel.analyzer.dart.lexer",
        "archkeel.analyzer.dart.resolve",
    }
    assert analyzer.unassigned == ()
    assert levels["analyzer:python"].unassigned == ()
    assert levels["analyzer:dart"].unassigned == ()
    assert levels["ir"].unassigned == ()
    assert all(
        ".embedded" not in module for modules in modules_by_component.values() for module in modules
    )


def test_process_public_interface_names_the_collector_class_only() -> None:
    contract = _contract()
    analyzer = next(item for item in contract.components if item.label == "analyzer")
    assert analyzer.public is not None
    assert "archkeel.analyzer.process:ProcessCollector" in analyzer.public
    assert "archkeel.analyzer.process" not in analyzer.public
    nested = json.loads((ROOT / "docs/architecture/contracts/analyzer.json").read_text())
    process = next(item for item in nested["components"] if item["label"] == "process")
    assert "archkeel.analyzer.process:ProcessCollector" in process["public"]
    assert "archkeel.analyzer.process" not in process["public"]


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
    """AD-70: the self contract must declare every type its public API hands out."""
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


def test_self_facade_profile_measures_archkeel_interfaces(self_observation: Observation) -> None:
    """AD-88 is exercised against the repository's own declared facades."""
    profile = interface_profile(self_observation)
    interfaces = next(item for item in profile.facades if item.module == "archkeel.ir.interfaces")
    assert interfaces.exported_name_count > 0
    assert any(item.source == "analyzer" and item.target == "ir" for item in profile.coupling)
