# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The one owner of the scope label and of module membership (AD-321).

A scope key names a component inside its parents: `parent:label`. A module belongs to a
component when exactly one component claims it at each level, from the root down. Two
claimants own nothing. Every reader of this rule calls this module.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TypeVar

from .architecture_graph import ComponentIntent
from .dependency import ComponentOwnership, module_in_ownership

_Claim = TypeVar("_Claim")


def scope_key(parent: str | None, label: str) -> str:
    """Return the key of a component in its parent scope. The root has no parent."""
    return f"{parent}:{label}" if parent else label


def scope_names(intents: Iterable[ComponentIntent]) -> dict[str, str]:
    """Map each component id to its scope key. A missing label uses the component id."""
    by_id = {item.component_id: item for item in intents}
    names: dict[str, str] = {}

    def name(identity: str) -> str:
        if identity not in names:
            intent = by_id[identity]
            label = intent.label or identity
            names[identity] = scope_key(name(intent.parent_id) if intent.parent_id else None, label)
        return names[identity]

    for identity in by_id:
        name(identity)
    return names


def sole(claims: Sequence[_Claim]) -> _Claim | None:
    """Return the one claimant. Zero or many claimants own nothing."""
    return claims[0] if len(claims) == 1 else None


def owner_of(module: str, components: Iterable[ComponentOwnership]) -> str | None:
    """Return the one component owning a module, or None if zero or many claim it."""
    return sole(
        tuple(
            label
            for label, packages, exact_modules in components
            if module_in_ownership(module, packages, exact_modules)
        )
    )


def partition(
    names: Iterable[str], components: Iterable[ComponentOwnership]
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Group names by their one owner. A name with zero or many claimants comes back unowned."""
    claims = tuple(components)
    owned: dict[str, list[str]] = {}
    unowned: list[str] = []
    for name in names:
        owner = owner_of(name, claims)
        if owner is None:
            unowned.append(name)
        else:
            owned.setdefault(owner, []).append(name)
    return {owner: tuple(group) for owner, group in owned.items()}, tuple(unowned)


def scope_owners(
    intents: Sequence[ComponentIntent], module: str, parent_id: str | None
) -> tuple[str, ...]:
    """Return the sorted ids of the children of a scope that claim a module.

    The scope itself must be the one owner at its own level. Below an ambiguous or unowned
    parent the result is empty.
    """
    if parent_id is not None:
        parent = next(item for item in intents if item.component_id == parent_id)
        if scope_owners(intents, module, parent.parent_id) != (parent_id,):
            return ()
    return tuple(
        sorted(
            item.component_id
            for item in intents
            if item.parent_id == parent_id
            and module_in_ownership(module, item.packages, item.exact_modules)
        )
    )


def _descend(
    intents: Sequence[ComponentIntent], module: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    chain: list[str] = []
    while True:
        matches = scope_owners(intents, module, chain[-1] if chain else None)
        if len(matches) != 1:
            return tuple(chain), matches
        chain.append(matches[0])


def containing(intents: Sequence[ComponentIntent], module: str) -> tuple[str, ...]:
    """Return the ids of the components that contain a module, from the root to the deepest."""
    return _descend(intents, module)[0]


def deepest_owners(intents: Sequence[ComponentIntent], module: str) -> tuple[str, ...]:
    """Return the deepest owner, or every claimant where one level has zero or many.

    Where the first level has no claimant the result is empty. Where a deeper level has no
    claimant, the parent is the owner. Where it has many, the caller decides.
    """
    chain, matches = _descend(intents, module)
    return matches or chain[-1:]
