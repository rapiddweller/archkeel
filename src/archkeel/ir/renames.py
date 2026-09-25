# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Recognise a package rename between two contract revisions (AD-105, #151).

A rename moves code without widening anything, yet compared field by field every renamed
package reads as a gained permission. This module derives the prefix substitution the
component packages imply, checks that it explains the old contract, baseline and scan without
touching anything else, and renames the old side with it, so `ir.widening` compares like with
like: whatever the substitution does not explain is still compared, and so still reported.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Final

from .baseline import KnownViolation, ViolationFingerprint
from .codec import RawJson, contract_bytes, parse_contract
from .measurements import MeasurementBudget
from .model import ArchitectureContract, in_scope

# A dotted module name, optionally followed by `:Name`: the only spelling a rename rewrites, so
# prose, paths and URLs stay as they are.
_DOTTED: Final = r"[^\W\d]\w*(?:\.[^\W\d]\w*)*(?::[^\W\d][\w.]*)?"


def renamed(name: str, renames: Mapping[str, str]) -> str:
    """`name` under the longest renamed prefix holding it; any other string stays as it is."""
    if re.fullmatch(_DOTTED, name) is None:
        return name
    module, colon, symbol = name.partition(":")
    old = max((prefix for prefix in renames if in_scope(module, prefix)), key=len, default=None)
    if old is None:
        return name
    return f"{renames[old]}{module[len(old) :]}{colon}{symbol}"


def _shortest(old: str, new: str) -> tuple[str, str]:
    """Drop the trailing segments a move kept, so `a.x -> b.x` reads `a -> b`."""
    old_parts, new_parts = old.split("."), new.split(".")
    kept = 0
    while (
        kept < min(len(old_parts), len(new_parts)) - 1
        and old_parts[-1 - kept] == new_parts[-1 - kept]
    ):
        kept += 1
    return ".".join(old_parts[: len(old_parts) - kept]), ".".join(
        new_parts[: len(new_parts) - kept]
    )


def _mapping(pairs: Iterable[tuple[str, str]]) -> dict[str, str]:
    """One substitution for every pair, without an entry a shorter one implies; {} when two
    pairs disagree or two old prefixes would become one."""
    mapping: dict[str, str] = {}
    for old, new in sorted(set(pairs), key=lambda pair: (len(pair[0]), pair)):
        if renamed(old, mapping) == new:
            continue
        if old in mapping or new in mapping.values():
            return {}
        mapping[old] = new
    return mapping


