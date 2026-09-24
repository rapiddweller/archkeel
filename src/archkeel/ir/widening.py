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
both contract revisions with `check/git.py` and hands them to `contract_widenings`, which stays
a pure function over two `ArchitectureContract` values, the way `ir.baseline` derives a
fingerprint without reading Git itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from dataclasses import fields as dataclass_fields
from typing import Any, ClassVar, Final, Protocol

from .baseline import KnownViolation
from .measurements import MeasurementBudget, name_drift
from .model import (
    AllowedDependencyRule,
    ArchitectureContract,
    ArchitectureRule,
    BoundaryTypesRule,
    CompleteAssignmentRule,
    CompleteExternalScopeRule,
    CompleteRequiresRule,
    ContractComponent,
    ContractDeclarations,
    ExternalDependencyScopeRule,
    ForbiddenConstructRule,
    ForbiddenDependencyRule,
    InterfaceBoundaryRule,
    NoComponentCyclesRule,
    RequiredComponent,
    RootLayoutRule,
    SiblingIsolationRule,
)


class _DataclassInstance(Protocol):
    """Structural stand-in for `_typeshed.DataclassInstance`, itself an external dependency."""

    __dataclass_fields__: ClassVar[dict[str, Any]]


AMENDMENT_SCHEMA_VERSION = "1.0.0"

# Rationale and provenance are the design's own "neutral" prose; `id` and `kind` are the keys
# these classifiers match entries by, never content to diff themselves.
_ALWAYS_NEUTRAL: Final = frozenset({"id", "kind", "rationale", "provenance"})

# AllowedDependencyRule alone grants an edge; every other kind restricts something (AD-15).
_PERMISSION_RULE_KINDS: Final = frozenset({"allowed_dependency"})
_RESTRICTION_RULE_KINDS: Final = frozenset(
    {
        "forbidden_dependency",
        "forbidden_construct",
        "external_dependency_scope",
        "complete_assignment",
        "root_layout",
        "complete_external_scope",
        "complete_requires",
        "no_component_cycles",
        "interface_boundary",
        "sibling_isolation",
        "symbol_placement",
        "boundary_types",
    }
)


@dataclass(frozen=True, slots=True)
class Amendment:
    """A recorded decision to widen the contract from one exact revision to another (#11).

    Binding both digests, rather than only `after`, is what AD-52's baseline does not do for
    itself: an amendment written for one change must not silently authorise a different one.
    `decided_by` and `rationale` are free text, checked for non-emptiness only, the way a
    rule's own `rationale` is: this module has no way to judge whether a reason is a good one.
    """

    before_digest: str
    after_digest: str
    decided_by: str
    rationale: str


def verify_amendment(amendment: Amendment, *, before_digest: str, after_digest: str) -> bool:
    """True when `amendment` was written for exactly this before/after contract pair."""
    return amendment.before_digest == before_digest and amendment.after_digest == after_digest


def _set_widenings(
    label: str, before: frozenset[str], after: frozenset[str], *, grows_widens: bool
) -> list[str]:
    """One field's added/removed entries, reporting only the direction that widens it."""
    if grows_widens:
        return [f"{label} gained {item!r}" for item in sorted(after - before)]
    return [f"{label} lost {item!r}" for item in sorted(before - after)]


def _include_type_checking_widening(subject: str, before: bool, after: bool) -> list[str]:
    """A rule that stops covering type-checking-only imports is weakened, not strengthened."""
    if before and not after:
        return [f"{subject}.include_type_checking relaxed from true to false"]
    return []


def _generic_field_widenings(
    subject: str, before: _DataclassInstance, after: _DataclassInstance, *, handled: frozenset[str]
) -> list[str]:
    """Fail closed: any field neither neutral nor already classified is a widening if it differs.

    `handled` names the fields a set-based or boolean classifier already covered for this
    dataclass type. Everything else — an unenumerated field on a known kind, or the entire
    shape of a kind this module has no classifier for — falls through to here, which is what
    makes the "no diagnosis is treated as widening" test in tests/test_widening.py hold: two
    contracts differing only in a field this function does not name still report widening.
    """
    findings = []
    skip = _ALWAYS_NEUTRAL | handled
    # dataclasses.asdict, not a per-field getattr: the same construct CONSTRUCT-NO-DYNAMIC
    # forbids elsewhere in this codebase, avoided here for its own sake, not only self-checked.
    before_values = asdict(before)
    after_values = asdict(after)
    for field in dataclass_fields(before):
        if field.name in skip:
            continue
        before_value = before_values[field.name]
        after_value = after_values[field.name]
        if before_value != after_value:
            findings.append(
                f"{subject}.{field.name} changed from {before_value!r} to {after_value!r}"
            )
    return findings


