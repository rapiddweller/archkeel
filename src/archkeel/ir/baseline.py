# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Name a violation independently of its position, and compare a known-violation baseline.

AD-52: a `VIO-` id hashes the fact it cites, and a fact id hashes the source position, so an
unrelated line inserted above a violating import renames the violation without changing the
architecture. What a violation *is* - the rules it breaks and the names those rules name - is
already on the record, and that is what this module derives, counts and compares.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .interfaces import component_owners, owner_of
from .model import Observation, Record, text_value

BASELINE_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class ViolationFingerprint:
    """One violation's position-independent identity.

    `subjects` is the analyzer's own subject list, sorted by `classified` and so carrying no
    direction: the modules, the construct owner or the cycle members the violation is about,
    whichever its kind records. Two violations of one rule that name the same subjects - two
    `getattr` calls in one function - share a fingerprint and are told apart by their count.
    """

    rules: tuple[str, ...]
    subjects: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnownViolation:
    fingerprint: ViolationFingerprint
    count: int


def violation_fingerprint(record: Record) -> ViolationFingerprint:
    return ViolationFingerprint(record.rule_ids, record.subjects)


def _ordered(counts: Counter[ViolationFingerprint]) -> tuple[KnownViolation, ...]:
    return tuple(
        KnownViolation(fingerprint, counts[fingerprint])
        for fingerprint in sorted(counts, key=lambda item: (item.rules, item.subjects))
    )


@dataclass(frozen=True, slots=True)
class ViolationRow:
    """One violation, read the way a consumer off disk wants it rather than as a raw record.

    `fingerprint` is AD-52's stable key: `(rules, subjects)` survives an edit that moves the
    violating line without changing what the violation is, and is what a consumer should key
    on across runs - read `fingerprint.rules` and `fingerprint.subjects` directly rather than
    a second copy of them here, so there is exactly one place either can drift. `source_module`,
    `target_module` and `symbol` are the import a dependency or interface violation crosses; a
    violation kind that names no import, such as a forbidden construct or a component cycle,
    leaves them None rather than a value nobody derived (AD-2). `source_component` and
    `target_component` come from `ir.interfaces.owner_of`, the one place this repository maps a
    module to its component.
    """

    fingerprint: ViolationFingerprint
    source_module: str | None
    target_module: str | None
    symbol: str | None
    source_component: str | None
    target_component: str | None
    evidence_ids: tuple[str, ...]


def violation_rows(observation: Observation) -> tuple[ViolationRow, ...]:
    """Every violation this observation reports, one typed row per record, in record order.

    AD-54: the one derivation that both `observed_violations` below and
    `ir.decisions.violation_counts` build on, so a baseline comparison and a rule-and-pair
    breakdown can never disagree about what a violation is or which component it crosses.
    """
    resolved = component_owners(observation)
    rows = []
    for record in observation.records("violations") or ():
        source_module = text_value(record.data.get("source_module")) or None
        target_module = text_value(record.data.get("target_module")) or None
        symbol = text_value(record.data.get("symbol")) or None
        rows.append(
            ViolationRow(
                violation_fingerprint(record),
                source_module,
                target_module,
                symbol,
                owner_of(source_module, resolved) if source_module is not None else None,
                owner_of(target_module, resolved) if target_module is not None else None,
                record.evidence_ids,
            )
        )
    return tuple(rows)


def observed_violations(observation: Observation) -> tuple[KnownViolation, ...]:
    """Every violation this observation reports, counted per fingerprint and ordered."""
    return _ordered(Counter(row.fingerprint for row in violation_rows(observation)))


def _drift(fingerprint: ViolationFingerprint, known: int, observed: int) -> str:
    name = f"{' '.join(fingerprint.rules)} | {' '.join(fingerprint.subjects)}"
    counted = f"({observed} observed, {known} in the baseline)"
    if observed > known:
        return f"new violation: {name} {counted}"
    return f"resolved violation: {name} {counted}; rewrite the baseline with --write-baseline"


def compare_violations(
    known: tuple[KnownViolation, ...], observed: tuple[KnownViolation, ...]
) -> tuple[str, ...]:
    """One line per fingerprint the baseline states wrongly, new violations and resolved ones.

    Counts must match exactly, so the file states today's debt rather than an upper bound: a
    fingerprint the baseline underestimates is new work, and one it overestimates is work
    already done, which has to leave the file in the change that did it (the budget only
    shrinks). Both are failures, because a budget that may exceed the code lets a violation
    someone removed come back unreported.
    """
    known_counts = {item.fingerprint: item.count for item in known}
    observed_counts = {item.fingerprint: item.count for item in observed}
    return tuple(
        _drift(fingerprint, known_counts.get(fingerprint, 0), observed_counts.get(fingerprint, 0))
        for fingerprint in sorted(
            known_counts.keys() | observed_counts.keys(),
            key=lambda item: (item.rules, item.subjects),
        )
        if known_counts.get(fingerprint, 0) != observed_counts.get(fingerprint, 0)
    )
