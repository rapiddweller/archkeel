# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Owned dependency vocabulary and pure module/component selection."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from .facts import in_scope

ComponentOwnership: TypeAlias = tuple[str, tuple[str, ...], tuple[str, ...]]


class ImportSymbolMarker(StrEnum):
    WILDCARD = "*"


class SelectorMatch(StrEnum):
    PREFIX = "prefix"
    EXACT = "exact"


class DependencyTargetKind(StrEnum):
    MODULE = "module"
    IMPORT_NAMESPACE = "import_namespace"


def module_in_ownership(module: str, packages: Iterable[str], exact_modules: Iterable[str]) -> bool:
    """Apply package and exact ownership through the same matcher everywhere."""
    return module in exact_modules or any(in_scope(module, package) for package in packages)


@dataclass(frozen=True, slots=True)
class ModuleSelection:
    packages: tuple[str, ...] = ()
    exact_modules: tuple[str, ...] = ()

    def matches(self, module: str) -> bool:
        return module_in_ownership(module, self.packages, self.exact_modules)

    def __iter__(self) -> Iterator[tuple[str, ...]]:
        """Keep existing ownership-selector unpacking compatible."""
        yield self.packages
        yield self.exact_modules


@dataclass(frozen=True, slots=True)
class DependencyOwner:
    """A caller's component identity and its immutable owned module selection."""

    identity: str
    modules: ModuleSelection


@dataclass(frozen=True, slots=True)
class DependencySelection:
    source: ModuleSelection
    target: ModuleSelection

    def __iter__(self) -> Iterator[ModuleSelection]:
        """Keep existing source/target unpacking compatible."""
        yield self.source
        yield self.target


@dataclass(frozen=True, slots=True)
class DependencySelector:
    source: str
    target: str
    target_symbol: str | None = None
    source_match: SelectorMatch = SelectorMatch.PREFIX
    target_match: SelectorMatch = SelectorMatch.PREFIX
    target_kind: DependencyTargetKind = DependencyTargetKind.MODULE

    def __post_init__(self) -> None:
        if not isinstance(self.source_match, SelectorMatch) or not isinstance(
            self.target_match, SelectorMatch
        ):
            raise ValueError("Dependency match modes must use SelectorMatch")
        if not isinstance(self.target_kind, DependencyTargetKind):
            raise ValueError("Dependency target kind must use DependencyTargetKind")

    def component_pair(self, components: tuple[DependencyOwner, ...]) -> tuple[str, str] | None:
        """Only a legacy whole-package module ban decides an entire component pair."""
        if (
            self.target_symbol is not None
            or self.source_match is not SelectorMatch.PREFIX
            or self.target_match is not SelectorMatch.PREFIX
            or self.target_kind is not DependencyTargetKind.MODULE
        ):
            return None
        sources = {owner.identity for owner in components if self.source in owner.modules.packages}
        targets = {owner.identity for owner in components if self.target in owner.modules.packages}
        if len(sources) != 1 or len(targets) != 1:
            return None
        return next(iter(sources)), next(iter(targets))

    def select(self, components: tuple[DependencyOwner, ...]) -> DependencySelection:
        pair = self.component_pair(components)
        if pair is not None:
            owners = {owner.identity: owner.modules for owner in components}
            return DependencySelection(owners[pair[0]], owners[pair[1]])
        return DependencySelection(
            ModuleSelection(exact_modules=(self.source,))
            if self.source_match is SelectorMatch.EXACT
            else ModuleSelection(packages=(self.source,)),
            ModuleSelection(exact_modules=(self.target,))
            if self.target_match is SelectorMatch.EXACT
            else ModuleSelection(packages=(self.target,)),
        )


__all__ = (
    "ComponentOwnership",
    "ImportSymbolMarker",
    "DependencyOwner",
    "DependencySelection",
    "DependencySelector",
    "DependencyTargetKind",
    "ModuleSelection",
    "SelectorMatch",
    "module_in_ownership",
)
