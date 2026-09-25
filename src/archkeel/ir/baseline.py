# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Name a violation independently of its position, and compare a validation baseline.

AD-52: a `VIO-` id hashes the fact it cites, and a fact id hashes the source position, so an
unrelated line inserted above a violating import renames the violation without changing the
architecture. What a violation *is* - the rules it breaks and the names those rules name - is
already on the record, and that is what this module derives, counts and compares.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from .interfaces import component_owners, owner_of
from .measurements import MeasurementBudget
from .model import (
    RULE_KINDS,
    Diagnostic,
    DiagnosticError,
    Observation,
    Record,
    ReportFilter,
    text_value,
)

# AD-99: 1.3.0 adds keyed name sets; 1.2.0 added scalar budgets (AD-89) and stays readable.
BASELINE_SCHEMA_VERSION = "1.3.0"
SCALAR_BUDGETS_BASELINE_SCHEMA_VERSION = "1.2.0"
ROLES_BASELINE_SCHEMA_VERSION = "1.1.0"
LEGACY_BASELINE_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class ViolationFingerprint:
    """One violation's position-independent identity, built by `canonical_fingerprint`.

    `subjects` is the analyzer's own subject list, carrying no direction: the modules, the
    construct owner or the cycle members the violation is about, whichever its kind records. Two
    violations of one rule that name the same subjects - two `getattr` calls in one function -
    share a fingerprint and are told apart by their count.
    """

    rules: tuple[str, ...]
    subjects: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnownViolation:
    fingerprint: ViolationFingerprint
    count: int
    # Decision-relevant direction evidence; protected separately from fingerprint identity.
    roles: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationBaseline:
    """Known violations and accepted values for contract-selected measurements."""

    violations: tuple[KnownViolation, ...] = ()
    budgets: tuple[MeasurementBudget, ...] = ()


def canonical_fingerprint(rules: Iterable[str], subjects: Iterable[str]) -> ViolationFingerprint:
    """Name a violation the same way whatever order its lists arrive in (AD-106).

    Neither order means anything - direction lives in `KnownViolation.roles` - so an observed
    record and a baseline entry written in another order, by hand or by a text replace that
    renamed a namespace, name one violation. Sorted rather than a set, so a repeated subject
    still counts and no two different lists collapse into one.
    """
    return ViolationFingerprint(tuple(sorted(rules)), tuple(sorted(subjects)))


def violation_fingerprint(record: Record) -> ViolationFingerprint:
    return canonical_fingerprint(record.rule_ids, record.subjects)


def _ordered(
    counts: Counter[ViolationFingerprint],
    roles: dict[ViolationFingerprint, set[tuple[str, str]]] | None = None,
) -> tuple[KnownViolation, ...]:
    return tuple(
        KnownViolation(
            fingerprint,
            counts[fingerprint],
            tuple(sorted(roles.get(fingerprint, set()))) if roles is not None else (),
        )
        for fingerprint in sorted(counts, key=lambda item: (item.rules, item.subjects))
    )


def _counts(violations: tuple[KnownViolation, ...]) -> dict[ViolationFingerprint, int]:
    return {item.fingerprint: item.count for item in violations}


@dataclass(frozen=True, slots=True)
class CycleIdentity:
    """One SCC: what it is judged under, and its members.

    `key` is the level of a measured SCC and the rule ids of a cycle violation. Removing imports
    only shrinks or splits an SCC, so one whose members are a strict subset of a known SCC under
    the same key is that SCC contracting, not a new cycle. `check`'s delta and the baseline
    (AD-98) share `is_contraction` for that answer.
    """

    key: tuple[str, ...]
    members: frozenset[str]


def is_contraction(cycle: CycleIdentity, known: Iterable[CycleIdentity]) -> bool:
    """True when `cycle` is a strict subset of one `known` cycle under the same key."""
    return any(cycle.key == old.key and cycle.members < old.members for old in known)


