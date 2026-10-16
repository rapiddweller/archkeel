# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read and write measurements, accepted locks, baselines and amendments."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict

from archkeel.ir.amendment import AMENDMENT_SCHEMA_VERSION as AMENDMENT_SCHEMA_VERSION
from archkeel.ir.amendment import Amendment as Amendment
from archkeel.ir.amendment_codec import amendment_bytes as amendment_bytes
from archkeel.ir.amendment_codec import parse_amendment as parse_amendment
from archkeel.ir.baseline import (
    BASELINE_SCHEMA_VERSION,
    LEGACY_BASELINE_SCHEMA_VERSION,
    ROLES_BASELINE_SCHEMA_VERSION,
    SCALAR_BUDGETS_BASELINE_SCHEMA_VERSION,
    KnownViolation,
    ValidationBaseline,
    ViolationFingerprint,
    canonical_fingerprint,
    violation_name,
)
from archkeel.ir.codec_wire import (
    _exact,
    _nonempty,
    _object,
    _raw_object,
    _string,
    _strings,
    decode_json,
)
from archkeel.ir.lock import LOCK_SCHEMA_VERSION, AcceptedLock, LockError
from archkeel.ir.measurements import (
    SCALARS,
    MeasurementBudget,
    MeasurementBudgetName,
    Measurements,
    NameBudgetKind,
    RatchetError,
    RatchetScalars,
    count,
)
from archkeel.ir.measurements import MeasurementResolution as _MeasurementResolution
from archkeel.ir.model import RawJson as RawJson


def _measurement_payload(value: Measurements, *, legacy_calls: bool = False) -> dict[str, RawJson]:
    result = _raw_object(asdict(value))
    if legacy_calls and value.calls_total is None:
        result["calls_total"] = 0
    return result


def _measured(scalars: dict[str, RawJson], key: str, label: str) -> int:
    return count(scalars.get(key, 0), f"{label}.{key}")


def _optional(scalars: dict[str, RawJson], key: str, label: str) -> int | None:
    # AD-97: a scalar the profile does not measure is null, and stays null, never 0.
    return None if scalars.get(key, 0) is None else _measured(scalars, key, label)


def parse_measurements(raw: object, label: str, *, nullable_calls: bool = True) -> Measurements:
    value = _object(raw, label)
    if set(value) != {"scalars", "calls_total", "resolution"}:
        raise RatchetError(f"{label} measurement fields mismatch")
    scalars = _object(value.get("scalars"), f"{label}.scalars")
    scalar_keys = set(SCALARS)
    # Each scalar added later reads as 0 from the payloads written before it existed.
    before_unknown_positions = scalar_keys - {"unknown_positions"}
    before_untyped_private_accesses = before_unknown_positions - {"untyped_private_accesses"}
    if set(scalars) not in (scalar_keys, before_unknown_positions, before_untyped_private_accesses):
        raise RatchetError(f"{label}.scalars must contain exactly {SCALARS}")
    counts = RatchetScalars(
        violations=_measured(scalars, "violations", label),
        cycle_edges=_measured(scalars, "cycle_edges", label),
        private_crossings=_optional(scalars, "private_crossings", label),
        typing_positions=_optional(scalars, "typing_positions", label),
        calls_unresolved=_optional(scalars, "calls_unresolved", label),
        coverage_failures=_measured(scalars, "coverage_failures", label),
        untyped_private_accesses=_optional(scalars, "untyped_private_accesses", label),
        unknown_positions=_measured(scalars, "unknown_positions", label),
    )
    raw_total = value.get("calls_total")
    if raw_total is None and not nullable_calls:
        raise RatchetError(f"{label}: null call totals require a nullable format")
    total = None if raw_total is None else count(raw_total, f"{label}.calls_total")
    # Older unmeasured payloads used zero; measured zero remains a count.
    if total == 0 and counts.calls_unresolved is None:
        total = None
    expected = _MeasurementResolution.MEASURED if total else _MeasurementResolution.NOT_APPLICABLE
    return Measurements(
        counts, total, _measurement_resolution(value.get("resolution"), label, expected)
    )


