# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Closed world validation diagnostics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import TypeVar

from archkeel.ir.decisions import open_decisions
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    Diagnostic,
    DiagnosticCode,
    ForbiddenDependencyRule,
    Observation,
    declared_package_pair,
)

from .diagnostics import _diagnostic


def observed_component_edges(
    contract: ArchitectureContract, observation: Observation
) -> frozenset[tuple[str, str]]:
    """Project module imports onto declared component labels."""
    edges: set[tuple[str, str]] = set()
    for record in observation.records("imports") or ():
        source_module = record.data.get("source_module")
        target_module = record.data.get("target_module")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        source = contract.component_for(source_module)
        target = contract.component_for(target_module)
        if source is not None and target is not None and source != target:
            edges.add((source.label, target.label))
    return frozenset(edges)


_DecisionRule = TypeVar("_DecisionRule", ForbiddenDependencyRule, AllowedDependencyRule)


def _decided_pairs(
    contract: ArchitectureContract, rule_type: type[_DecisionRule]
) -> list[tuple[str, str]]:
    """Return whole-pair rules whose endpoints name unique declared packages."""
    components = tuple(
        (component.label, component.packages, component.exact_modules or ())
        for component in contract.components
    )
    pairs = []
    for rule in contract.rules:
        if not isinstance(rule, rule_type):
            continue
        target_symbol = rule.target_symbol if isinstance(rule, ForbiddenDependencyRule) else None
        pair = declared_package_pair(rule.source, rule.target, target_symbol, components)
        if pair is not None:
            pairs.append(pair)
    return pairs


def target_component_edges(contract: ArchitectureContract) -> frozenset[tuple[str, str]]:
    """The component pairs the contract permits, for `<!-- archkeel-target-graph -->` (AD-57).

    A contract states a pair may exist in one of two ways: a `requires` entry, AD-32's
    intentional grant, absence of which `complete_requires` forbids; or an `allowed_dependency`
    rule, AD-15's closed-world grant, where every pair is decided one way or the other. Both
    name a permitted pair, so the target draws their union - one rule, not a branch on which
    system a contract adopted. In practice a contract writes one or the other: a `requires`-based
    contract carries no coarse `allowed_dependency` pair and a pair-decided one carries no
    `requires` entry, so the union reduces to whichever the contract actually wrote, and a
    contract that has adopted neither permits nothing yet - the target graph is then empty.
    """
    requires_edges = {
        (component.label, entry.component)
        for component in contract.components
        for entry in component.requires or ()
    }
    return frozenset(requires_edges) | frozenset(_decided_pairs(contract, AllowedDependencyRule))


def _pair_diagnostics(
    code: DiagnosticCode, pairs: Iterable[tuple[str, str]], claim: str, remedy: str
) -> list[Diagnostic]:
    return [
        _diagnostic(code, "/rules", f"{source} -> {target}", claim, remedy)
        for source, target in pairs
    ]


def _open_decision_diagnostics(observation: Observation) -> list[Diagnostic]:
    decisions = open_decisions(observation)
    if not decisions:
        return []
    return [
        _diagnostic(
            "decision.open",
            "/components",
            f"{len(decisions)} open dependency decision{'s' if len(decisions) != 1 else ''}",
            "Component dependency directions remain undecided.",
            "Review open_decisions. Add each allowed component to its owner's requires list "
            "with a rationale and decided_by; add one complete_requires rule with a unique id, "
            "rationale, provenance and decided_by to forbid absent pairs. "
            "Do not infer permission from existing imports. See docs/onboarding.md.",
        )
    ]


def closed_world_diagnostics(
    contract: ArchitectureContract, observation: Observation
) -> tuple[Diagnostic, ...]:
    """Require each ordered component pair to be a decision, and each decision unique (AD-15)."""
    observed = observed_component_edges(contract, observation)
    forbidden_items = _decided_pairs(contract, ForbiddenDependencyRule)
    allowed_items = _decided_pairs(contract, AllowedDependencyRule)
    forbidden = set(forbidden_items)
    allowed = set(allowed_items)
    diagnostics = _open_decision_diagnostics(observation)
    diagnostics.extend(
        _pair_diagnostics(
            "closed_world.observed_forbidden",
            sorted(observed & forbidden),
            "An observed component dependency is also forbidden.",
            "Remove the dependency or correct the forbidden_dependency rule.",
        )
    )
    diagnostics.extend(
        _pair_diagnostics(
            "closed_world.duplicate",
            sorted(pair for pair, count in Counter(forbidden_items).items() if count > 1),
            "The component pair has duplicate forbidden_dependency rules.",
            "Keep one forbidden_dependency rule for this ordered component pair.",
        )
    )
    diagnostics.extend(
        _pair_diagnostics(
            "closed_world.duplicate",
            sorted(pair for pair, count in Counter(allowed_items).items() if count > 1),
            "The component pair has duplicate allowed_dependency rules.",
            "Keep one allowed_dependency rule for this ordered component pair.",
        )
    )
    diagnostics.extend(
        _pair_diagnostics(
            "decision.conflict",
            sorted(allowed & forbidden),
            "The component pair has both an allowed_dependency and a forbidden_dependency rule.",
            "Keep only one decision for this ordered component pair.",
        )
    )
    return tuple(diagnostics)
