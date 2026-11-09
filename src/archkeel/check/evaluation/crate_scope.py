# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Say UNKNOWN for a Rust scope below a crate root (AD-335).

The Rust collector writes the edges between crates, not the edges between the modules of one
crate. A component or a rule that names a module below a crate root would read "no edge" as
"no import", and PASS. Until slice 5b-2 writes the module edges, each such scope is UNKNOWN.
"""

from __future__ import annotations

from archkeel.ir.facts import EvidenceClass, SourceFacts, stable_id
from archkeel.ir.facts_codec import RawRecord, classified
from archkeel.ir.model import (
    AllowedDependencyRule,
    ArchitectureContract,
    CycleLevel,
    ForbiddenDependencyRule,
    NoComponentCyclesRule,
)
from archkeel.ir.profiles import Profile

from .rules import profile_failures


def _below(name: str, namespace: str) -> bool:
    """Whether a dotted name is a module below a crate root: namespace, crate, then more."""
    return name.startswith(namespace + ".") and name.count(".") > namespace.count(".") + 1


def limits_of(
    contract: ArchitectureContract, profile: Profile, facts: SourceFacts, namespace: str
) -> list[RawRecord]:
    """The profile limits (AD-97), and one UNKNOWN record for each scope inside a crate."""
    return [
        *profile_failures(contract, profile, facts.capabilities.constructs),
        *_crate_scopes(contract, profile, namespace),
    ]


def _crate_scopes(
    contract: ArchitectureContract, profile: Profile, namespace: str
) -> list[RawRecord]:
    if not profile.crate_edges_only:
        return []
    scopes: list[tuple[str, list[str], str]] = [
        (component.id, [], f"component {component.label} below a crate root")
        for component in contract.components
        if any(_below(package, namespace) for package in component.packages)
        or any(_below(module, namespace) for module in component.exact_modules or ())
    ]
    for rule in contract.rules:
        if isinstance(rule, ForbiddenDependencyRule | AllowedDependencyRule) and (
            _below(rule.source, namespace) or _below(rule.target, namespace)
        ):
            scopes.append((rule.id, [rule.id], f"rule {rule.kind} below a crate root"))
        if isinstance(rule, NoComponentCyclesRule) and rule.level is CycleLevel.MODULE:
            scopes.append((rule.id, [rule.id], "module cycles"))
    return [
        classified(
            item_id=stable_id("UNKNOWN-CRATE-SCOPE", subject),
            evidence_class=EvidenceClass.UNKNOWN,
            area="analysis_coverage",
            kind="rule-unsupported-by-profile",
            title=f"{subject}: {what} is not supported by the {profile.analyzer} profile "
            "(edges inside a crate are not collected)",
            subjects=[subject],
            rule_ids=rule_ids,
            data={"analyzer": profile.analyzer},
        )
        for subject, rule_ids, what in scopes
    ]
