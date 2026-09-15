# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Derive undecided component pairs from one observation alone (AD-15).

One function reads the projected dependency decisions and the observed component edges, so
validation and a report rendered later from `architecture.json` bytes share one derivation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

# AD-9: reused ahead of its promotion to a public interface on this module.
from .interfaces import _components
from .model import Observation

_DECIDING_KINDS = frozenset({"forbidden_dependency", "allowed_dependency"})


@dataclass(frozen=True, slots=True)
class OpenDecision:
    """AD-15: one ordered component pair neither allowed nor forbidden by the contract."""

    source: str
    target: str
    observed: bool
    import_sites: int


def _package_owners(components: tuple[tuple[str, tuple[str, ...]], ...]) -> dict[str, str]:
    return {package: label for label, packages in components for package in packages}


def _decided_component_pairs(
    observation: Observation, owners: dict[str, str]
) -> set[tuple[str, str]]:
    """Pairs a `forbidden_dependency` or `allowed_dependency` rule decides.

    Exact package match only, like validation's own `_decided_pairs`: a rule scoped to a
    submodule or a `target_symbol` narrows a rule, it does not decide the component pair.
    """
    decided: set[tuple[str, str]] = set()
    for record in observation.records("declarations") or ():
        if record.kind not in _DECIDING_KINDS:
            continue
        source_module = record.data.get("source")
        target_module = record.data.get("target")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        source = owners.get(source_module)
        target = owners.get(target_module)
        if source is not None and target is not None:
            decided.add((source, target))
    return decided


def _component_import_sites(
    observation: Observation, owners: dict[str, str]
) -> Counter[tuple[str, str]]:
    """Import-site counts per component pair, from the analyzer's own package-level edges."""
    sites: Counter[tuple[str, str]] = Counter()
    for record in observation.records("dependency_edges") or ():
        if record.kind != "package_dependency":
            continue
        source_package = record.data.get("source")
        target_package = record.data.get("target")
        count = record.data.get("count")
        if not isinstance(source_package, str) or not isinstance(target_package, str):
            continue
        if not isinstance(count, int):
            continue
        source = owners.get(source_package)
        target = owners.get(target_package)
        if source is not None and target is not None and source != target:
            sites[(source, target)] += count
    return sites


def open_decisions(observation: Observation) -> tuple[OpenDecision, ...]:
    """Derive undecided component pairs, heaviest observed edges first (AD-15)."""
    components = _components(observation)
    owners = _package_owners(components)
    labels = {label for label, _ in components}
    expected = {(source, target) for source in labels for target in labels if source != target}
    decided = _decided_component_pairs(observation, owners)
    sites = _component_import_sites(observation, owners)
    return tuple(
        sorted(
            (
                OpenDecision(source, target, sites[(source, target)] > 0, sites[(source, target)])
                for source, target in expected - decided
            ),
            key=lambda item: (-item.import_sites, item.source, item.target),
        )
    )
