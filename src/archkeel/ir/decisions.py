# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Derive undecided component pairs from one observation alone (AD-15).

One function reads the projected dependency decisions and the observed component edges, so
validation and a report rendered later from `architecture.json` bytes share one derivation.
"""

from __future__ import annotations

from collections import Counter
from typing import Final, get_args, get_type_hints

from .interfaces import component_owners, owner_of
from .model import (
    AllowedDependencyRule,
    ArchitectureRule,
    ForbiddenDependencyRule,
    Observation,
    OpenDecision,
    package_owners,
)

_DECIDING_KINDS = frozenset({"forbidden_dependency", "allowed_dependency"})

# Every rule kind the ArchitectureRule union names, read by reflection so a new rule kind
# is counted here without a second hand-written list (AD-16).
_RULE_KINDS: Final[frozenset[str]] = frozenset(
    kind
    for rule_type in get_args(ArchitectureRule)
    for kind in get_args(get_type_hints(rule_type)["kind"])
)

# The provenance every drafted dependency option cites; init writes this file alongside
# the contract, so the path already exists by the time an architect copies an option in.
DOCUMENT_PATH: Final = "docs/architecture/architecture.md"

_PLACEHOLDER_RATIONALE: Final = "TODO: the architect's reason for this decision."


def _decided_component_pairs(
    observation: Observation, owners: dict[str, str]
) -> set[tuple[str, str]]:
    """Pairs a `forbidden_dependency` or `allowed_dependency` rule decides.

    Exact package match only, like validation's own `_decided_pairs`: a rule scoped to a
    submodule or a `target_symbol` narrows a rule, it does not decide the component pair.
    """
    decided: set[tuple[str, str]] = set()
    for record in observation.records("declarations") or ():
        if record.kind not in _DECIDING_KINDS:
            continue
        source_module = record.data.get("source")
        target_module = record.data.get("target")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        source = owners.get(source_module)
        target = owners.get(target_module)
        if source is not None and target is not None:
            decided.add((source, target))
    return decided


def _component_import_sites(
    observation: Observation, components: tuple[tuple[str, tuple[str, ...]], ...]
) -> Counter[tuple[str, str]]:
    """Import-site counts per component pair, from the analyzer's own module-level edges."""
    sites: Counter[tuple[str, str]] = Counter()
    for record in observation.records("dependency_edges") or ():
        if record.kind != "module_dependency":
            continue
        source_module = record.data.get("source")
        target_module = record.data.get("target")
        count = record.data.get("count")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        if not isinstance(count, int):
            continue
        source = owner_of(source_module, components)
        target = owner_of(target_module, components)
        if source is not None and target is not None and source != target:
            sites[(source, target)] += count
    return sites


def _open_decision(
    source: str, target: str, packages: dict[str, tuple[str, ...]], import_sites: int
) -> OpenDecision:
    source_package = packages[source][0]
    target_package = packages[target][0]
    forbidden_id, allowed_id = dependency_rule_ids(source, target)
    return OpenDecision(
        source,
        target,
        source_package,
        target_package,
        import_sites > 0,
        import_sites,
        ForbiddenDependencyRule(
            forbidden_id,
            "forbidden_dependency",
            source_package,
            target_package,
            True,
            _PLACEHOLDER_RATIONALE,
            (DOCUMENT_PATH,),
            "agent",
        ),
        AllowedDependencyRule(
            allowed_id,
            "allowed_dependency",
            source_package,
            target_package,
            _PLACEHOLDER_RATIONALE,
            (DOCUMENT_PATH,),
            "agent",
        ),
    )


def inner_opt_ins(observation: Observation) -> frozenset[str]:
    """Components whose inside an architect chose to govern (AD-31)."""
    return frozenset(
        component
        for record in observation.records("declarations") or ()
        if record.kind == "complete_inner_decisions"
        and isinstance(component := record.data.get("component"), str)
    )


def decided_module_pairs(observation: Observation) -> set[tuple[str, str]]:
    """Module pairs a dependency rule names directly, by exact module scope."""
    decided: set[tuple[str, str]] = set()
    for record in observation.records("declarations") or ():
        if record.kind not in _DECIDING_KINDS:
            continue
        source = record.data.get("source")
        target = record.data.get("target")
        if isinstance(source, str) and isinstance(target, str):
            decided.add((source, target))
    return decided


