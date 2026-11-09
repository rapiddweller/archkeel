# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Say UNKNOWN for a Rust scope that needs the edges inside a crate (AD-335).

The Rust collector writes the edges between crates, not the edges between the modules of one
crate. A component or a rule that names a module below a crate root would read "no edge" as "no
import", and PASS. Until slice 5b-2 writes the module edges, each such scope is UNKNOWN.

`EDGE_FIELDS` lists, for each rule kind that reads edges, the fields that name a module or a
component. `NO_INTERNAL_EDGES` lists the kinds that read no edge inside a crate. A rule kind in
neither list, and not unsupported by the profile, fails `tests/test_crate_scope_catalog.py`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict

from archkeel.ir.facts import ConstructCapability, EvidenceClass, SourceFacts, stable_id
from archkeel.ir.facts_codec import RawRecord, classified
from archkeel.ir.model import (
    ArchitectureContract,
    CycleLevel,
    NoComponentCyclesRule,
)
from archkeel.ir.model import ArchitectureRuleKind as Kind
from archkeel.ir.profiles import Profile

from .rules import profile_failures

# The fields that name a module (or a prefix of modules) in a rule that reads edges.
EDGE_FIELDS: dict[Kind, tuple[str, ...]] = {
    Kind.FORBIDDEN_DEPENDENCY: ("source", "target", "allowed_sources"),
    Kind.ALLOWED_DEPENDENCY: ("source", "target"),
    Kind.SIBLING_ISOLATION: ("members",),
}
# Rule kinds that read no edge inside a crate: they read components (the component check covers
# them), the files, the external edges, or constructs (which this profile never collects).
NO_INTERNAL_EDGES: frozenset[Kind] = frozenset(
    {
        Kind.COMPLETE_ASSIGNMENT,
        Kind.COMPLETE_EXTERNAL_SCOPE,
        Kind.COMPLETE_REQUIRES,
        Kind.EXTERNAL_DEPENDENCY_SCOPE,
        Kind.FORBIDDEN_CONSTRUCT,
        Kind.LAYER_ORDER,
        Kind.NO_COMPONENT_CYCLES,
        Kind.ROOT_LAYOUT,
    }
)


def _depth(names: Iterable[str]) -> int | None:
    """The dots in a crate root module: the shallowest module of the scan."""
    return min((name.count(".") for name in names), default=None)


def _overlap(first: str, second: str) -> bool:
    return first == second or first.startswith(second + ".") or second.startswith(first + ".")


def _names(value: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return (value,) if isinstance(value, str) else tuple(value)


def _rule_scopes(contract: ArchitectureContract, root: int) -> list[tuple[str, str]]:
    scopes: list[tuple[str, str]] = []
    for rule in contract.rules:
        fields = EDGE_FIELDS.get(Kind(rule.kind), ())
        values = asdict(rule)
        named = [name for field in fields for name in _names(values[field])]
        if any(name.count(".") > root for name in named):
            scopes.append((rule.id, f"rule {rule.kind} below a crate root"))
        elif rule.kind in {Kind.FORBIDDEN_DEPENDENCY, Kind.SIBLING_ISOLATION} and any(
            _overlap(a, b) for i, a in enumerate(named) for b in named[i + 1 :]
        ):
            scopes.append((rule.id, f"rule {rule.kind} that covers the modules of a crate"))
        if isinstance(rule, NoComponentCyclesRule) and rule.level is CycleLevel.MODULE:
            scopes.append((rule.id, "module cycles"))
    return scopes


def _crate_scopes(
    contract: ArchitectureContract, profile: Profile, names: Iterable[str]
) -> list[RawRecord]:
    root = _depth(names)
    if not profile.crate_edges_only or root is None:
        return []
    scopes = [
        (component.id, f"component {component.label} below a crate root")
        for component in contract.components
        if any(
            name.count(".") > root
            for name in (*component.packages, *(component.exact_modules or ()))
        )
    ]
    scopes += _rule_scopes(contract, root)
    return [
        classified(
            item_id=stable_id("UNKNOWN-CRATE-SCOPE", subject, what),
            evidence_class=EvidenceClass.UNKNOWN,
            area="analysis_coverage",
            kind="rule-unsupported-by-profile",
            title=f"{subject}: {what} is not supported by the {profile.analyzer} profile "
            "(edges inside a crate are not collected)",
            subjects=[subject],
            rule_ids=[],
            data={"analyzer": profile.analyzer},
        )
        for subject, what in scopes
    ]


def root_limits(
    contract: ArchitectureContract, profile: Profile, facts: SourceFacts
) -> list[RawRecord]:
    """The profile limits (AD-97) of the root contract, and the crate scope limits."""
    return [
        *profile_failures(contract, profile, facts.capabilities.constructs),
        *_crate_scopes(contract, profile, (item.module for item in facts.files)),
    ]


def inside_limits(
    contract: ArchitectureContract,
    profile: Profile,
    constructs: tuple[ConstructCapability, ...],
    modules: Iterable[RawRecord],
) -> list[RawRecord]:
    """The same limits for the contract that a component declares for its inside."""
    names = [item["data"]["qualified_name"] for item in modules]
    return [
        *profile_failures(contract, profile, constructs),
        *_crate_scopes(contract, profile, names),
    ]