def _measurement_resolution(
    raw: RawJson, label: str, expected: _MeasurementResolution
) -> _MeasurementResolution:
    try:
        resolution = _MeasurementResolution(raw)
    except ValueError as error:
        raise RatchetError(f"{label}.resolution must be {expected}") from error
    if resolution is not expected:
        raise RatchetError(f"{label}.resolution must be {expected}")
    return resolution


def parse_lock(payload: bytes) -> AcceptedLock:
    try:
        raw = _exact(
            decode_json(payload),
            {
                "schema_version",
                "accepted_commit",
                "observation_digest",
                "config_digest",
                "checker_digest",
                "measurements",
                "approval_ref",
            },
            "accepted lock",
        )
        if raw["schema_version"] not in {"1.0.0", LOCK_SCHEMA_VERSION}:
            raise ValueError("invalid accepted lock schema")
        digests: dict[str, str] = {}
        for key, size in (
            ("accepted_commit", 40),
            ("observation_digest", 64),
            ("config_digest", 64),
            ("checker_digest", 64),
        ):
            value = raw[key]
            if not isinstance(value, str) or re.fullmatch(f"[0-9a-f]{{{size}}}", value) is None:
                raise ValueError(f"invalid lock {key}")
            digests[key] = value
        approval_ref = _string(raw["approval_ref"], "approval_ref")
        if not approval_ref.strip():
            raise ValueError("accepted lock needs an opaque approval_ref")
        return AcceptedLock(
            digests["accepted_commit"],
            digests["observation_digest"],
            digests["config_digest"],
            digests["checker_digest"],
            parse_measurements(
                raw["measurements"],
                "accepted",
                nullable_calls=raw["schema_version"] == LOCK_SCHEMA_VERSION,
            ),
            approval_ref,
        )
    except (ValueError, TypeError, KeyError) as error:
        raise LockError(str(error)) from error


def _known_violation(raw: RawJson, label: str, *, with_roles: bool) -> KnownViolation:
    fields = {"rules", "subjects", "count"}
    value = _object(raw, label)
    if with_roles and set(value) not in (fields, fields | {"roles"}):
        raise ValueError(f"{label} fields mismatch")
    if not with_roles and set(value) != fields:
        raise ValueError(f"{label} fields mismatch")
    occurrences = count(value["count"], f"{label}.count")
    if not occurrences:
        raise ValueError(f"{label}.count must be at least 1")
    roles: tuple[tuple[str, str], ...] = ()
    if with_roles and "roles" in value:
        raw_roles = value["roles"]
        if not isinstance(raw_roles, list):
            raise ValueError(f"{label}.roles must be an array")
        parsed_roles = []
        for index, raw_role in enumerate(raw_roles):
            role = _exact(raw_role, {"source", "target"}, f"{label}.roles[{index}]")
            parsed_roles.append(
                (
                    _string(role["source"], f"{label}.roles[{index}].source"),
                    _string(role["target"], f"{label}.roles[{index}].target"),
                )
            )
        if len(set(parsed_roles)) != len(parsed_roles):
            raise ValueError(f"{label}.roles repeats a role")
        roles = tuple(sorted(parsed_roles))
    return KnownViolation(
        canonical_fingerprint(
            _strings(value["rules"], f"{label}.rules"),
            _strings(value["subjects"], f"{label}.subjects"),
        ),
        occurrences,
        roles,
    )


def _measurement_budget_name(raw: object, label: str) -> MeasurementBudgetName:
    value = _string(raw, label)
    try:
        return MeasurementBudgetName(value)
    except ValueError as error:
        raise ValueError(f"{label} is not a supported measurement budget") from error


def _name_budget_kind(raw: str) -> NameBudgetKind | None:
    try:
        return NameBudgetKind(raw)
    except ValueError:
        return None


def _name_budgets(kind: NameBudgetKind, raw: RawJson, label: str) -> list[MeasurementBudget]:
    """One budget per facade or pair key and its accepted names (AD-99)."""
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    budgets = []
    for key, names in sorted(raw.items()):
        accepted = _strings(names, f"{label}.{key}")
        if list(accepted) != sorted(set(accepted)):
            raise ValueError(f"{label}.{key} must list sorted unique names")
        budgets.append(MeasurementBudget(kind, len(accepted), _nonempty(key, label), accepted))
    return budgets