def _rule_presence_widening(rule: ArchitectureRule, *, added: bool) -> list[str]:
    verb = "added" if added else "removed"
    if rule.kind in _PERMISSION_RULE_KINDS:
        widens = added
    elif rule.kind in _RESTRICTION_RULE_KINDS:
        widens = not added
    else:
        # Fail closed: a rule kind this module does not enumerate is never assumed to be a
        # restriction, so its presence changing in either direction is reported.
        widens = True
    return [f"rule {rule.id} ({rule.kind}) {verb}"] if widens else []


def _forbidden_dependency_widenings(
    subject: str, before: ForbiddenDependencyRule, after: ForbiddenDependencyRule
) -> list[str]:
    return [
        *_set_widenings(
            f"{subject}.allowed_sources",
            frozenset(before.allowed_sources),
            frozenset(after.allowed_sources),
            grows_widens=True,
        ),
        *_include_type_checking_widening(
            subject, before.include_type_checking, after.include_type_checking
        ),
        *_generic_field_widenings(
            subject, before, after, handled=frozenset({"allowed_sources", "include_type_checking"})
        ),
    ]


def _forbidden_construct_widenings(
    subject: str, before: ForbiddenConstructRule, after: ForbiddenConstructRule
) -> list[str]:
    return [
        # A construct dropped from the forbidden list is a widening; one added is not.
        *_set_widenings(
            f"{subject}.constructs",
            frozenset(before.constructs),
            frozenset(after.constructs),
            grows_widens=False,
        ),
        *_set_widenings(
            f"{subject}.allowed_sources",
            frozenset(before.allowed_sources),
            frozenset(after.allowed_sources),
            grows_widens=True,
        ),
        *_set_widenings(
            f"{subject}.exact_sources",
            frozenset(before.exact_sources),
            frozenset(after.exact_sources),
            grows_widens=True,
        ),
        *_generic_field_widenings(
            subject,
            before,
            after,
            handled=frozenset({"constructs", "allowed_sources", "exact_sources"}),
        ),
    ]


def _external_dependency_scope_widenings(
    subject: str, before: ExternalDependencyScopeRule, after: ExternalDependencyScopeRule
) -> list[str]:
    return [
        *_set_widenings(
            f"{subject}.allowed_sources",
            frozenset(before.allowed_sources),
            frozenset(after.allowed_sources),
            grows_widens=True,
        ),
        *_set_widenings(
            f"{subject}.exact_sources",
            frozenset(before.exact_sources),
            frozenset(after.exact_sources),
            grows_widens=True,
        ),
        *_generic_field_widenings(
            subject, before, after, handled=frozenset({"allowed_sources", "exact_sources"})
        ),
    ]


def _sibling_isolation_widenings(
    subject: str, before: SiblingIsolationRule, after: SiblingIsolationRule
) -> list[str]:
    return [
        # Fewer isolated members means less is kept apart: a widening, not a narrowing.
        *_set_widenings(
            f"{subject}.members",
            frozenset(before.members),
            frozenset(after.members),
            grows_widens=False,
        ),
        *_include_type_checking_widening(
            subject, before.include_type_checking, after.include_type_checking
        ),
        *_generic_field_widenings(
            subject, before, after, handled=frozenset({"members", "include_type_checking"})
        ),
    ]


def _boundary_types_widenings(
    subject: str, before: BoundaryTypesRule, after: BoundaryTypesRule
) -> list[str]:
    return [
        f"{subject}.allowed_positions gained {item!r}"
        for item in sorted(
            set(after.allowed_positions) - set(before.allowed_positions),
            key=lambda entry: (
                entry.qualified_name,
                entry.position,
                entry.field_path,
                entry.annotation,
            ),
        )
    ]


