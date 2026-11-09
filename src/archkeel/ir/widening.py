# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Classify a contract's difference from a prior revision as widening or narrowing (#11).

A target contract is only a specification if it cannot quietly move toward the code. This
module enumerates, per rule kind and per component field, which difference widens the
contract (a new permission or a dropped restriction) and which narrows it (the reverse); a
rationale or provenance text is the one kind of difference the design calls neutral. It fails
closed: a difference no classifier below recognises — an unrecognised rule kind's presence, a
field no set-based or boolean rule names — is reported as a widening rather than passed over,
because a silent "neutral" here is exactly the hole issue #11 is filed against. `check` reads
both contract revisions with `check/git.py` and hands them to
`contract_widening_changes`, which stays a pure function over two `ArchitectureContract` values,
the way `ir.baseline` derives a
fingerprint without reading Git itself. This module owns the component and declaration
classifiers and re-exports the rule and ratchet classifiers of `ir.widening_rules` and
`ir.widening_ratchet`.
"""

from __future__ import annotations

import builtins as _builtins
from dataclasses import replace

from .amendment import AMENDMENT_SCHEMA_VERSION as AMENDMENT_SCHEMA_VERSION
from .amendment import Amendment as Amendment
from .amendment import verify_amendment as verify_amendment
from .model import (
    ArchitectureContract,
    CompatibilityLifetime,
    ContractComponent,
    ContractDeclarations,
    RequiredComponent,
    last_name,
    requires_covers,
)
from .widening_change import WideningChange, generic_field_widenings, set_widenings
from .widening_ratchet import baseline_widening_changes as baseline_widening_changes
from .widening_ratchet import baseline_widenings as baseline_widenings
from .widening_ratchet import measurement_budget_changes as measurement_budget_changes
from .widening_ratchet import measurement_budget_widenings as measurement_budget_widenings
from .widening_rules import PERMISSION_RULE_KINDS, RESTRICTION_RULE_KINDS, rules_widenings

__all__ = (
    "AMENDMENT_SCHEMA_VERSION",
    "Amendment",
    "verify_amendment",
    "WideningChange",
    "contract_narrowing_changes",
    "contract_widening_changes",
    "baseline_widening_changes",
    "measurement_budget_changes",
    "contract_widenings",
    "baseline_widenings",
    "measurement_budget_widenings",
)


def _requires_widenings(
    subject: str, before: tuple[RequiredComponent, ...], after: tuple[RequiredComponent, ...]
) -> list[WideningChange]:
    # A component may be required by several entries, so entries are compared as a set, never
    # keyed by component: a new entry widens unless the same author already permitted its
    # imports to the same target (AD-245); a removed entry is a narrowing, not reported.
    before_entries = {(item.component, item.through, item.decided_by) for item in before}
    before_components = {item.component for item in before}
    findings: list[WideningChange] = []
    for name, through, decided_by in sorted(
        {
            (item.component, item.through, item.decided_by)
            for item in after
            if not _contained(item, before)
        }
        - before_entries,
        key=repr,
    ):
        findings.append(
            WideningChange(
                subject,
                "requires",
                f"{subject}.requires gained an edge to {name!r}"
                if name not in before_components
                else f"{subject}.requires[{name!r}] gained an entry through {list(through)}"
                + ("" if decided_by is None else f", decided by {decided_by}"),
            )
        )
    return findings


def _effective_requires(component: ContractComponent) -> tuple[RequiredComponent, ...]:
    """Entries with the author they inherit from their component when they name none (AD-50)."""
    return tuple(
        replace(item, decided_by=item.decided_by or component.decided_by)
        for item in component.requires or ()
    )


def _contained(entry: RequiredComponent, before: tuple[RequiredComponent, ...]) -> bool:
    """Whether `before` already let the same author import everything `entry` permits."""
    same = tuple(
        item
        for item in before
        if item.component == entry.component and item.decided_by == entry.decided_by
    )
    if not entry.through:
        return any(not item.through for item in same)
    return all(
        requires_covers(same, entry.component, module, symbol or None)
        for module, _, symbol in (
            _builtins.str.partition(selector, ":") for selector in entry.through
        )
    )


def _namespace_widenings(
    subject: str, before: str | None, after: str | None
) -> list[WideningChange]:
    """A namespace adds a placement restriction; removing or changing it widens."""
    if before is None and after is not None:
        return []
    if before != after:
        return [
            WideningChange(
                subject, "namespace", f"{subject}.namespace changed from {before!r} to {after!r}"
            )
        ]
    return []


def _component_widenings(
    before: ContractComponent, after: ContractComponent
) -> list[WideningChange]:
    subject = f"component {before.label!r}"
    before_public = frozenset(before.public or ())
    after_public = frozenset(after.public or ())
    before_planned = frozenset(before.planned or ())
    after_planned = frozenset(after.planned or ())
    promoted = (before_planned - after_planned) & after_public
    gained = after_public - before_public - promoted
    lost = before_public - after_public
    return [
        *[
            WideningChange(
                subject,
                "public",
                f"{subject}.public gained {item!r}{_in_place_of(item, gained, lost)}",
            )
            for item in sorted(gained)
        ],
        *[
            WideningChange(subject, "planned", f"{subject}.planned lost {item!r}")
            for item in sorted(before_planned - after_planned - promoted)
        ],
        *_requires_widenings(subject, _effective_requires(before), _effective_requires(after)),
        *_namespace_widenings(subject, before.namespace, after.namespace),
        *generic_field_widenings(
            subject,
            before,
            after,
            handled=frozenset({"public", "planned", "requires", "namespace"}),
        ),
    ]


def _alike(entry: str, other: str) -> bool:
    """Both entries modules or both symbols, with the same last name."""
    return (":" in entry) == (":" in other) and last_name(entry) == last_name(other)


def _in_place_of(entry: str, gained: frozenset[str], lost: frozenset[str]) -> str:
    """Name the lost entry `entry` may replace, for the reader only (#151).

    Only a one-to-one pair counts: one lost entry alike `entry`, and no other gain alike it. A
    lost `public` entry is a narrowing and fails nothing; beside the gain that may replace it,
    it tells a moved entry from a new one where no rename was recognised (AD-105).
    """
    matches = [item for item in lost if _alike(entry, item)]
    if len(matches) != 1 or [item for item in gained if _alike(item, matches[0])] != [entry]:
        return ""
    return f" in place of {matches[0]!r}"


def _components_widenings(
    before: tuple[ContractComponent, ...], after: tuple[ContractComponent, ...]
) -> list[WideningChange]:
    before_map = {item.id: item for item in before}
    after_map = {item.id: item for item in after}
    findings = [
        WideningChange(
            f"component {after_map[cid].label!r}",
            "presence",
            f"component {after_map[cid].label!r} added",
        )
        for cid in sorted(set(after_map) - set(before_map))
    ]
    findings += [
        WideningChange(
            f"component {before_map[cid].label!r}",
            "presence",
            f"component {before_map[cid].label!r} removed",
        )
        for cid in sorted(set(before_map) - set(after_map))
    ]
    for cid in sorted(set(before_map) & set(after_map)):
        findings += _component_widenings(before_map[cid], after_map[cid])
    return findings


def contract_widening_changes(
    before: ArchitectureContract, after: ArchitectureContract
) -> tuple[WideningChange, ...]:
    """Every difference from `before` to `after` that issue #11 requires an amendment for.

    Only a set-based or boolean field this module explicitly classifies as a removal, and
    `_ALWAYS_NEUTRAL` (rationale, provenance, and the id/kind two entries are matched by),
    produce no finding. Everything else — an unrecognised rule kind's presence, a field no
    classifier names, `declarations` or `$schema` — is reported, never silently accepted.
    """
    findings = [
        *_components_widenings(before.components, after.components),
        *rules_widenings(before.rules, after.rules),
    ]
    if before.schema != after.schema:
        findings.append(
            WideningChange(
                "contract",
                "$schema",
                f"contract.$schema changed from {before.schema!r} to {after.schema!r}",
            )
        )
    before_declarations = before.declarations or ContractDeclarations()
    after_declarations = after.declarations or ContractDeclarations()
    findings += set_widenings(
        "contract.declarations",
        "measurement_budgets",
        frozenset(item.name for item in before_declarations.measurement_budgets),
        frozenset(item.name for item in after_declarations.measurement_budgets),
        grows_widens=False,
    )
    findings += _ceiling_widenings(
        "facade budget",
        {item.subject: item.max_names for item in before_declarations.facade_budgets or ()},
        {item.subject: item.max_names for item in after_declarations.facade_budgets or ()},
    )
    findings += _ceiling_widenings(
        "coupling budget",
        {item.subject: item.max_names for item in before_declarations.coupling_budgets or ()},
        {item.subject: item.max_names for item in after_declarations.coupling_budgets or ()},
    )
    if _unenumerated(before_declarations) != _unenumerated(after_declarations):
        findings.append(
            WideningChange(
                "contract.declarations",
                "declarations",
                "contract.declarations changed in a way this comparison does not enumerate",
            )
        )
    before_compat = {item.module: item for item in before_declarations.compat}
    after_compat = {item.module: item for item in after_declarations.compat}
    findings.extend(
        WideningChange(
            f"compat module {after_compat[module].module!r}",
            "presence",
            f"compat module {after_compat[module].module!r} added",
        )
        for module in sorted(set(after_compat) - set(before_compat))
    )
    for module in sorted(set(before_compat) & set(after_compat)):
        old, new = before_compat[module], after_compat[module]
        if old.target != new.target:
            findings.append(
                WideningChange(
                    f"compat module {module!r}",
                    "target",
                    f"compat module {module!r} changed from {old.target!r} to {new.target!r}",
                )
            )
        if old.lifetime != new.lifetime and new.lifetime == CompatibilityLifetime.PERMANENT:
            findings.append(
                WideningChange(
                    f"compat module {module!r}",
                    "lifetime",
                    f"compat module {module!r} lifetime became permanent",
                )
            )
    return tuple(sorted(findings, key=lambda item: item.message))


def _requires_narrowings(
    subject: str, before: tuple[RequiredComponent, ...], after: tuple[RequiredComponent, ...]
) -> list[WideningChange]:
    """Per target and author: entries that went away, folded with contained replacements."""
    before_entries = {(item.component, item.through, item.decided_by) for item in before}
    after_entries = {(item.component, item.through, item.decided_by) for item in after}
    findings: list[WideningChange] = []
    for name, decided_by in sorted(
        {(item.component, item.decided_by) for item in before}, key=repr
    ):
        removed = [
            list(item.through)
            for item in before
            if (item.component, item.decided_by) == (name, decided_by)
            and (item.component, item.through, item.decided_by) not in after_entries
            and not _contained(item, after)
        ]
        contained = [
            list(item.through)
            for item in after
            if (item.component, item.decided_by) == (name, decided_by)
            and (item.component, item.through, item.decided_by) not in before_entries
            and _contained(item, before)
        ]
        # Only a removed permission narrows; a contained entry beside it is its replacement.
        if removed and contained:
            findings.append(
                WideningChange(
                    subject,
                    "requires",
                    f"{subject}.requires[{name!r}] narrowed from {removed} to {contained}",
                )
            )
        elif removed:
            findings.append(
                WideningChange(
                    subject, "requires", f"{subject}.requires[{name!r}] dropped through {removed}"
                )
            )
    return findings


def contract_narrowing_changes(
    before: ArchitectureContract, after: ArchitectureContract
) -> tuple[WideningChange, ...]:
    """What `after` no longer allows that `before` did, for the kinds AD-255 enumerates."""
    findings: list[WideningChange] = []
    before_components = {item.id: item for item in before.components}
    for component in after.components:
        old = before_components.get(component.id)
        if old is None:
            continue
        subject = f"component {component.label!r}"
        findings += [
            WideningChange(subject, "public", f"{subject}.public lost {entry!r}")
            for entry in sorted(frozenset(old.public or ()) - frozenset(component.public or ()))
        ]
        findings += _requires_narrowings(
            subject, _effective_requires(old), _effective_requires(component)
        )
    before_rules = {rule.id: rule for rule in before.rules}
    after_rules = {rule.id: rule for rule in after.rules}
    findings += [
        WideningChange(
            f"rule {rule_id}", "presence", f"rule {rule_id} ({after_rules[rule_id].kind}) added"
        )
        for rule_id in sorted(set(after_rules) - set(before_rules))
        if after_rules[rule_id].kind in RESTRICTION_RULE_KINDS
    ]
    findings += [
        WideningChange(
            f"rule {rule_id}", "presence", f"rule {rule_id} ({before_rules[rule_id].kind}) removed"
        )
        for rule_id in sorted(set(before_rules) - set(after_rules))
        if before_rules[rule_id].kind in PERMISSION_RULE_KINDS
    ]
    return tuple(sorted(findings, key=lambda item: item.message))


def contract_widenings(
    before: ArchitectureContract, after: ArchitectureContract
) -> tuple[str, ...]:
    """Backward-compatible rendered contract widening messages."""
    return tuple(item.message for item in contract_widening_changes(before, after))


def _unenumerated(declarations: ContractDeclarations) -> ContractDeclarations:
    """The declarations no classifier above compares field by field."""
    return replace(
        declarations, compat=(), measurement_budgets=(), facade_budgets=None, coupling_budgets=None
    )


def _ceiling_widenings(
    kind: str, before: dict[str, int], after: dict[str, int]
) -> list[WideningChange]:
    """AD-99: a raised or removed ceiling widens; a lowered or added one narrows."""
    findings = []
    for subject in sorted(before):
        if subject not in after:
            findings.append(WideningChange(subject, "presence", f"{kind} {subject} removed"))
        elif after[subject] > before[subject]:
            findings.append(
                WideningChange(
                    subject,
                    "max_names",
                    f"{kind} {subject} raised from {before[subject]} to {after[subject]}",
                )
            )
    return findings