def _observed_inner_pairs(
    observation: Observation,
    components: tuple[tuple[str, tuple[str, ...]], ...],
    opted: frozenset[str],
) -> dict[tuple[str, str], int]:
    """Observed module pairs inside an opted-in component, with their import-site weight.

    Observed pairs only, never the product of the modules: `analyzer` holds 21 modules, so
    the product is 420 pairs against 46 observed ones, and a pair nobody imports needs no
    decision (AD-31).
    """
    found: dict[tuple[str, str], int] = {}
    for record in observation.records("dependency_edges") or ():
        if record.kind != "module_dependency":
            continue
        source = record.data.get("source")
        target = record.data.get("target")
        count = record.data.get("count")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        owner = owner_of(source, components)
        if owner is None or owner not in opted or owner != owner_of(target, components):
            continue
        found[(source, target)] = count if isinstance(count, int) else 0
    return found


def _inner_open_decision(source: str, target: str, import_sites: int) -> OpenDecision:
    forbidden_id, allowed_id = dependency_rule_ids(source, target)
    return OpenDecision(
        source,
        target,
        source,
        target,
        True,
        import_sites,
        ForbiddenDependencyRule(
            forbidden_id,
            "forbidden_dependency",
            source,
            target,
            True,
            _PLACEHOLDER_RATIONALE,
            (DOCUMENT_PATH,),
            "agent",
        ),
        AllowedDependencyRule(
            allowed_id,
            "allowed_dependency",
            source,
            target,
            _PLACEHOLDER_RATIONALE,
            (DOCUMENT_PATH,),
            "agent",
        ),
    )


def open_inner_decisions(
    observation: Observation,
    components: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
) -> tuple[OpenDecision, ...]:
    """Derive undecided module pairs inside components that opted in (AD-31).

    Empty unless a `complete_inner_decisions` rule names a component, so no repository
    inherits this work by upgrading.
    """
    opted = inner_opt_ins(observation)
    if not opted:
        return ()
    resolved = component_owners(observation) if components is None else components
    decided = decided_module_pairs(observation)
    observed = _observed_inner_pairs(observation, resolved, opted)
    return tuple(
        sorted(
            (
                _inner_open_decision(source, target, sites)
                for (source, target), sites in observed.items()
                if (source, target) not in decided
            ),
            key=lambda item: (-item.import_sites, item.source, item.target),
        )
    )


def open_decisions(
    observation: Observation,
    components: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
) -> tuple[OpenDecision, ...]:
    """Derive undecided component pairs, heaviest observed edges first (AD-15).

    `components` lets `init` supply the components it just drafted, before any contract
    declares them; `validate` and a report rendered later from `architecture.json` bytes
    pass none and read the observation's own declared components instead.
    """
    resolved = component_owners(observation) if components is None else components
    owners = package_owners(resolved)
    packages = dict(resolved)
    labels = {label for label, _ in resolved}
    expected = {(source, target) for source in labels for target in labels if source != target}
    decided = _decided_component_pairs(observation, owners)
    sites = _component_import_sites(observation, resolved)
    return tuple(
        sorted(
            (
                _open_decision(source, target, packages, sites[(source, target)])
                for source, target in expected - decided
            ),
            key=lambda item: (-item.import_sites, item.source, item.target),
        )
    )


def all_open_decisions(observation: Observation) -> tuple[OpenDecision, ...]:
    """Every decision the contract still owes: between components (AD-15) and inside one (AD-31).

    One owner for the complete set, so `validate`'s diagnostics, its JSON array, `report` and a
    report rendered later from `architecture.json` bytes cannot disagree about what is open.
    """
    return (*open_decisions(observation), *open_inner_decisions(observation))


def identifier(label: str) -> str:
    return label.upper().replace("_", "-")


def agent_decisions(observation: Observation) -> tuple[int, int]:
    """Count rule declarations `decided_by` the agent against every rule declaration (AD-16).

    Reads the analyzer's own projected rule declarations, the same evidence `open_decisions`
    reads, so validation and a report rendered later from `architecture.json` bytes alone
    share one derivation with no second contract read.
    """
    declared_rules = [
        record for record in observation.records("declarations") or () if record.kind in _RULE_KINDS
    ]
    agent = sum(record.data.get("decided_by") == "agent" for record in declared_rules)
    return agent, len(declared_rules)


def dependency_rule_ids(source: str, target: str) -> tuple[str, str]:
    """Return the `(forbidden, allowed)` rule ids AD-15 gives one directed component pair.

    The only owner of this id scheme: `init`, every open-decision option, and a
    hand-written `forbidden_dependency` or `allowed_dependency` rule all agree with this
    function by construction, never by convention.
    """
    return (
        f"DEP-{identifier(source)}-NO-{identifier(target)}",
        f"DEP-{identifier(source)}-ALLOWS-{identifier(target)}",
    )
