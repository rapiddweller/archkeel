# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Classify the difference of each architecture rule between two contract revisions (#11).

A new permission or a dropped restriction widens the contract. The rule kinds below say which
side of a kind is the permission. A kind that no branch names fails closed: its presence, and
any field difference, is reported as a widening.
"""

from __future__ import annotations

from typing import Final

from .model import (
    AllowedDependencyRule,
    ArchitectureRule,
    BoundaryTypesRule,
    BoundedNumericOperandRule,
    CallOwnerRule,
    CompleteAssignmentRule,
    CompleteExternalScopeRule,
    CompleteRequiresRule,
    DependencyTargetKind,
    ExternalDependencyScopeRule,
    ForbiddenCallArgumentRule,
    ForbiddenConstructRule,
    ForbiddenDependencyRule,
    InterfaceBoundaryRule,
    NoComponentCyclesRule,
    RootLayoutRule,
    SelectorMatch,
    SiblingIsolationRule,
    SourceOwnershipRule,
)
from .widening_change import WideningChange, generic_field_widenings, set_widenings

# AllowedDependencyRule alone grants an edge; every other kind restricts something (AD-15).
PERMISSION_RULE_KINDS: Final = frozenset({"allowed_dependency"})
RESTRICTION_RULE_KINDS: Final = frozenset(
    {
        "call_owner",
        "bounded_numeric_operand",
        "protocol_declarations",
        "forbidden_call_argument",
        "forbidden_effect_under_condition",
        "forbidden_dependency",
        "forbidden_construct",
        "external_dependency_scope",
        "complete_assignment",
        "root_layout",
        "complete_external_scope",
        "complete_requires",
        "layer_order",
        "no_component_cycles",
        "interface_boundary",
        "sibling_isolation",
        "symbol_placement",
        "boundary_types",
        "catalog_argument",
        "catalog_use",
        "source_ownership",
    }
)


def _include_type_checking_widening(
    subject: str, before: bool, after: bool
) -> list[WideningChange]:
    """A rule that stops covering type-checking-only imports is weakened, not strengthened."""
    if before and not after:
        return [
            WideningChange(
                subject,
                "include_type_checking",
                f"{subject}.include_type_checking relaxed from true to false",
            )
        ]
    return []


def _type_checking_rule_widenings(
    subject: str,
    before: CompleteRequiresRule | InterfaceBoundaryRule,
    after: CompleteRequiresRule | InterfaceBoundaryRule,
) -> list[WideningChange]:
    return [
        *_include_type_checking_widening(
            subject, before.include_type_checking, after.include_type_checking
        ),
        *generic_field_widenings(
            subject, before, after, handled=frozenset({"include_type_checking"})
        ),
    ]


def _interface_boundary_widenings(
    subject: str, before: InterfaceBoundaryRule, after: InterfaceBoundaryRule
) -> list[WideningChange]:
    return [
        *[
            WideningChange(
                subject, "module_object_grants", f"{subject}.module_object_grants gained {grant!r}"
            )
            for grant in sorted(
                set(after.module_object_grants or ()) - set(before.module_object_grants or ()),
                key=lambda item: (item.source_module, item.target_module),
            )
        ],
        *_include_type_checking_widening(
            subject, before.include_type_checking, after.include_type_checking
        ),
        *generic_field_widenings(
            subject,
            before,
            after,
            handled=frozenset({"include_type_checking", "module_object_grants"}),
        ),
    ]


def _rule_presence_widening(rule: ArchitectureRule, *, added: bool) -> list[WideningChange]:
    verb = "added" if added else "removed"
    if rule.kind in PERMISSION_RULE_KINDS:
        widens = added
    elif rule.kind in RESTRICTION_RULE_KINDS:
        widens = not added
    else:
        # Fail closed: a rule kind this module does not enumerate is never assumed to be a
        # restriction, so its presence changing in either direction is reported.
        widens = True
    subject = f"rule {rule.id}"
    return (
        [WideningChange(subject, "presence", f"{subject} ({rule.kind}) {verb}")] if widens else []
    )


def _forbidden_dependency_widenings(
    subject: str, before: ForbiddenDependencyRule, after: ForbiddenDependencyRule
) -> list[WideningChange]:
    return [
        *set_widenings(
            subject,
            "allowed_sources",
            frozenset(before.allowed_sources),
            frozenset(after.allowed_sources),
            grows_widens=True,
        ),
        *_include_type_checking_widening(
            subject, before.include_type_checking, after.include_type_checking
        ),
        *[
            WideningChange(subject, name, f"{subject}.{name} narrowed from prefix to exact")
            for name, old, new in (
                ("source_match", before.source_match, after.source_match),
                ("target_match", before.target_match, after.target_match),
            )
            if old is SelectorMatch.PREFIX and new is SelectorMatch.EXACT
        ],
        *(
            [
                WideningChange(
                    subject, "target_kind", f"{subject} now permits an absent import namespace"
                )
            ]
            if before.target_kind is DependencyTargetKind.MODULE
            and after.target_kind is DependencyTargetKind.IMPORT_NAMESPACE
            else []
        ),
        *generic_field_widenings(
            subject,
            before,
            after,
            handled=frozenset(
                {
                    "allowed_sources",
                    "include_type_checking",
                    "source_match",
                    "target_match",
                    "target_kind",
                }
            ),
        ),
    ]


def _forbidden_construct_widenings(
    subject: str, before: ForbiddenConstructRule, after: ForbiddenConstructRule
) -> list[WideningChange]:
    return [
        # A construct dropped from the forbidden list is a widening; one added is not.
        *set_widenings(
            subject,
            "constructs",
            frozenset(before.constructs),
            frozenset(after.constructs),
            grows_widens=False,
        ),
        *set_widenings(
            subject,
            "allowed_sources",
            frozenset(before.allowed_sources),
            frozenset(after.allowed_sources),
            grows_widens=True,
        ),
        *set_widenings(
            subject,
            "exact_sources",
            frozenset(before.exact_sources),
            frozenset(after.exact_sources),
            grows_widens=True,
        ),
        *[
            WideningChange(
                subject, "allowed_type_ignores", f"{subject}.allowed_type_ignores gained {item!r}"
            )
            for item in sorted(
                set(after.allowed_type_ignores) - set(before.allowed_type_ignores),
                key=lambda item: (item.qualified_name, item.line, item.statement, item.tag),
            )
        ],
        *generic_field_widenings(
            subject,
            before,
            after,
            handled=frozenset(
                {"constructs", "allowed_sources", "exact_sources", "allowed_type_ignores"}
            ),
        ),
    ]


def _external_dependency_scope_widenings(
    subject: str,
    before: ExternalDependencyScopeRule | CallOwnerRule,
    after: ExternalDependencyScopeRule | CallOwnerRule,
) -> list[WideningChange]:
    return [
        *set_widenings(
            subject,
            "allowed_sources",
            frozenset(before.allowed_sources),
            frozenset(after.allowed_sources),
            grows_widens=True,
        ),
        *set_widenings(
            subject,
            "exact_sources",
            frozenset(before.exact_sources),
            frozenset(after.exact_sources),
            grows_widens=True,
        ),
        *generic_field_widenings(
            subject, before, after, handled=frozenset({"allowed_sources", "exact_sources"})
        ),
    ]


def _sibling_isolation_widenings(
    subject: str, before: SiblingIsolationRule, after: SiblingIsolationRule
) -> list[WideningChange]:
    return [
        # Fewer isolated members means less is kept apart: a widening, not a narrowing.
        *set_widenings(
            subject,
            "members",
            frozenset(before.members),
            frozenset(after.members),
            grows_widens=False,
        ),
        *_include_type_checking_widening(
            subject, before.include_type_checking, after.include_type_checking
        ),
        *generic_field_widenings(
            subject, before, after, handled=frozenset({"members", "include_type_checking"})
        ),
    ]


def _boundary_types_widenings(
    subject: str, before: BoundaryTypesRule, after: BoundaryTypesRule
) -> list[WideningChange]:
    return [
        WideningChange(subject, "allowed_positions", f"{subject}.allowed_positions gained {item!r}")
        for item in sorted(
            set(after.allowed_positions) - set(before.allowed_positions),
            key=lambda entry: (
                entry.qualified_name,
                entry.position,
                entry.field_path,
                entry.annotation,
                entry.container_depth or 0,
                entry.mapping_depth or 0,
                entry.literal_mapping_arm or "",
                entry.native_mapping,
                entry.alias_body is not None,
                entry.alias_body.origin if entry.alias_body is not None else "",
                entry.alias_body.shape if entry.alias_body is not None else "",
                entry.key_alias_body is not None,
                entry.key_alias_body.origin if entry.key_alias_body is not None else "",
                entry.key_alias_body.shape if entry.key_alias_body is not None else "",
            ),
        )
    ]


def _no_component_cycles_widenings(
    subject: str, before: NoComponentCyclesRule, after: NoComponentCyclesRule
) -> list[WideningChange]:
    """AD-98: judging fewer cycles widens, and so does any level change.

    Neither level implies the other: `a1 -> b1` and `b2 -> a2` close a component cycle through
    modules that form none, and one component can hold a module cycle while no component
    cycle exists.
    """
    old_level, new_level = before.level or "component", after.level or "component"
    level = (
        [
            WideningChange(
                subject, "level", f"{subject}.level changed from {old_level} to {new_level}"
            )
        ]
        if old_level != new_level
        else []
    )
    if after.components is None:
        scope: list[WideningChange] = []
    elif before.components is None:
        scope = [
            WideningChange(
                subject, "components", f"{subject}.components scoped to {sorted(after.components)}"
            )
        ]
    else:
        scope = set_widenings(
            subject,
            "components",
            frozenset(before.components),
            frozenset(after.components),
            grows_widens=False,
        )
    return [
        *level,
        *scope,
        *generic_field_widenings(
            subject, before, after, handled=frozenset({"level", "components"})
        ),
    ]


def _bounded_numeric_operand_widenings(
    subject: str, before: BoundedNumericOperandRule, after: BoundedNumericOperandRule
) -> list[WideningChange]:
    threshold = (
        [
            WideningChange(
                subject,
                "minimum_value",
                f"{subject}.minimum_value decreased from {before.minimum_value} "
                f"to {after.minimum_value}",
            )
        ]
        if after.minimum_value < before.minimum_value
        else []
    )
    return [
        *threshold,
        *generic_field_widenings(subject, before, after, handled=frozenset({"minimum_value"})),
    ]


def _matched_rule_widenings(
    before: ArchitectureRule, after: ArchitectureRule
) -> list[WideningChange]:
    """Dispatch by matched rule kind; a kind this module has no branch for falls closed below."""
    subject = f"rule {before.id}"
    if before.kind != after.kind:
        # An id kept across a kind change: neither the permission nor the restriction map
        # still applies, so fail closed rather than guess which side is now safe.
        return [
            WideningChange(
                subject, "kind", f"{subject} changed kind from {before.kind} to {after.kind}"
            )
        ]
    if isinstance(before, ForbiddenDependencyRule) and isinstance(after, ForbiddenDependencyRule):
        return _forbidden_dependency_widenings(subject, before, after)
    if isinstance(before, AllowedDependencyRule) and isinstance(after, AllowedDependencyRule):
        return generic_field_widenings(subject, before, after, handled=frozenset())
    if isinstance(before, ForbiddenConstructRule) and isinstance(after, ForbiddenConstructRule):
        return _forbidden_construct_widenings(subject, before, after)
    if isinstance(before, ExternalDependencyScopeRule | CallOwnerRule) and isinstance(
        after, ExternalDependencyScopeRule | CallOwnerRule
    ):
        return _external_dependency_scope_widenings(subject, before, after)
    if isinstance(before, ForbiddenCallArgumentRule) and isinstance(
        after, ForbiddenCallArgumentRule
    ):
        return generic_field_widenings(subject, before, after, handled=frozenset())
    if isinstance(before, CompleteRequiresRule) and isinstance(after, CompleteRequiresRule):
        return _type_checking_rule_widenings(subject, before, after)
    if isinstance(before, RootLayoutRule) and isinstance(after, RootLayoutRule):
        return [
            *set_widenings(
                subject,
                "allowed_children",
                frozenset(before.allowed_children),
                frozenset(after.allowed_children),
                grows_widens=True,
            ),
            *generic_field_widenings(
                subject, before, after, handled=frozenset({"allowed_children"})
            ),
        ]
    if isinstance(before, InterfaceBoundaryRule) and isinstance(after, InterfaceBoundaryRule):
        return _interface_boundary_widenings(subject, before, after)
    if isinstance(before, SiblingIsolationRule) and isinstance(after, SiblingIsolationRule):
        return _sibling_isolation_widenings(subject, before, after)
    if isinstance(before, BoundaryTypesRule) and isinstance(after, BoundaryTypesRule):
        return [
            *_boundary_types_widenings(subject, before, after),
            *generic_field_widenings(
                subject, before, after, handled=frozenset({"allowed_positions"})
            ),
        ]
    if isinstance(before, SourceOwnershipRule) and isinstance(after, SourceOwnershipRule):
        return generic_field_widenings(subject, before, after, handled=frozenset())
    if isinstance(before, CompleteAssignmentRule) and isinstance(after, CompleteAssignmentRule):
        return generic_field_widenings(subject, before, after, handled=frozenset())
    if isinstance(before, CompleteExternalScopeRule) and isinstance(
        after, CompleteExternalScopeRule
    ):
        return generic_field_widenings(subject, before, after, handled=frozenset())
    if isinstance(before, BoundedNumericOperandRule) and isinstance(
        after, BoundedNumericOperandRule
    ):
        return _bounded_numeric_operand_widenings(subject, before, after)
    if isinstance(before, NoComponentCyclesRule) and isinstance(after, NoComponentCyclesRule):
        return _no_component_cycles_widenings(subject, before, after)
    # Fail closed: a rule type this dispatch does not recognise is never assumed safe.
    return (
        [
            WideningChange(
                subject, "rule", f"{subject} changed in a way this comparison does not enumerate"
            )
        ]
        if before != after
        else []
    )


def rules_widenings(
    before: tuple[ArchitectureRule, ...], after: tuple[ArchitectureRule, ...]
) -> list[WideningChange]:
    before_map = {rule.id: rule for rule in before}
    after_map = {rule.id: rule for rule in after}
    findings: list[WideningChange] = []
    for rule_id in sorted(set(after_map) - set(before_map)):
        findings += _rule_presence_widening(after_map[rule_id], added=True)
    for rule_id in sorted(set(before_map) - set(after_map)):
        findings += _rule_presence_widening(before_map[rule_id], added=False)
    for rule_id in sorted(set(before_map) & set(after_map)):
        findings += _matched_rule_widenings(before_map[rule_id], after_map[rule_id])
    return findings
