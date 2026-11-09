# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Classify the difference of the measurement budgets and the baseline as widening (#11).

Both are ratchets: a raised, grown or dropped accepted value widens, a lowered one narrows.
`ir.widening` re-exports the four public functions.
"""

from __future__ import annotations

from collections.abc import Mapping

from .baseline import KnownViolation, cycle_contractions, violation_name
from .measurements import MeasurementBudget, name_drift
from .widening_change import WideningChange


def measurement_budget_changes(
    before: tuple[MeasurementBudget, ...],
    after: tuple[MeasurementBudget, ...],
    targets: Mapping[str, int] | None = None,
) -> tuple[WideningChange, ...]:
    """A raised, grown or dropped accepted value widens its measurement budget.

    AD-89 compares a scalar; AD-99 a key's accepted names, where any gained name widens even
    when another one left, because the ratchet holds names rather than their count. `targets`
    are the old contract's `max_names` by label: a key the old baseline did not hold was held by
    that target alone, so a first accepted set above it widens too.
    """
    accepted = {item.label: item for item in after}
    findings: list[WideningChange] = []
    for item in sorted(before, key=lambda budget: budget.label):
        now = accepted.get(item.label)
        if now is None:
            findings.append(
                WideningChange(
                    item.label, "baseline", f"measurement budget baseline lost {item.label}"
                )
            )
            continue
        gained, _ = name_drift(item, now)
        if gained:
            findings.append(
                WideningChange(
                    item.label,
                    "accepted_names",
                    f"measurement budget widened: {item.label} (gained {', '.join(gained)})",
                )
            )
        elif now.value > item.value:
            findings.append(
                WideningChange(
                    item.label,
                    "value",
                    f"measurement budget widened: {item.label} "
                    f"({now.value} now, {item.value} before)",
                )
            )
    held = {item.label for item in before}
    old_targets = targets or {}
    findings.extend(
        WideningChange(
            item.label,
            "value",
            f"measurement budget widened: {item.label} "
            f"({item.value} accepted, target {old_targets[item.label]} before)",
        )
        for item in sorted(after, key=lambda budget: budget.label)
        if item.label not in held
        and item.label in old_targets
        and item.value > old_targets[item.label]
    )
    return tuple(findings)


def measurement_budget_widenings(
    before: tuple[MeasurementBudget, ...],
    after: tuple[MeasurementBudget, ...],
    targets: Mapping[str, int] | None = None,
) -> tuple[str, ...]:
    """Backward-compatible rendered measurement-budget widening messages."""
    return tuple(item.message for item in measurement_budget_changes(before, after, targets))


def baseline_widening_changes(
    before: tuple[KnownViolation, ...],
    after: tuple[KnownViolation, ...],
    *,
    cycle_rules: frozenset[str],
) -> tuple[WideningChange, ...]:
    """A known-violation baseline is part of the contract's surface (#11).

    Padding it to make a new violation disappear is exactly the move a target-first workflow
    invites, so it is compared the same way every other rule is: by fingerprint, a higher count
    or a new fingerprint reported as widening, a lower or removed one left to pass silently.
    Roles do not change fingerprint identity, but AD-85 uses them as directional evidence. Any
    role-only change is therefore protected rather than classified as neutral metadata. A cycle
    that replaces a baselined cycle it lies inside is that cycle contracting (AD-98): narrowing.
    """
    contracted = cycle_contractions(before, after, cycle_rules=cycle_rules)
    before_by_fingerprint = {item.fingerprint: item for item in before}
    after_by_fingerprint = {item.fingerprint: item for item in after}
    findings: list[WideningChange] = []
    for fingerprint in sorted(
        before_by_fingerprint.keys() | after_by_fingerprint.keys(),
        key=lambda item: (item.rules, item.subjects),
    ):
        before_item = before_by_fingerprint.get(fingerprint)
        after_item = after_by_fingerprint.get(fingerprint)
        before_count = before_item.count if before_item is not None else 0
        after_count = after_item.count if after_item is not None else 0
        name = violation_name(fingerprint)
        if after_count > before_count and fingerprint not in contracted:
            findings.append(
                WideningChange(
                    name,
                    "count",
                    f"baseline entry widened: {name} ({after_count} now, {before_count} before)",
                )
            )
        if (
            before_item is not None
            and after_item is not None
            and before_count == after_count
            and before_item.roles != after_item.roles
        ):
            before_roles = ", ".join(
                f"{source} -> {target}" for source, target in before_item.roles
            )
            after_roles = ", ".join(f"{source} -> {target}" for source, target in after_item.roles)
            findings.append(
                WideningChange(
                    name,
                    "roles",
                    f"baseline entry roles changed: {name} "
                    f"({before_roles or 'none'} before; {after_roles or 'none'} now)",
                )
            )
    return tuple(findings)


def baseline_widenings(
    before: tuple[KnownViolation, ...],
    after: tuple[KnownViolation, ...],
    *,
    cycle_rules: frozenset[str],
) -> tuple[str, ...]:
    """Backward-compatible rendered baseline widening messages."""
    return tuple(
        item.message for item in baseline_widening_changes(before, after, cycle_rules=cycle_rules)
    )
