# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Name the types passed across the most component boundaries (issue #9, part 3).

The claim needs the `symbols` and `imports` signals `interfaces.py` already reads: `imports`
for which cross-component call reaches a function, `symbols` for that function's own
parameter and return annotations. Either missing reports UNKNOWN and no candidates, the way
a claim without its signal does elsewhere (AD-26). A type crossing many component pairs is
what a target architecture calls a broad context or a service locator; naming the count is
evidence, deciding whether it is a problem stays the architect's, never a verdict here.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .interfaces import component_owners, owner_of
from .model import FUNCTION_KINDS, ComparisonStatus, Observation, RecordData, text_value

# A type used across exactly one component pair is ordinary parameter passing, not fan-in;
# two or more is what makes it a candidate worth an architect's look.
MINIMUM_CROSSINGS = 2


@dataclass(frozen=True, slots=True)
class TypeCrossing:
    """One annotation string and the distinct ordered component pairs it is passed across."""

    annotation: str
    crossings: int


@dataclass(frozen=True, slots=True)
class TypeFanin:
    """The claim: its support, the annotation positions examined, and the widest crossings."""

    status: ComparisonStatus
    positions: int = 0
    candidates: tuple[TypeCrossing, ...] = ()

    def __post_init__(self) -> None:
        if self.status == "UNKNOWN" and (self.positions or self.candidates):
            raise ValueError("an unsupported claim names no crossing")


def _annotations(data: RecordData) -> list[str]:
    """Every non-empty parameter or return annotation a function or method symbol carries."""
    found: list[str] = []
    parameters = data.get("parameters")
    if isinstance(parameters, tuple):
        for entry in parameters:
            if not isinstance(entry, RecordData):
                continue
            annotation = entry.get("annotation")
            if isinstance(annotation, str) and annotation:
                found.append(annotation)
    returns = data.get("returns")
    if isinstance(returns, str) and returns:
        found.append(returns)
    return found


def type_fanin(observation: Observation) -> TypeFanin:
    """Name the annotation strings crossing the most distinct ordered component pairs."""
    if observation.records("symbols") is None or observation.records("imports") is None:
        return TypeFanin("UNKNOWN")
    components = component_owners(observation)
    symbols_by_qualname = {
        name: record
        for record in observation.records("symbols") or ()
        if (name := text_value(record.data.get("qualified_name")))
    }
    # One (source, target, function) triple per crossing function, however many call sites
    # import it: a function imported five times by one component crosses one pair, not five.
    crossed: set[tuple[str, str, str]] = set()
    for item in observation.records("imports") or ():
        data = item.data
        origin = text_value(data.get("origin_definition"))
        resolved = symbols_by_qualname.get(origin) if origin else None
        if resolved is None or resolved.kind not in FUNCTION_KINDS:
            continue
        source = owner_of(text_value(data.get("source_module")), components)
        target = owner_of(text_value(data.get("target_module")), components)
        if source is None or target is None or source == target:
            continue
        crossed.add((source, target, origin))

    positions = 0
    crossings: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for source, target, origin in crossed:
        for annotation in _annotations(symbols_by_qualname[origin].data):
            positions += 1
            crossings[annotation].add((source, target))

    candidates = tuple(
        sorted(
            (
                TypeCrossing(annotation, len(pairs))
                for annotation, pairs in crossings.items()
                if len(pairs) >= MINIMUM_CROSSINGS
            ),
            key=lambda item: (-item.crossings, item.annotation),
        )
    )
    return TypeFanin("SUPPORTED", positions=positions, candidates=candidates)
