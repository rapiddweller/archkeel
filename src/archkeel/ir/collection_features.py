# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-257: the resolution families a contract's rules need the collector to gather."""

from collections.abc import Sequence

from .facts import (
    CALL_ARGUMENTS_FEATURE,
    CONSTRUCT_SELECTORS_FEATURE,
    EXTENDED_CALL_BINDINGS_FEATURE,
    GUARDED_EFFECTS_FEATURE,
    NUMERIC_OPERANDS_FEATURE,
    SOURCE_ROLES_FEATURE,
)
from .model import (
    ArchitectureContract,
    ArchitectureRule,
    BoundedNumericOperandRule,
    CallOwnerRule,
    CatalogArgumentRule,
    CatalogUseRule,
    ForbiddenCallArgumentRule,
    ForbiddenConstructRule,
    ForbiddenEffectUnderConditionRule,
    InsideContractMount,
    SourceOwnershipRule,
)


def rule_resolution_features(rule: ArchitectureRule) -> frozenset[str]:
    """The only mapping from a rule to the gated families its decision reads."""
    # catalog_* read source_role write/delete facts to prove the target mutates no member.
    if isinstance(rule, CatalogUseRule | CatalogArgumentRule):
        return frozenset(
            {SOURCE_ROLES_FEATURE, EXTENDED_CALL_BINDINGS_FEATURE, CALL_ARGUMENTS_FEATURE}
        )
    if isinstance(rule, SourceOwnershipRule):
        return frozenset({SOURCE_ROLES_FEATURE})
    if isinstance(rule, CallOwnerRule):
        return frozenset({EXTENDED_CALL_BINDINGS_FEATURE})
    # A written argument is only attributed to a call whose binding is proven, receivers included.
    if isinstance(rule, ForbiddenCallArgumentRule):
        return frozenset({CALL_ARGUMENTS_FEATURE, EXTENDED_CALL_BINDINGS_FEATURE})
    # Helper actuals are bound from the caller's written call arguments.
    if isinstance(rule, ForbiddenEffectUnderConditionRule):
        return frozenset(
            {GUARDED_EFFECTS_FEATURE, EXTENDED_CALL_BINDINGS_FEATURE, CALL_ARGUMENTS_FEATURE}
        )
    if isinstance(rule, ForbiddenConstructRule) and rule.selector is not None:
        return frozenset({CONSTRUCT_SELECTORS_FEATURE, EXTENDED_CALL_BINDINGS_FEATURE})
    if isinstance(rule, BoundedNumericOperandRule):
        return frozenset({NUMERIC_OPERANDS_FEATURE})
    return frozenset()


def required_resolution_features(
    contract: ArchitectureContract, inside_contracts: Sequence[InsideContractMount] = ()
) -> frozenset[str]:
    """Gated families declared by the root contract and every mounted inside contract."""
    rules = (
        *contract.rules,
        *(rule for mount in inside_contracts for rule in mount.contract.rules),
    )
    families: set[str] = set()
    for rule in rules:
        families |= rule_resolution_features(rule)
    return frozenset(families)
