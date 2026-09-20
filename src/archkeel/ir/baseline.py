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

from .model import Observation, Record

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


def observed_violations(observation: Observation) -> tuple[KnownViolation, ...]:
    """Every violation this observation reports, counted per fingerprint and ordered."""
    return _ordered(
        Counter(violation_fingerprint(record) for record in observation.records("violations") or ())
    )


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