def _matched_rule_widenings(before: ArchitectureRule, after: ArchitectureRule) -> list[str]:
    """Dispatch by matched rule kind; a kind this module has no branch for falls closed below."""
    subject = f"rule {before.id}"
    if before.kind != after.kind:
        # An id kept across a kind change: neither the permission nor the restriction map
        # still applies, so fail closed rather than guess which side is now safe.
        return [f"{subject} changed kind from {before.kind} to {after.kind}"]
    if isinstance(before, ForbiddenDependencyRule) and isinstance(after, ForbiddenDependencyRule):
        return _forbidden_dependency_widenings(subject, before, after)
    if isinstance(before, AllowedDependencyRule) and isinstance(after, AllowedDependencyRule):
        return _generic_field_widenings(subject, before, after, handled=frozenset())
    if isinstance(before, ForbiddenConstructRule) and isinstance(after, ForbiddenConstructRule):
        return _forbidden_construct_widenings(subject, before, after)
    if isinstance(before, ExternalDependencyScopeRule) and isinstance(
        after, ExternalDependencyScopeRule
    ):
        return _external_dependency_scope_widenings(subject, before, after)
    if isinstance(before, CompleteRequiresRule) and isinstance(after, CompleteRequiresRule):
        return [
            *_include_type_checking_widening(
                subject, before.include_type_checking, after.include_type_checking
            ),
            *_generic_field_widenings(
                subject, before, after, handled=frozenset({"include_type_checking"})
            ),
        ]
    if isinstance(before, RootLayoutRule) and isinstance(after, RootLayoutRule):
        return [
            *_set_widenings(
                f"{subject}.allowed_children",
                frozenset(before.allowed_children),
                frozenset(after.allowed_children),
                grows_widens=True,
            ),
            *_generic_field_widenings(
                subject, before, after, handled=frozenset({"allowed_children"})
            ),
        ]
    if isinstance(before, InterfaceBoundaryRule) and isinstance(after, InterfaceBoundaryRule):
        return [
            *_include_type_checking_widening(
                subject, before.include_type_checking, after.include_type_checking
            ),
            *_generic_field_widenings(
                subject, before, after, handled=frozenset({"include_type_checking"})
            ),
        ]
    if isinstance(before, SiblingIsolationRule) and isinstance(after, SiblingIsolationRule):
        return _sibling_isolation_widenings(subject, before, after)
    if isinstance(before, BoundaryTypesRule) and isinstance(after, BoundaryTypesRule):
        return [
            *_boundary_types_widenings(subject, before, after),
            *_generic_field_widenings(
                subject, before, after, handled=frozenset({"allowed_positions"})
            ),
        ]
    if isinstance(before, CompleteAssignmentRule) and isinstance(after, CompleteAssignmentRule):
        return _generic_field_widenings(subject, before, after, handled=frozenset())
    if isinstance(before, CompleteExternalScopeRule) and isinstance(
        after, CompleteExternalScopeRule
    ):
        return _generic_field_widenings(subject, before, after, handled=frozenset())
    if isinstance(before, NoComponentCyclesRule) and isinstance(after, NoComponentCyclesRule):
        return _generic_field_widenings(subject, before, after, handled=frozenset())
    # Fail closed: a rule type this dispatch does not recognise is never assumed safe.
    return (
        [f"{subject} changed in a way this comparison does not enumerate"]
        if before != after
        else []
    )


def _rules_widenings(
    before: tuple[ArchitectureRule, ...], after: tuple[ArchitectureRule, ...]
) -> list[str]:
    before_map = {rule.id: rule for rule in before}
    after_map = {rule.id: rule for rule in after}
    findings: list[str] = []
    for rule_id in sorted(set(after_map) - set(before_map)):
        findings += _rule_presence_widening(after_map[rule_id], added=True)
    for rule_id in sorted(set(before_map) - set(after_map)):
        findings += _rule_presence_widening(before_map[rule_id], added=False)
    for rule_id in sorted(set(before_map) & set(after_map)):
        findings += _matched_rule_widenings(before_map[rule_id], after_map[rule_id])
    return findings


