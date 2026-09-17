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

from .bindings import unread_bindings
from .duplication import repeated_logic
from .interfaces import component_owners, owner_of
from .model import (
    AllowedDependencyRule,
    ArchitectureRule,
    ComparisonStatus,
    ForbiddenDependencyRule,
    Observation,
    OpenDecision,
    Record,
    ReviewClaims,
    package_owners,
)
from .references import unreferenced_symbols
from .structure import oversized_insides

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


def _decides_this_level(record: Record) -> bool:
    """False for a rule a component's inside declares: it decides that level's pairs, not these.

    The parent id is the signal the analyzer writes on every inside record (AD-36); reading the
    rule id's prefix instead would decide behaviour from a name.
    """
    return record.data.get("parent_id") is None


def _decided_component_pairs(
    observation: Observation, owners: dict[str, str]
) -> set[tuple[str, str]]:
    """Pairs a `forbidden_dependency` or `allowed_dependency` rule decides.

    Exact package match only, like validation's own `_decided_pairs`: a rule scoped to a
    submodule or a `target_symbol` narrows a rule, it does not decide the component pair.
    """
    decided: set[tuple[str, str]] = set()
    for record in observation.records("declarations") or ():
        if record.kind not in _DECIDING_KINDS or not _decides_this_level(record):
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


def requires_declared(observation: Observation) -> bool:
    """True when a `complete_requires` rule decides every component pair by absence (AD-32)."""
    return any(
        record.kind == "complete_requires" and _decides_this_level(record)
        for record in observation.records("declarations") or ()
    )


def open_decisions(
    observation: Observation,
    components: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
) -> tuple[OpenDecision, ...]:
    """Derive undecided component pairs, heaviest observed edges first (AD-15).

    `components` lets `init` supply the components it just drafted, before any contract
    declares them; `validate` and a report rendered later from `architecture.json` bytes
    pass none and read the observation's own declared components instead.

    A contract carrying `complete_requires` owes no pair decision at all: there absence
    forbids, so an unlisted pair is decided rather than open (AD-32).
    """
    if requires_declared(observation):
        return ()
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


def identifier(label: str) -> str:
    return label.upper().replace("_", "-")


def agent_decisions(observation: Observation) -> tuple[int, int]:
    """Count rule declarations `decided_by` the agent against every rule declaration (AD-16).

    Reads the analyzer's own projected rule declarations, the same evidence `open_decisions`
    reads, so validation and a report rendered later from `architecture.json` bytes alone
    share one derivation with no second contract read. A rule an inside declares counts here,
    unlike in the pair derivations above: it is a decision somebody made, whichever level it
    governs, and an agent decision nobody reviewed is no less unreviewed one level down.
    """
    declared_rules = [
        record for record in observation.records("declarations") or () if record.kind in _RULE_KINDS
    ]
    agent = sum(record.data.get("decided_by") == "agent" for record in declared_rules)
    return agent, len(declared_rules)


def _named(status: ComparisonStatus, candidates: tuple[object, ...]) -> int | None:
    """An unsupported claim names nothing, which is not the same as finding nothing (AD-5)."""
    return len(candidates) if status == "SUPPORTED" else None


def review_claims(observation: Observation) -> ReviewClaims:
    """Count every review claim once, so terminal, JSON and page cannot disagree (AD-35).

    Derived here beside `agent_decisions` and `open_decisions`, the other counts a result
    carries, so a report rendered later from `architecture.json` bytes alone still agrees.
    """
    symbols = unreferenced_symbols(observation)
    insides = oversized_insides(observation)
    bindings = unread_bindings(observation)
    logic = repeated_logic(observation)
    return ReviewClaims(
        _named(symbols.status, symbols.candidates),
        _named(insides.status, insides.candidates),
        _named(bindings.status, bindings.candidates),
        _named(logic.status, logic.candidates),
    )


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
