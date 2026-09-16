# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Name the symbols one observation never references (AD-26).

The claim needs the `references` signal: without it a call graph alone reports every
function that is only handed to a table, and every property read as an attribute, as
unreferenced. An observation that carries no such section therefore yields UNKNOWN and
no candidates, the way regression measurements exist exactly when the comparison is
SUPPORTED (AD-5). The claim stays a review claim: it never becomes a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import ComparisonStatus, Observation, Record


@dataclass(frozen=True, slots=True)
class UnreferencedSymbol:
    """One declared symbol that no call, reference or import in the scan scope names."""

    name: str
    kind: str
    visibility: str
    module: str


@dataclass(frozen=True, slots=True)
class SymbolReferences:
    """The claim: its support, its candidates, and how many symbols it set aside."""

    status: ComparisonStatus
    symbols: int = 0
    exempt: int = 0
    candidates: tuple[UnreferencedSymbol, ...] = ()

    def __post_init__(self) -> None:
        if self.status == "UNKNOWN" and (self.symbols or self.exempt or self.candidates):
            raise ValueError("an unsupported claim names no symbols")


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _referenced(observation: Observation) -> set[str]:
    names: set[str] = set()
    for section in ("calls", "references"):
        for record in observation.records(section) or ():
            targets = record.data.get("targets")
            if isinstance(targets, tuple | list):
                names.update(target for target in targets if isinstance(target, str))
    for record in observation.records("imports") or ():
        module = _text(record.data.get("target_module"))
        symbol = _text(record.data.get("symbol"))
        if module:
            names.add(f"{module}.{symbol}" if symbol else module)
    return names


def _is_exempt(symbol: Record, classes: dict[str, Record]) -> bool:
    """Runtime dispatch and declared interfaces are used without naming the symbol."""
    name = _text(symbol.data.get("qualified_name"))
    leaf = name.rsplit(".", 1)[-1]
    if leaf.startswith("__") and leaf.endswith("__"):
        return True
    if symbol.data.get("declared_in_all"):
        return True
    owner = classes.get(_text(symbol.data.get("parent")))
    return bool(owner and owner.data.get("bases"))


def unreferenced_symbols(observation: Observation) -> SymbolReferences:
    """Return the symbols nothing references, or UNKNOWN when the signal is missing."""
    if observation.records("references") is None:
        return SymbolReferences("UNKNOWN")
    symbols = observation.records("symbols") or ()
    classes = {
        name: record
        for record in symbols
        if (name := _text(record.data.get("qualified_name"))) and record.kind == "class"
    }
    referenced = _referenced(observation)
    candidates: list[UnreferencedSymbol] = []
    exempt = 0
    for record in symbols:
        name = _text(record.data.get("qualified_name"))
        if not name or name in referenced:
            continue
        if _is_exempt(record, classes):
            exempt += 1
            continue
        candidates.append(
            UnreferencedSymbol(
                name=name,
                kind=record.kind,
                visibility=_text(record.data.get("visibility")),
                module=_text(record.data.get("module")),
            )
        )
    return SymbolReferences(
        "SUPPORTED",
        symbols=len(symbols),
        exempt=exempt,
        candidates=tuple(sorted(candidates, key=lambda item: item.name)),
    )