def _requires_widenings(
    subject: str, before: tuple[RequiredComponent, ...], after: tuple[RequiredComponent, ...]
) -> list[str]:
    before_map = {item.component: item for item in before}
    after_map = {item.component: item for item in after}
    findings = [
        f"{subject}.requires gained an edge to {name!r}"
        for name in sorted(set(after_map) - set(before_map))
    ]
    # A requires entry no longer present is a removed permission: narrowing, not reported.
    for name in sorted(set(before_map) & set(after_map)):
        findings += _generic_field_widenings(
            f"{subject}.requires[{name!r}]",
            before_map[name],
            after_map[name],
            handled=frozenset({"component"}),
        )
    return findings


def _namespace_widenings(subject: str, before: str | None, after: str | None) -> list[str]:
    """A namespace adds a placement restriction; removing or changing it widens."""
    if before is None and after is not None:
        return []
    if before != after:
        return [f"{subject}.namespace changed from {before!r} to {after!r}"]
    return []


def _component_widenings(before: ContractComponent, after: ContractComponent) -> list[str]:
    subject = f"component {before.label!r}"
    before_public = frozenset(before.public or ())
    after_public = frozenset(after.public or ())
    before_planned = frozenset(before.planned or ())
    after_planned = frozenset(after.planned or ())
    promoted = (before_planned - after_planned) & after_public
    return [
        *[
            f"{subject}.public gained {item!r}"
            for item in sorted(after_public - before_public - promoted)
        ],
        *[
            f"{subject}.planned lost {item!r}"
            for item in sorted(before_planned - after_planned - promoted)
        ],
        *_requires_widenings(subject, before.requires or (), after.requires or ()),
        *_namespace_widenings(subject, before.namespace, after.namespace),
        *_generic_field_widenings(
            subject,
            before,
            after,
            handled=frozenset({"public", "planned", "requires", "namespace"}),
        ),
    ]


def _components_widenings(
    before: tuple[ContractComponent, ...], after: tuple[ContractComponent, ...]
) -> list[str]:
    before_map = {item.id: item for item in before}
    after_map = {item.id: item for item in after}
    findings = [
        f"component {after_map[cid].label!r} added"
        for cid in sorted(set(after_map) - set(before_map))
    ]
    findings += [
        f"component {before_map[cid].label!r} removed"
        for cid in sorted(set(before_map) - set(after_map))
    ]
    for cid in sorted(set(before_map) & set(after_map)):
        findings += _component_widenings(before_map[cid], after_map[cid])
    return findings


