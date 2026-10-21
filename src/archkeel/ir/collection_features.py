# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-257: the resolution families a contract's rules need the collector to gather."""

from collections.abc import Sequence

from .facts import (
    CONSTRUCT_SELECTORS_FEATURE,
    GUARDED_EFFECTS_FEATURE,
    SOURCE_ROLES_FEATURE,
)
from .model import (
    ArchitectureContract,
    ArchitectureRule,
    CatalogArgumentRule,
    CatalogUseRule,
    ForbiddenConstructRule,
    ForbiddenEffectUnderConditionRule,
    InsideContractMount,
    SourceOwnershipRule,
)


def rule_resolution_features(rule: ArchitectureRule) -> frozenset[str]:
    """The only mapping from a rule to the gated families its decision reads."""
    # catalog_argument reads source_role write/delete facts to prove the target mutates no member.
    if isinstance(rule, SourceOwnershipRule | CatalogUseRule | CatalogArgumentRule):
        return frozenset({SOURCE_ROLES_FEATURE})
    if isinstance(rule, ForbiddenConstructRule) and rule.selector is not None:
        return frozenset({CONSTRUCT_SELECTORS_FEATURE})
    if isinstance(rule, ForbiddenEffectUnderConditionRule):
        return frozenset({GUARDED_EFFECTS_FEATURE})
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
