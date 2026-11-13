# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Reobserve Archkeel and verify fresh evidence and product quality checks."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from archkeel.check.onboarding import (
    _crossing_targets,
    draft_contract,
    interface_entries,
    module_all_exports,
)
from archkeel.check.validation import COMPONENT_GRAPH_MARKER
from archkeel.check.validation.graphs import TARGET_GRAPH_MARKER
from archkeel.check.validation.rationale import rationale_diagnostics
from archkeel.ir.codec import decode_json, parse_contract
from archkeel.ir.model import (
    ArchitectureContract,
    ForbiddenDependencyRule,
    Observation,
    module_in_ownership,
)

# Adapters share source facts, record builders, protocol and language-specific fact values.
# Governance models, metrics and rule policy stay behind the Core boundary.
ANALYZER_PUBLIC_IR = frozenset(
    {
        "archkeel.ir.facts",
        "archkeel.ir.facts_codec",
        "archkeel.ir.identity",
        "archkeel.ir.phases",
        "archkeel.ir.protocol",
        "archkeel.ir.profiles:is_test_source",
        "archkeel.ir.state_facts",
        "archkeel.ir.type_shapes",
        "archkeel.ir.reexports",
        "archkeel.ir.source_records",
        "archkeel.ir.guard_paths:GuardedCallPath",
        "archkeel.ir.guard_paths:guarded_call_paths",
        "archkeel.ir.source_proofs:class_instance_member_write_names",
        "archkeel.ir.source_proofs:parse_numeric_evidence_excerpt",
        # AD-346: the opt-in store collector reads the read-set and opens the store session.
        "archkeel.ir.readset_codec:decode_read_set",
        "archkeel.ir.store_seam:StoreEntry",
        "archkeel.ir.store_seam:close_store",
        "archkeel.ir.store_seam:open_store",
        "archkeel.ir.store_seam:store_enabled",
    }
)
ROOT = Path(__file__).parents[1]


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
    baseline = json.loads((ROOT / "architecture-baseline.json").read_bytes())

    assert public in (check.public or ()) and public in (owners[0].public or ())
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


def _architecture_documents() -> tuple[tuple[str, str], ...]:
    paths = (ROOT / "docs/architecture/archkeel.md", ROOT / "README.md")
    return tuple((str(path.relative_to(ROOT)), path.read_text()) for path in paths)


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
        # A retained module port remains used through its named exports.
        used_modules = {entry.partition(":")[0] for entry in needed}
        extra = entries - set(proposed.get(component.label) or ()) - needed - used_modules
        assert {item.replace(":", ".") for item in extra} <= exposed, (component.label, extra)


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


def test_contract_rationales_explain_more_than_the_rule() -> None:
    assert rationale_diagnostics(_contract()) == ()


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
