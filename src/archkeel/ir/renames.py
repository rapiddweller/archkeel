# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Recognise a package rename between two contract revisions (AD-105, #151).

A rename moves code without widening anything, yet compared field by field every renamed
package reads as a gained permission. This module derives the prefix substitution the
component packages imply, checks that it leaves every relation between names as it was and
that the code moved with it, and renames the old side with it, so `ir.widening` compares like
with like: whatever the substitution does not explain is still compared, and so still reported.
Only the fields `ir.model.module_references` lists are renamed; an id, label, kind or other
value never is.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

from .baseline import KnownViolation, ViolationFingerprint
from .codec import RawJson, contract_bytes, parse_contract
from .measurements import MeasurementBudget
from .model import (
    ArchitectureContract,
    NoComponentCyclesRule,
    in_scope,
    last_name,
    module_references,
)


@dataclass(frozen=True, slots=True)
class Renamed:
    """The compared revision under a recognised rename's new names (AD-105)."""

    prefixes: tuple[tuple[str, str], ...]
    contract: ArchitectureContract
    violations: tuple[KnownViolation, ...]
    budgets: tuple[MeasurementBudget, ...]


def renamed(name: str, renames: Mapping[str, str]) -> str:
    """`name` under the longest renamed prefix holding it, or `name` itself."""
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


def _named(name: str, items: list[str]) -> list[str]:
    """The items whose last segment is `name`'s."""
    return [item for item in items if last_name(item) == last_name(name)]


def _moved(old: tuple[str, ...], new: tuple[str, ...]) -> list[tuple[str, str]]:
    """One component's moved packages paired by a last segment only one on each side has,
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

    `names` are the module and symbol names the old contract and baseline hold, `modules` the
    modules the scan reads now. A rule, package or entry scopes by prefix, so a name held another
    before exactly when their new names hold each other, the renamed prefixes themselves
    included: then the renamed contract states for each new name what the old one stated for its
    old name. No scanned module may lie under an old prefix, where the renamed contract no longer
    governs it, whatever its file is called (AD-105).
    """
    olds = frozenset(_module(name) for name in names) | frozenset(renames)
    news = {old: renamed(old, renames) for old in olds}
    holders: dict[str, list[str]] = {}
    for old in sorted(olds):
        holders[news[old]] = [*holders.get(news[old], []), old]
    return all(
        {prefix for prefix in _prefixes(old) if prefix in olds}
        == {each for prefix in _prefixes(news[old]) for each in holders.get(prefix, [])}
        for old in olds
    ) and not any(in_scope(module, old) for module in modules for old in renames)


def _module(name: str) -> str:
    return name.partition(":")[0]


def _prefixes(module: str) -> list[str]:
    """`module` and every dotted prefix of it: the names that hold it."""
    parts = module.split(".")
    return [".".join(parts[:end]) for end in range(1, len(parts) + 1)]


def contract_names(contract: ArchitectureContract) -> frozenset[str]:
    """Every module and symbol name the contract holds: what a rename must explain."""
    return frozenset(value for _, value in module_references(contract))


def _labelled(contract: ArchitectureContract) -> frozenset[str]:
    """The rules whose violations name component labels, not modules: component cycles."""
    return frozenset(
        rule.id
        for rule in contract.rules
        if isinstance(rule, NoComponentCyclesRule) and rule.level is None
    )


def _renamable(item: KnownViolation, labelled: frozenset[str]) -> bool:
    return not frozenset(item.fingerprint.rules) <= labelled


def _baseline_names(
    violations: tuple[KnownViolation, ...],
    budgets: tuple[MeasurementBudget, ...],
    labelled: frozenset[str],
) -> frozenset[str]:
    """Every module or symbol name a validation baseline holds."""
    held = [item for item in violations if _renamable(item, labelled)]
    return frozenset(
        {
            *(subject for item in held for subject in item.fingerprint.subjects),
            *(name for item in held for role in item.roles for name in role),
            *(name for item in budgets for name in item.names),
        }
    )


def _written(document: RawJson, parts: tuple[str, ...], value: str) -> RawJson:
    """`document` with the string at the pointer `parts` replaced by `value`."""
    if not parts:
        return value
    head, rest = parts[0], parts[1:]
    if isinstance(document, list):
        index = int(head)
        return [*document[:index], _written(document[index], rest, value), *document[index + 1 :]]
    if isinstance(document, dict):
        return {**document, head: _written(document[head], rest, value)}
    raise ValueError(f"the contract holds no field at /{'/'.join(parts)}")


def renamed_contract(
    contract: ArchitectureContract, renames: Mapping[str, str]
) -> ArchitectureContract:
    """`contract` with each name `module_references` lists renamed, through its canonical JSON.

    Raises ValueError when the renamed document is no valid contract.
    """
    document: RawJson = json.loads(contract_bytes(contract))
    for pointer, value in module_references(contract):
        if renamed(value, renames) != value:
            document = _written(document, _parts(pointer), renamed(value, renames))
    return parse_contract(document)


def _parts(pointer: str) -> tuple[str, ...]:
    return tuple(pointer.split("/")[1:])


def renamed_baseline(
    violations: tuple[KnownViolation, ...],
    renames: Mapping[str, str],
    labelled: frozenset[str] = frozenset(),
) -> tuple[KnownViolation, ...]:
    """Known violations under the new names, their subjects sorted the way the analyzer does.

    An entry of a `labelled` rule names component labels, which a rename leaves alone.
    """
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
        if _renamable(item, labelled)
        else item
        for item in violations
    )


def _renamed_budgets(
    budgets: tuple[MeasurementBudget, ...], renames: Mapping[str, str]
) -> tuple[MeasurementBudget, ...]:
    """Accepted facade and coupling names under the new names (AD-99)."""
    return tuple(
        replace(item, names=tuple(sorted(renamed(name, renames) for name in item.names)))
        for item in budgets
    )


def rename_since(
    before: ArchitectureContract,
    after: ArchitectureContract,
    *,
    violations: tuple[KnownViolation, ...],
    budgets: tuple[MeasurementBudget, ...],
    modules: frozenset[str],
) -> Renamed | None:
    """The compared revision renamed by the first candidate that holds, or None.

    A candidate whose renamed contract the parser refuses, such as a `root_layout` child moved
    one level down, is no rename: the comparison stays field by field, where an amendment can
    accept the change.
    """
    labelled = _labelled(before)
    names = contract_names(before) | _baseline_names(violations, budgets, labelled)
    for candidate in rename_candidates(before, after):
        if not rename_holds(candidate, names=names, modules=modules):
            continue
        try:
            contract = renamed_contract(before, candidate)
        except ValueError:
            continue
        return Renamed(
            tuple(sorted((old, candidate[old]) for old in candidate)),
            contract,
            renamed_baseline(violations, candidate, labelled),
            _renamed_budgets(budgets, candidate),
        )
    return None