def parse_validation_baseline(raw: object) -> ValidationBaseline:
    """Read the violation and measurement-budget baseline written by validate."""
    untyped = _object(raw, "baseline")
    schema_version = untyped.get("schema_version")
    versions = {
        LEGACY_BASELINE_SCHEMA_VERSION,
        ROLES_BASELINE_SCHEMA_VERSION,
        SCALAR_BUDGETS_BASELINE_SCHEMA_VERSION,
        BASELINE_SCHEMA_VERSION,
    }
    with_budgets = {SCALAR_BUDGETS_BASELINE_SCHEMA_VERSION, BASELINE_SCHEMA_VERSION}
    if schema_version not in versions:
        raise ValueError(
            f"baseline schema {schema_version!r} cannot be read as {', '.join(sorted(versions))}"
        )
    fields = {"schema_version", "violations", "budgets"}
    document = _exact(
        untyped,
        fields if schema_version in with_budgets else fields - {"budgets"},
        "baseline",
    )
    entries = document["violations"]
    if not isinstance(entries, list):
        raise ValueError("baseline.violations must be an array")
    violations = tuple(
        _known_violation(
            entry,
            f"baseline.violations[{index}]",
            with_roles=schema_version != LEGACY_BASELINE_SCHEMA_VERSION,
        )
        for index, entry in enumerate(entries)
    )
    first: dict[ViolationFingerprint, int] = {}
    for index, item in enumerate(violations):
        if item.fingerprint in first:
            raise ValueError(
                f"baseline.violations[{index}] repeats baseline.violations"
                f"[{first[item.fingerprint]}], {violation_name(item.fingerprint)} (subjects "
                "match in any order); give it one count instead"
            )
        first[item.fingerprint] = index
    ordered = tuple(
        sorted(violations, key=lambda item: (item.fingerprint.rules, item.fingerprint.subjects))
    )
    raw_budgets = document.get("budgets", {})
    if not isinstance(raw_budgets, dict) or not all(isinstance(name, str) for name in raw_budgets):
        raise ValueError("baseline.budgets must be an object")
    budgets: list[MeasurementBudget] = []
    for name, value in sorted(raw_budgets.items()):
        label = f"baseline.budgets.{name}"
        kind = _name_budget_kind(name) if schema_version == BASELINE_SCHEMA_VERSION else None
        if kind is not None:
            budgets.extend(_name_budgets(kind, value, label))
        else:
            budgets.append(
                MeasurementBudget(_measurement_budget_name(name, label), count(value, label))
            )
    return ValidationBaseline(ordered, tuple(budgets))


def parse_baseline(raw: object) -> tuple[KnownViolation, ...]:
    """Read known violations for callers that do not consume measurement budgets."""
    return parse_validation_baseline(raw).violations


def _budgets_payload(budgets: tuple[MeasurementBudget, ...]) -> dict[str, RawJson]:
    """Scalars by name; each keyed kind as one object of key to accepted names (AD-99)."""
    payload: dict[str, RawJson] = {}
    keyed: dict[str, dict[str, RawJson]] = {}
    for item in budgets:
        if item.key:
            keyed.setdefault(item.name, {})[item.key] = list(item.names)
        else:
            payload[item.name] = item.value
    return {**payload, **keyed}


def baseline_bytes(
    violations: tuple[KnownViolation, ...], budgets: tuple[MeasurementBudget, ...] = ()
) -> bytes:
    """Write the baseline indented and one entry per line: this file is read in diffs."""
    payload = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "budgets": _budgets_payload(budgets),
        "violations": [
            {
                "rules": list(item.fingerprint.rules),
                "subjects": list(item.fingerprint.subjects),
                "count": item.count,
                **(
                    {
                        "roles": [
                            {"source": source, "target": target}
                            for source, target in sorted(item.roles)
                        ]
                    }
                    if item.roles
                    else {}
                ),
            }
            for item in sorted(
                violations, key=lambda item: (item.fingerprint.rules, item.fingerprint.subjects)
            )
        ],
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def baseline_digest(
    violations: tuple[KnownViolation, ...], budgets: tuple[MeasurementBudget, ...]
) -> str:
    return hashlib.sha256(baseline_bytes(violations, budgets)).hexdigest()


def absent_baseline_digest(path: str) -> str:
    return hashlib.sha256(b"\0no baseline at " + path.encode()).hexdigest()