def _last(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def _named(name: str, items: list[str]) -> list[str]:
    """The items whose last segment is `name`'s."""
    return [item for item in items if _last(item) == _last(name)]


def _moved(old: tuple[str, ...], new: tuple[str, ...]) -> list[tuple[str, str]]:
    """One component's moved packages paired: by a last segment only one on each side has,
    since a package move keeps it, then the rest in their order."""
    gone = [item for item in old if item not in new]
    came = [item for item in new if item not in old]
    if len(gone) != len(came):
        return []
    by_name: dict[str, str] = {
        item: _named(item, came)[0]
        for item in gone
        if len(_named(item, came)) == 1 and len(_named(item, gone)) == 1
    }
    taken = set(by_name.values())
    rest = zip(
        [item for item in gone if item not in by_name],
        [item for item in came if item not in taken],
        strict=True,
    )
    return [*by_name.items(), *rest]


def rename_candidates(
    before: ArchitectureContract, after: ArchitectureContract
) -> tuple[dict[str, str], ...]:
    """The substitutions the moved component packages imply, shortest prefixes first.

    A component keeps its id across a rename. `rename_holds` decides whether a candidate
    explains the change; none is trusted here.
    """
    after_packages = {component.id: component.packages for component in after.components}
    pairs = [
        pair
        for component in before.components
        for pair in _moved(component.packages, after_packages.get(component.id, ()))
    ]
    candidates: list[dict[str, str]] = []
    for mapping in (_mapping(_shortest(old, new) for old, new in pairs), _mapping(pairs)):
        if mapping and mapping not in candidates:
            candidates.append(mapping)
    return tuple(candidates)


def rename_holds(
    renames: Mapping[str, str], *, names: frozenset[str], modules: frozenset[str]
) -> bool:
    """Whether `renames` renames the old side and leaves every relation between names as it was.

    `names` are the dotted names the old contract and baseline hold, `modules` the modules the
    scan reads now. A rule, package or entry scopes by prefix, so a name held another before
    exactly when their new names hold each other: then the renamed contract states for each new
    name what the old one stated for its old name. No scanned module may keep an old name, which
    the renamed contract no longer governs (AD-105).
    """
    olds = frozenset(_module(name) for name in names)
    news = {old: renamed(old, renames) for old in olds}
    holders: dict[str, list[str]] = {}
    for old in sorted(olds):
        holders[news[old]] = [*holders.get(news[old], []), old]
    return all(
        {prefix for prefix in _prefixes(old) if prefix in olds}
        == {each for prefix in _prefixes(news[old]) for each in holders.get(prefix, [])}
        for old in olds
    ) and all(renamed(module, renames) == module for module in modules)


def _module(name: str) -> str:
    return name.partition(":")[0]


def _prefixes(module: str) -> list[str]:
    """`module` and every dotted prefix of it: the names that hold it."""
    parts = module.split(".")
    return [".".join(parts[:end]) for end in range(1, len(parts) + 1)]


def _strings(value: RawJson) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for key in value:
            yield from _strings(value[key])


def _renamed_json(value: RawJson, renames: Mapping[str, str]) -> RawJson:
    if isinstance(value, str):
        return renamed(value, renames)
    if isinstance(value, list):
        return [_renamed_json(item, renames) for item in value]
    if isinstance(value, dict):
        return {key: _renamed_json(value[key], renames) for key in value}
    return value


def contract_names(contract: ArchitectureContract) -> frozenset[str]:
    """Every dotted name the contract holds, in any field: what a rename must explain."""
    return frozenset(
        item
        for item in _strings(json.loads(contract_bytes(contract)))
        if re.fullmatch(_DOTTED, item)
    )


def baseline_names(
    violations: tuple[KnownViolation, ...], budgets: tuple[MeasurementBudget, ...]
) -> frozenset[str]:
    """Every module or symbol name a validation baseline holds."""
    return frozenset(
        {
            *(subject for item in violations for subject in item.fingerprint.subjects),
            *(name for item in violations for role in item.roles for name in role),
            *(name for item in budgets for name in item.names),
        }
    )


def renamed_contract(
    contract: ArchitectureContract, renames: Mapping[str, str]
) -> ArchitectureContract:
    """`contract` with every dotted name in every field renamed, through its canonical JSON."""
    return parse_contract(_renamed_json(json.loads(contract_bytes(contract)), renames))


def renamed_baseline(
    violations: tuple[KnownViolation, ...], renames: Mapping[str, str]
) -> tuple[KnownViolation, ...]:
    """Known violations under the new names, their subjects sorted the way the analyzer does."""
    return tuple(
        KnownViolation(
            ViolationFingerprint(
                item.fingerprint.rules,
                tuple(sorted(renamed(subject, renames) for subject in item.fingerprint.subjects)),
            ),
            item.count,
            tuple(
                sorted(
                    (renamed(source, renames), renamed(target, renames))
                    for source, target in item.roles
                )
            ),
        )
        for item in violations
    )


def renamed_budgets(
    budgets: tuple[MeasurementBudget, ...], renames: Mapping[str, str]
) -> tuple[MeasurementBudget, ...]:
    """Accepted facade and coupling names under the new names (AD-99)."""
    return tuple(
        replace(item, names=tuple(sorted(renamed(name, renames) for name in item.names)))
        for item in budgets
    )
