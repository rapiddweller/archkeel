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
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .model import FUNCTION_KINDS, ComparisonStatus, Observation, in_scope, int_value, text_value

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
        if self.status == "UNKNOWN" and (self.owners or self.functions or self.candidates):
            raise ValueError("an unsupported claim names no repetition")


def _owners(observation: Observation) -> tuple[tuple[str, str], ...]:
    """Read every declared SPOT owner as (owner, responsibility) from the observation."""
    return tuple(
        (owner, text_value(record.data.get("responsibility")))
        for record in observation.records("declarations") or ()
        if record.kind == "spot_owner" and (owner := text_value(record.data.get("owner")))
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


def _repetitions(
    owner: str, responsibility: str, groups: dict[tuple[str, int], list[str]]
) -> list[RepeatedLogic]:
    found: list[RepeatedLogic] = []
    for (_, nodes), names in groups.items():
        if len(names) < 2 or nodes < MINIMUM_SHAPE_NODES:
            continue
        inside = sorted(name for name in names if in_scope(name, owner))
        outside = sorted(name for name in names if not in_scope(name, owner))
        if not inside or not outside:
            continue
        found.extend(
            RepeatedLogic(
                owner=owner,
                responsibility=responsibility,
                inside=inside[0],
                outside=name,
                shape_nodes=nodes,
            )
            for name in outside
        )
    return found


def repeated_logic(observation: Observation) -> OwnedLogic:
    """Return the logic repeated outside its declared owner, or UNKNOWN without the signal."""
    groups = _shapes(observation)
    if groups is None:
        return OwnedLogic("UNKNOWN")
    owners = _owners(observation)
    candidates: list[RepeatedLogic] = []
    for owner, responsibility in owners:
        candidates.extend(_repetitions(owner, responsibility, groups))
    return OwnedLogic(
        "SUPPORTED",
        owners=len(owners),
        functions=sum(len(names) for names in groups.values()),
        candidates=tuple(
            sorted(candidates, key=lambda item: (item.owner, item.outside, item.inside))
        ),
    )