def _cycle(fingerprint: ViolationFingerprint) -> CycleIdentity:
    return CycleIdentity(fingerprint.rules, frozenset(fingerprint.subjects))


def cycle_contractions(
    known: tuple[KnownViolation, ...],
    observed: tuple[KnownViolation, ...],
    *,
    cycle_rules: frozenset[str],
) -> frozenset[ViolationFingerprint]:
    """The observed cycle fingerprints that are a baselined cycle contracting (AD-98).

    A fingerprint qualifies only under a `no_component_cycles` rule, whose subjects are the
    members of one SCC, and only inside a baselined cycle whose own count fell: a baseline that
    keeps the old cycle beside a part of it is padded, not contracted.
    """
    known_counts, observed_counts = _counts(known), _counts(observed)
    fallen = [
        _cycle(item.fingerprint)
        for item in known
        if set(item.fingerprint.rules) <= cycle_rules
        and observed_counts.get(item.fingerprint, 0) < item.count
    ]
    return frozenset(
        item.fingerprint
        for item in observed
        if set(item.fingerprint.rules) <= cycle_rules
        and item.count > known_counts.get(item.fingerprint, 0)
        and is_contraction(_cycle(item.fingerprint), fallen)
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


def declared_rule_ids(observation: Observation) -> frozenset[str]:
    """Every rule id the contract declares at either level, the domain `--rule` validates against.

    Reads the DECLARED_RULE records themselves, not `violation_rows`: a rule with no violation
    is still a valid filter target, and an id this returns but `violation_rows` never cites
    simply selects nothing, which is not the same as naming a rule nobody declared (AD-60). An
    inside's rule already carries the `<component>:<rule id>` prefix `report.py`'s
    `_owned_rules` renamed it to before it reached this observation (AD-36), so this needs no
    prefix logic of its own.
    """
    return frozenset(
        record.id
        for record in observation.records("declarations") or ()
        if record.kind in RULE_KINDS
    )


def declared_components(observation: Observation) -> frozenset[str]:
    """Every top-level component label, the domain `--component` validates against (AD-60).

    `ViolationRow.source_component`/`target_component` are always this top level's own labels
    (`ir.interfaces.component_owners` reads only `component_responsibility`, never a
    sub-component's `inside_component_responsibility`), so a sub-component name is correctly
    unknown here rather than silently matching nothing.
    """
    return frozenset(label for label, _ in component_owners(observation))


def require_declared_filter(observation: Observation, report_filter: ReportFilter) -> None:
    """Raise `DiagnosticError` for a `rule` or `component` naming nothing this observation
    declares, so a typo reports an error rather than an empty page a reader could mistake for a
    clean one (AD-60). `--only calls` checks its `component` here too (AD-100).
    """
    known_rules = declared_rule_ids(observation)
    if report_filter.rule is not None and report_filter.rule not in known_rules:
        raise DiagnosticError(
            Diagnostic(
                "filter_unknown",
                f"--rule {report_filter.rule}",
                f"{report_filter.rule!r} is not a rule id this contract declares.",
                "Read violations_by_rule from archkeel report --json for the declared rule "
                "ids, an inside rule included as <component>:<rule id>.",
            )
        )
    known_components = declared_components(observation)
    if report_filter.component is not None and report_filter.component not in known_components:
        raise DiagnosticError(
            Diagnostic(
                "filter_unknown",
                f"--component {report_filter.component}",
                f"{report_filter.component!r} is not a component this contract declares.",
                "Read violations_by_component_pair from archkeel report --json, or the "
                "contract's own component labels, for a valid --component value.",
            )
        )


def select_violations(observation: Observation, report_filter: ReportFilter) -> tuple[Record, ...]:
    """Return the violation records `report_filter` selects, in record order (AD-60).

    Built on `violation_rows` (AD-54), the one place a violation's rule ids and component pair
    are derived, so the HTML table and `--json`'s `filtered_violations` can never select a
    different row than the other. `rule` and `component` each narrow independently; a
    violation matches `component` on either side of the import it crosses, source or target,
    and a violation that crosses no pair (a construct, an unassigned module, a cycle) matches
    no `component` filter at all. An undeclared `rule` or `component` raises, through
    `require_declared_filter`.
    """
    require_declared_filter(observation, report_filter)
    return tuple(
        record
        for row, record in zip(
            violation_rows(observation), observation.records("violations") or (), strict=True
        )
        if (report_filter.rule is None or report_filter.rule in row.fingerprint.rules)
        and (
            report_filter.component is None
            or report_filter.component in (row.source_component, row.target_component)
        )
    )


def observed_violations(observation: Observation) -> tuple[KnownViolation, ...]:
    """Every violation this observation reports, counted per fingerprint and ordered.

    Directional row fields stay separate from identity, but are semantic evidence: validation
    uses them to prove which public entry lost its last importer (AD-85).
    """
    rows = violation_rows(observation)
    counts = Counter(row.fingerprint for row in rows)
    roles: dict[ViolationFingerprint, set[tuple[str, str]]] = {}
    for row in rows:
        if row.source_module is not None and row.target_module is not None:
            roles.setdefault(row.fingerprint, set()).add((row.source_module, row.target_module))
    return _ordered(counts, roles)


def _drift(
    fingerprint: ViolationFingerprint, known: int, observed: int, contracted: bool, rewrite: str
) -> str:
    name = f"{' '.join(fingerprint.rules)} | {' '.join(fingerprint.subjects)}"
    counted = f"({observed} observed, {known} in the baseline)"
    if contracted:
        return f"contracted violation: {name} {counted} inside a baselined cycle{rewrite}"
    if observed > known:
        return f"new violation: {name} {counted}"
    return f"resolved violation: {name} {counted}{rewrite}"


def compare_violations(
    known: tuple[KnownViolation, ...],
    observed: tuple[KnownViolation, ...],
    *,
    cycle_rules: frozenset[str],
    refused: bool = False,
) -> tuple[str, ...]:
    """One line per fingerprint the baseline states wrongly, new violations and resolved ones.

    Counts must match exactly, so the file states today's debt rather than an upper bound: a
    fingerprint the baseline underestimates is new work, and one it overestimates is work
    already done, which has to leave the file in the change that did it (the budget only
    shrinks). Both are failures, because a budget that may exceed the code lets a violation
    someone removed come back unreported. `refused` says the lines explain a `--write-baseline`
    that refused, so none advises running it: the refusal names the way on (AD-106).
    """
    known_counts = _counts(known)
    observed_counts = _counts(observed)
    contracted = cycle_contractions(known, observed, cycle_rules=cycle_rules)
    rewrite = "" if refused else "; rewrite the baseline with --write-baseline"
    return tuple(
        _drift(
            fingerprint,
            known_counts.get(fingerprint, 0),
            observed_counts.get(fingerprint, 0),
            fingerprint in contracted,
            rewrite,
        )
        for fingerprint in sorted(
            known_counts.keys() | observed_counts.keys(),
            key=lambda item: (item.rules, item.subjects),
        )
        if known_counts.get(fingerprint, 0) != observed_counts.get(fingerprint, 0)
    )


def violation_drift_counts(
    known: tuple[KnownViolation, ...],
    observed: tuple[KnownViolation, ...],
    *,
    cycle_rules: frozenset[str],
) -> tuple[int, int]:
    """Return changed fingerprint counts as `(new_or_increased, resolved_or_decreased)`.

    A contracted cycle is neither; the baselined cycle it shrank from counts as resolved.
    """
    known_counts = _counts(known)
    observed_counts = _counts(observed)
    contracted = cycle_contractions(known, observed, cycle_rules=cycle_rules)
    fingerprints = known_counts.keys() | observed_counts.keys()
    new = sum(
        observed_counts.get(item, 0) > known_counts.get(item, 0) and item not in contracted
        for item in fingerprints
    )
    resolved = sum(
        observed_counts.get(item, 0) < known_counts.get(item, 0) for item in fingerprints
    )
    return new, resolved
