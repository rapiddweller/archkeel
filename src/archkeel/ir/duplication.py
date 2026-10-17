# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Name the logic repeated outside the owner the contract declared for it (AD-30).

The claim needs the `shape` a symbol record carries. An observation whose symbols carry no
shape yields UNKNOWN and no candidates, the way regression measurements exist exactly when
the comparison is SUPPORTED (AD-5). It also needs a decision to contradict: the owners are
read from the observation's own declaration records, never from a contract file (AD-10),
and without a declared owner the claim stays empty rather than reporting every structural
twin in the repository, which no architect ever decided.

Complete existing call evidence can distinguish structural twins that call different
canonical declarations. This only refines a review question; it proves no runtime behavior
or constructor result type. Missing or ambiguous evidence retains the original candidate.
"""

from __future__ import annotations

import builtins as _builtins
from collections import defaultdict
from dataclasses import dataclass

from archkeel.ir.architecture_graph import (
    ArchitectureDeclarationKind,
    parse_architecture_declaration_kind,
)

from .architecture_graph import ResolutionKind
from .model import (
    FUNCTION_KINDS,
    ComparisonStatus,
    Evidence,
    Observation,
    Record,
    Verdict,
    in_scope,
    int_value,
    text_value,
)

# Measured on Archkeel: below ten nodes the twins are shapes Python forces, not copies. The
# eight-node group is visit_FunctionDef/visit_AsyncFunctionDef, which ast.NodeVisitor makes
# every collector write twice, and the two-node group is a pair of empty Protocol methods.
MINIMUM_SHAPE_NODES = 10


@dataclass(frozen=True, slots=True)
class RepeatedLogic:
    """One function outside a declared owner whose shape matches one inside it."""

    owner: str
    responsibility: str
    inside: str
    outside: str
    shape_nodes: int


@dataclass(frozen=True, slots=True)
class OwnedLogic:
    """The claim: its support, what it examined, and the repetitions it found."""

    status: ComparisonStatus
    owners: int = 0
    functions: int = 0
    candidates: tuple[RepeatedLogic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, ComparisonStatus):
            _builtins.object.__setattr__(self, "status", ComparisonStatus(self.status))
        if self.status is ComparisonStatus.UNKNOWN and (
            self.owners or self.functions or self.candidates
        ):
            raise ValueError("an unsupported claim names no repetition")


def _owners(observation: Observation) -> tuple[tuple[str, str], ...]:
    """Read every declared SPOT owner as (owner, responsibility) from the observation."""
    return tuple(
        (owner, text_value(record.data.get("responsibility")))
        for record in observation.records("declarations") or ()
        if parse_architecture_declaration_kind(record.kind)
        is ArchitectureDeclarationKind.SPOT_OWNER
        and (owner := text_value(record.data.get("owner")))
    )


def _shapes(observation: Observation) -> dict[tuple[str, int], list[str]] | None:
    """Group every named function and method by its shape, or None without the signal."""
    grouped: dict[tuple[str, int], list[str]] = defaultdict(list)
    seen_shape = False
    for record in observation.records("symbols") or ():
        if record.kind not in FUNCTION_KINDS:
            continue
        shape = text_value(record.data.get("shape"))
        name = text_value(record.data.get("qualified_name"))
        if not shape or not name:
            continue
        seen_shape = True
        grouped[(shape, int_value(record.data.get("shape_nodes")))].append(name)
    return dict(grouped) if seen_shape else None


def _call_target(record: Record) -> str | None:
    """Accept one already-resolved callee, without interpreting constructor results."""
    try:
        status = ResolutionKind(text_value(record.data.get("status")))
    except ValueError:
        return None
    targets = record.data.get("targets")
    count = record.data.get("candidate_count")
    if (
        status != ResolutionKind.RESOLVED
        or record.data.get("candidates_truncated") is not False
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count != 1
        or not isinstance(targets, tuple)
        or len(targets) != 1
        or not isinstance(targets[0], str)
        or not targets[0]
    ):
        return None
    return targets[0]


def _resolved_calls(observation: Observation) -> dict[str, tuple[str, ...]]:
    """Keep complete ordered call sequences; absence means no basis to exclude a pair."""
    calls = observation.records("calls")
    if (
        calls is None
        or observation.coverage.status != Verdict.PASS
        or observation.coverage.calls_analyzed != len(calls)
    ):
        return {}
    definitions: dict[str, Record | None] = {}
    for symbol in observation.records("symbols") or ():
        if symbol.kind in FUNCTION_KINDS and (
            name := text_value(symbol.data.get("qualified_name"))
        ):
            definitions[name] = None if name in definitions else symbol
    grouped: dict[str, list[Record]] = defaultdict(list)
    scopes: set[str] = set()
    for record in calls:
        name = text_value(record.data.get("source_scope"))
        if not name:
            return {}
        scopes.add(name)
        if name in definitions:
            bucket: list[Record] = grouped[name]
            bucket.append(record)
    evidence: dict[str, Evidence] = {item.id: item for item in observation.evidence}
    result: dict[str, tuple[str, ...]] = {}
    for name, rows in grouped.items():
        definition = definitions[name]
        if definition is None or len(definition.evidence_ids) != 1:
            continue
        # Body shapes include nested scopes, whose call correspondence is not established here.
        if any(scope != name and in_scope(scope, name) for scope in scopes):
            continue
        origin = evidence.get(definition.evidence_ids[0])
        if origin is None:
            continue
        positions: dict[tuple[int, int], str] = {}
        for record in rows:
            if (
                record.data.get("source_definition_id") != definition.id
                or len(record.evidence_ids) != 1
            ):
                break
            location = evidence.get(record.evidence_ids[0])
            target = _call_target(record)
            if (
                location is None
                or location.file != origin.file
                or not origin.line <= location.line <= origin.end_line
                or location.column < 0
                or (location.line, location.column) in positions
                or target is None
            ):
                break
            positions[(location.line, location.column)] = target
        else:
            result[name] = tuple(positions[position] for position in sorted(positions))
    return result


def _compatible_calls(left: tuple[str, ...] | None, right: tuple[str, ...] | None) -> bool:
    return not left or not right or len(left) != len(right) or left == right


def _repetitions(
    owner: str,
    responsibility: str,
    groups: dict[tuple[str, int], list[str]],
    calls: dict[str, tuple[str, ...]],
) -> list[RepeatedLogic]:
    found: list[RepeatedLogic] = []
    for (_, nodes), names in groups.items():
        if len(names) < 2 or nodes < MINIMUM_SHAPE_NODES:
            continue
        inside = sorted(name for name in names if in_scope(name, owner))
        outside = sorted(name for name in names if not in_scope(name, owner))
        if not inside or not outside:
            continue
        for name in outside:
            match = next(
                (
                    candidate
                    for candidate in inside
                    if _compatible_calls(calls.get(candidate), calls.get(name))
                ),
                None,
            )
            if match is not None:
                found.append(RepeatedLogic(owner, responsibility, match, name, nodes))
    return found


def repeated_logic(observation: Observation) -> OwnedLogic:
    """Return the logic repeated outside its declared owner, or UNKNOWN without the signal."""
    groups = _shapes(observation)
    if groups is None:
        return OwnedLogic(ComparisonStatus.UNKNOWN)
    owners = _owners(observation)
    calls = _resolved_calls(observation)
    candidates: list[RepeatedLogic] = []
    for owner, responsibility in owners:
        candidates.extend(_repetitions(owner, responsibility, groups, calls))
    return OwnedLogic(
        ComparisonStatus.SUPPORTED,
        owners=len(owners),
        functions=sum(len(names) for names in groups.values()),
        candidates=tuple(
            sorted(candidates, key=lambda item: (item.owner, item.outside, item.inside))
        ),
    )
