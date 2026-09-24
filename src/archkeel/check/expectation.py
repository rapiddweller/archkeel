# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Fixed architecture-change expectation contract for governance checks."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from archkeel.ir.baseline import CycleIdentity, is_contraction
from archkeel.ir.digest import package_digest
from archkeel.ir.model import ArchitectureDelta, DeltaProvenance, Projection, SemanticChange

from .delta import SUPPORTED_DIMENSIONS, require_comparable_runtime
from .ratchets import compare_ratchets

EXPECTATION_SCHEMA_VERSION: Final = "1.2.0"
GUARDRAIL_DIMENSIONS: Final = (
    "violations",
    "cycles",
    "private_crossings",
    "typing_signals",
    "unknowns",
    "dependency_edges",
)
# AD-44: an edge count grows with any new import, so unlike the other five guardrail
# dimensions its aggregate growth is not itself a regression; only a genuinely new,
# undeclared edge is. A removed edge cannot violate a boundary, so it is never checked here.
_COUNT_REGRESSION_DIMENSIONS: Final = frozenset(GUARDRAIL_DIMENSIONS) - {"dependency_edges"}
GUARDRAIL_KEYS: Final = (
    "no_new_violations",
    "no_new_cycles",
    "no_new_private_crossings",
    "no_new_typing_signals",
    "no_new_unknowns",
    "coverage_must_pass",
)
CHANGE_KINDS: Final = frozenset({"added", "removed", "relocated", "changed"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ExpectationError(ValueError):
    """Raised when an expectation or delta cannot be checked safely."""


@dataclass(frozen=True, slots=True)
class ExpectedSemanticChange:
    """One selected deterministic delta fingerprint and its expected cardinality."""

    dimension: str
    change: str
    fingerprint: str
    before_count: int
    after_count: int


@dataclass(frozen=True, slots=True)
class ArchitectureExpectation:
    """Validated, fixed-shape HYPOTHESIS supplied for one architecture change."""

    checker_digest: str
    accepted_digest: str
    baseline_commit: str
    analyzer_digest: str
    contract_digest: str
    baseline_digest: str
    selected_changes: tuple[ExpectedSemanticChange, ...]


@dataclass(frozen=True, slots=True)
class ExpectationResult:
    """Governance result; failures are deterministic policy mismatches (exit 1)."""

    failures: tuple[str, ...]


def sha256_bytes(payload: bytes) -> str:
    """Return the lowercase SHA-256 digest used for immutable input locks."""
    return hashlib.sha256(payload).hexdigest()


def parse_expectation(raw: object) -> ArchitectureExpectation:
    """Validate one expectation without accepting a programmable rule language."""
    expectation = _require_mapping(raw, "architecture expectation")
    required_keys = {
        "schema_version",
        "evidence_class",
        "checker_digest",
        "accepted_digest",
        "baseline_commit",
        "analyzer_digest",
        "contract_digest",
        "baseline_digest",
        "selected_changes",
        "guardrails",
    }
    if set(expectation) != required_keys:
        missing = sorted(required_keys - set(expectation))
        extra = sorted(set(expectation) - required_keys)
        raise ExpectationError(
            f"architecture expectation fields mismatch; missing={missing}, extra={extra}"
        )
    if expectation["schema_version"] != EXPECTATION_SCHEMA_VERSION:
        raise ExpectationError(
            f"architecture expectation schema_version must be {EXPECTATION_SCHEMA_VERSION}"
        )
    if expectation["evidence_class"] != "HYPOTHESIS":
        raise ExpectationError("architecture expectation evidence_class must be HYPOTHESIS")

    checker_digest = _require_sha256(expectation["checker_digest"], "checker_digest")
    accepted_digest = _require_sha256(expectation["accepted_digest"], "accepted_digest")
    baseline_commit = _require_nonempty_string(expectation["baseline_commit"], "baseline_commit")
    if re.fullmatch("[0-9a-f]{40}", baseline_commit) is None:
        raise ExpectationError("baseline_commit must be a full lowercase Git SHA")
    analyzer_digest = _require_sha256(expectation["analyzer_digest"], "analyzer_digest")
    contract_digest = _require_sha256(expectation["contract_digest"], "contract_digest")
    baseline_digest = _require_sha256(expectation["baseline_digest"], "baseline_digest")
    selected_raw = expectation["selected_changes"]
    if not isinstance(selected_raw, list):
        raise ExpectationError("selected_changes must be a list")
    selected = tuple(
        _parse_selected_change(value, index=index) for index, value in enumerate(selected_raw)
    )
    identities = {(item.dimension, item.change, item.fingerprint) for item in selected}
    if len(identities) != len(selected):
        raise ExpectationError("selected_changes must not repeat a semantic fingerprint")

    guardrails = _require_mapping(expectation["guardrails"], "guardrails")
    if set(guardrails) != set(GUARDRAIL_KEYS):
        missing = sorted(set(GUARDRAIL_KEYS) - set(guardrails))
        extra = sorted(set(guardrails) - set(GUARDRAIL_KEYS))
        raise ExpectationError(f"fixed guardrail fields mismatch; missing={missing}, extra={extra}")
    disabled = sorted(key for key in GUARDRAIL_KEYS if guardrails[key] is not True)
    if disabled:
        raise ExpectationError(f"fixed architecture guardrails must be true: {', '.join(disabled)}")

    return ArchitectureExpectation(
        checker_digest=checker_digest,
        accepted_digest=accepted_digest,
        baseline_commit=baseline_commit,
        analyzer_digest=analyzer_digest,
        contract_digest=contract_digest,
        baseline_digest=baseline_digest,
        selected_changes=selected,
    )


def evaluate_expectation(
    delta_model: ArchitectureDelta, expectation: ArchitectureExpectation
) -> ExpectationResult:
    """Compare the typed delta with a validated declaration."""
    require_comparable_runtime(delta_model.baseline.python_version, delta_model.head.python_version)
    _require_matching_provenance(delta_model.provenance, expectation)
    if delta_model.coverage.status != "PASS":
        raise ExpectationError("delta coverage status must be PASS")

    dimension_counts = _require_dimension_counts(delta_model, expectation)
    actual_changes, removed_cycles, added_cycles = _index_semantic_changes(
        delta_model.semantic_changes
    )

    ratchets = delta_model.ratchets
    if ratchets.status != "SUPPORTED" or ratchets.baseline is None or ratchets.head is None:
        raise ExpectationError(
            f"delta regression checks are not safely comparable: {ratchets.reason}"
        )
    failures = list(compare_ratchets(ratchets.baseline, ratchets.head))
    if expectation.selected_changes:
        # A non-empty declaration is checked against what it named; anything else is
        # left to the fixed guardrail dimensions (AD-39).
        declared = {
            (item.dimension, item.change, item.fingerprint) for item in expectation.selected_changes
        }
        failures.extend(_match_selected_changes(expectation.selected_changes, actual_changes))
        failures.extend(
            _guardrail_failures(
                dimension_counts, actual_changes, added_cycles, removed_cycles, declared
            )
        )
    else:
        # An empty declaration asserts "no semantic change"; any change at all breaks it.
        failures.extend(_undeclared_change_failures(actual_changes))
    return ExpectationResult(failures=tuple(sorted(failures)))


def _require_matching_provenance(
    provenance: DeltaProvenance, expectation: ArchitectureExpectation
) -> None:
    for key, actual, expected in (
        ("checker_digest", provenance.checker_digest, expectation.checker_digest),
        ("analyzer_digest", provenance.analyzer_digest, expectation.analyzer_digest),
        ("contract_digest", provenance.contract_digest, expectation.contract_digest),
        ("baseline_digest", provenance.baseline_digest, expectation.baseline_digest),
    ):
        _require_sha256(actual, f"provenance.{key}")
        if not hmac.compare_digest(actual, expected):
            raise ExpectationError(f"delta {key} does not match the architecture expectation")
    if not hmac.compare_digest(expectation.checker_digest, package_digest()):
        raise ExpectationError("checker_digest differs from the running Archkeel package")


def _require_dimension_counts(
    delta_model: ArchitectureDelta, expectation: ArchitectureExpectation
) -> dict[str, tuple[int, int]]:
    dimensions = {item.name: item for item in delta_model.dimensions}
    required_dimensions = {
        *GUARDRAIL_DIMENSIONS,
        *(item.dimension for item in expectation.selected_changes),
    }
    dimension_counts: dict[str, tuple[int, int]] = {}
    for dimension in sorted(required_dimensions):
        if dimension not in SUPPORTED_DIMENSIONS:
            raise ExpectationError(f"unsupported expectation dimension: {dimension}")
        record = dimensions.get(dimension)
        if record is None or record.status != "SUPPORTED":
            raise ExpectationError(f"delta dimension {dimension} is not safely comparable")
        dimension_counts[dimension] = (
            _require_count(record.before_count, f"dimensions.{dimension}.before_count"),
            _require_count(record.after_count, f"dimensions.{dimension}.after_count"),
        )
    return dimension_counts


def _index_semantic_changes(
    semantic_changes: tuple[SemanticChange, ...],
) -> tuple[
    dict[tuple[str, str, str], tuple[int, int]], list[CycleIdentity], dict[str, CycleIdentity]
]:
    actual_changes: dict[tuple[str, str, str], tuple[int, int]] = {}
    removed_cycles: list[CycleIdentity] = []
    added_cycles: dict[str, CycleIdentity] = {}
    for index, change in enumerate(semantic_changes):
        if change.dimension not in SUPPORTED_DIMENSIONS:
            raise ExpectationError(
                f"semantic_changes[{index}] has unsupported dimension {change.dimension!r}"
            )
        _require_change_kind(change.change, f"semantic_changes[{index}].change")
        _require_nonempty_string(change.fingerprint, f"semantic_changes[{index}].fingerprint")
        _require_count(change.before_count, f"semantic_changes[{index}].before_count")
        _require_count(change.after_count, f"semantic_changes[{index}].after_count")
        _validate_change_counts(
            change.change, change.before_count, change.after_count, f"semantic_changes[{index}]"
        )
        identity = (change.dimension, change.change, change.fingerprint)
        if identity in actual_changes:
            raise ExpectationError(f"delta repeats semantic fingerprint: {identity}")
        actual_changes[identity] = (change.before_count, change.after_count)
        if change.dimension == "cycles" and change.change in {"added", "removed"}:
            cycle = _parse_cycle_identity(
                change.after if change.change == "added" else change.before, index=index
            )
            if change.change == "added":
                added_cycles[change.fingerprint] = cycle
            else:
                removed_cycles.append(cycle)
    return actual_changes, removed_cycles, added_cycles


def _match_selected_changes(
    selected_changes: tuple[ExpectedSemanticChange, ...],
    actual_changes: dict[tuple[str, str, str], tuple[int, int]],
) -> list[str]:
    failures = []
    for selected in selected_changes:
        identity = (selected.dimension, selected.change, selected.fingerprint)
        expected_counts = (selected.before_count, selected.after_count)
        actual_counts = actual_changes.get(identity)
        if actual_counts is None:
            failures.append(
                f"missing expected {selected.dimension} {selected.change} "
                f"fingerprint {selected.fingerprint}"
            )
        elif actual_counts != expected_counts:
            failures.append(
                f"count mismatch for {selected.dimension} {selected.fingerprint}: "
                f"expected {expected_counts[0]}->{expected_counts[1]}, "
                f"got {actual_counts[0]}->{actual_counts[1]}"
            )
    return failures


def _guardrail_failures(
    dimension_counts: dict[str, tuple[int, int]],
    actual_changes: dict[tuple[str, str, str], tuple[int, int]],
    added_cycles: dict[str, CycleIdentity],
    removed_cycles: list[CycleIdentity],
    declared: set[tuple[str, str, str]],
) -> list[str]:
    failures = []
    for dimension in GUARDRAIL_DIMENSIONS:
        before_count, after_count = dimension_counts[dimension]
        if dimension in _COUNT_REGRESSION_DIMENSIONS and after_count > before_count:
            failures.append(f"guardrail regression in {dimension}: {before_count}->{after_count}")
        added_fingerprints = sorted(
            fingerprint
            for actual_dimension, kind, fingerprint in actual_changes
            if actual_dimension == dimension and kind == "added"
        )
        if dimension == "cycles":
            added_fingerprints = [
                fingerprint
                for fingerprint in added_fingerprints
                if not is_contraction(added_cycles[fingerprint], removed_cycles)
            ]
        if dimension == "dependency_edges":
            # AD-44: unlike the other five, a named edge is not itself a regression; only
            # one the declaration never mentioned is.
            added_fingerprints = [
                fingerprint
                for fingerprint in added_fingerprints
                if (dimension, "added", fingerprint) not in declared
            ]
        failures.extend(
            f"guardrail added {dimension} fingerprint {fingerprint}"
            for fingerprint in added_fingerprints
        )
    return failures


def _undeclared_change_failures(
    actual_changes: dict[tuple[str, str, str], tuple[int, int]],
) -> list[str]:
    return [
        f"undeclared change in {dimension}: {kind} fingerprint {fingerprint}"
        for dimension, kind, fingerprint in actual_changes
    ]


def _parse_cycle_identity(projection: Projection | None, *, index: int) -> CycleIdentity:
    if projection is None:
        raise ExpectationError(f"semantic_changes[{index}] requires a cycle projection")
    level = _require_nonempty_string(
        projection.data.get("level"), f"semantic_changes[{index}].data.level"
    )
    raw_members = projection.data.get("members")
    if not isinstance(raw_members, tuple) or not raw_members:
        raise ExpectationError(f"semantic_changes[{index}].data.members must be a non-empty list")
    members = tuple(
        _require_nonempty_string(member, f"semantic_changes[{index}].data.members[{member_index}]")
        for member_index, member in enumerate(raw_members)
    )
    if len(set(members)) != len(members):
        raise ExpectationError(
            f"semantic_changes[{index}].data.members must not contain duplicates"
        )
    return CycleIdentity((level,), frozenset(members))


def _parse_selected_change(raw: object, *, index: int) -> ExpectedSemanticChange:
    change = _require_mapping(raw, f"selected_changes[{index}]")
    required_keys = {"dimension", "change", "fingerprint", "before_count", "after_count"}
    if set(change) != required_keys:
        raise ExpectationError(
            f"selected_changes[{index}] must contain exactly {sorted(required_keys)}"
        )
    dimension = _require_nonempty_string(
        change["dimension"], f"selected_changes[{index}].dimension"
    )
    if dimension not in SUPPORTED_DIMENSIONS:
        raise ExpectationError(f"selected_changes[{index}] has unsupported dimension {dimension!r}")
    change_kind = _require_nonempty_string(change["change"], f"selected_changes[{index}].change")
    if change_kind not in CHANGE_KINDS:
        raise ExpectationError(f"selected_changes[{index}] has unsupported change {change_kind!r}")
    before_count = _require_count(change["before_count"], f"selected_changes[{index}].before_count")
    after_count = _require_count(change["after_count"], f"selected_changes[{index}].after_count")
    _validate_change_counts(change_kind, before_count, after_count, f"selected_changes[{index}]")
    return ExpectedSemanticChange(
        dimension=dimension,
        change=change_kind,
        fingerprint=_require_nonempty_string(
            change["fingerprint"], f"selected_changes[{index}].fingerprint"
        ),
        before_count=before_count,
        after_count=after_count,
    )


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ExpectationError(f"{label} must be a JSON object")
    return value


def _require_nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExpectationError(f"{label} must be a non-empty string")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ExpectationError(f"{label} must be a lowercase SHA-256 hex value")
    return value


def _require_count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ExpectationError(f"{label} must be a non-negative integer")
    return value


def _require_change_kind(value: object, label: str) -> str:
    change = _require_nonempty_string(value, label)
    if change not in CHANGE_KINDS:
        raise ExpectationError(f"{label} has unsupported value {change!r}")
    return change


def _validate_change_counts(change: str, before_count: int, after_count: int, label: str) -> None:
    valid = {
        "added": before_count == 0 and after_count > 0,
        "removed": before_count > 0 and after_count == 0,
        "relocated": before_count > 0 and after_count > 0,
        "changed": before_count > 0 and after_count > 0,
    }
    if not valid[change]:
        raise ExpectationError(f"{label} has counts inconsistent with {change}")