def contract_widenings(
    before: ArchitectureContract, after: ArchitectureContract
) -> tuple[str, ...]:
    """Every difference from `before` to `after` that issue #11 requires an amendment for.

    Only a set-based or boolean field this module explicitly classifies as a removal, and
    `_ALWAYS_NEUTRAL` (rationale, provenance, and the id/kind two entries are matched by),
    produce no finding. Everything else — an unrecognised rule kind's presence, a field no
    classifier names, `declarations` or `$schema` — is reported, never silently accepted.
    """
    findings = [
        *_components_widenings(before.components, after.components),
        *_rules_widenings(before.rules, after.rules),
    ]
    if before.schema != after.schema:
        findings.append(f"contract.$schema changed from {before.schema!r} to {after.schema!r}")
    before_declarations = before.declarations or ContractDeclarations()
    after_declarations = after.declarations or ContractDeclarations()
    findings += _set_widenings(
        "contract.declarations.measurement_budgets",
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
        findings.append("contract.declarations changed in a way this comparison does not enumerate")
    before_compat = {item.module: item for item in before_declarations.compat}
    after_compat = {item.module: item for item in after_declarations.compat}
    findings.extend(
        f"compat module {after_compat[module].module!r} added"
        for module in sorted(set(after_compat) - set(before_compat))
    )
    for module in sorted(set(before_compat) & set(after_compat)):
        old, new = before_compat[module], after_compat[module]
        if old.target != new.target:
            findings.append(
                f"compat module {module!r} changed from {old.target!r} to {new.target!r}"
            )
        if old.lifetime == "migration" and new.lifetime == "permanent":
            findings.append(f"compat module {module!r} lifetime became permanent")
    return tuple(sorted(findings))


def _unenumerated(declarations: ContractDeclarations) -> ContractDeclarations:
    """The declarations no classifier above compares field by field."""
    return replace(
        declarations, compat=(), measurement_budgets=(), facade_budgets=None, coupling_budgets=None
    )


def _ceiling_widenings(kind: str, before: dict[str, int], after: dict[str, int]) -> list[str]:
    """AD-99: a raised or removed ceiling widens; a lowered or added one narrows."""
    findings = []
    for subject in sorted(before):
        if subject not in after:
            findings.append(f"{kind} {subject} removed")
        elif after[subject] > before[subject]:
            findings.append(f"{kind} {subject} raised from {before[subject]} to {after[subject]}")
    return findings


def measurement_budget_widenings(
    before: tuple[MeasurementBudget, ...],
    after: tuple[MeasurementBudget, ...],
    targets: Mapping[str, int] | None = None,
) -> tuple[str, ...]:
    """A raised, grown or dropped accepted value widens its measurement budget.

    AD-89 compares a scalar; AD-99 a key's accepted names, where any gained name widens even
    when another one left, because the ratchet holds names rather than their count. `targets`
    are the old contract's `max_names` by label: a key the old baseline did not hold was held by
    that target alone, so a first accepted set above it widens too.
    """
    accepted = {item.label: item for item in after}
    findings = []
    for item in sorted(before, key=lambda budget: budget.label):
        now = accepted.get(item.label)
        if now is None:
            findings.append(f"measurement budget baseline lost {item.label}")
            continue
        gained, _ = name_drift(item, now)
        if gained:
            findings.append(
                f"measurement budget widened: {item.label} (gained {', '.join(gained)})"
            )
        elif now.value > item.value:
            findings.append(
                f"measurement budget widened: {item.label} ({now.value} now, {item.value} before)"
            )
    held = {item.label for item in before}
    old_targets = targets or {}
    findings.extend(
        f"measurement budget widened: {item.label} "
        f"({item.value} accepted, target {old_targets[item.label]} before)"
        for item in sorted(after, key=lambda budget: budget.label)
        if item.label not in held
        and item.label in old_targets
        and item.value > old_targets[item.label]
    )
    return tuple(findings)


def baseline_widenings(
    before: tuple[KnownViolation, ...], after: tuple[KnownViolation, ...]
) -> tuple[str, ...]:
    """A known-violation baseline is part of the contract's surface (#11).

    Padding it to make a new violation disappear is exactly the move a target-first workflow
    invites, so it is compared the same way every other rule is: by fingerprint, a higher count
    or a new fingerprint reported as widening, a lower or removed one left to pass silently.
    Roles do not change fingerprint identity, but AD-85 uses them as directional evidence. Any
    role-only change is therefore protected rather than classified as neutral metadata.
    """
    before_by_fingerprint = {item.fingerprint: item for item in before}
    after_by_fingerprint = {item.fingerprint: item for item in after}
    findings = []
    for fingerprint in sorted(
        before_by_fingerprint.keys() | after_by_fingerprint.keys(),
        key=lambda item: (item.rules, item.subjects),
    ):
        before_item = before_by_fingerprint.get(fingerprint)
        after_item = after_by_fingerprint.get(fingerprint)
        before_count = before_item.count if before_item is not None else 0
        after_count = after_item.count if after_item is not None else 0
        name = f"{' '.join(fingerprint.rules)} | {' '.join(fingerprint.subjects)}"
        if after_count > before_count:
            findings.append(
                f"baseline entry widened: {name} ({after_count} now, {before_count} before)"
            )
        if (
            before_item is not None
            and after_item is not None
            and before_count == after_count
            and before_item.roles != after_item.roles
        ):
            before_roles = ", ".join(
                f"{source} -> {target}" for source, target in before_item.roles
            )
            after_roles = ", ".join(f"{source} -> {target}" for source, target in after_item.roles)
            findings.append(
                f"baseline entry roles changed: {name} "
                f"({before_roles or 'none'} before; {after_roles or 'none'} now)"
            )
    return tuple(findings)
