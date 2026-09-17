# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Name the parameters and locals nothing in their own function reads (AD-26).

The claim needs the `bindings` signal. An observation that carries no such section yields
UNKNOWN and no candidates, the way regression measurements exist exactly when the
comparison is SUPPORTED (AD-5). Unlike the unreferenced-symbol claim this one resolves
nothing across modules, so it is supported wherever the analyzer ran; what it cannot do is
count the bindings the collector set aside, and it therefore reports the functions it
examined as its denominator instead of a number it never observed.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import FUNCTION_KINDS, ComparisonStatus, Observation, text_value


@dataclass(frozen=True, slots=True)
class UnreadBinding:
    """One parameter or local that no expression in its own function reads."""

    owner: str
    name: str
    binding: str
    module: str


@dataclass(frozen=True, slots=True)
class BindingReads:
    """The claim: its support, the functions examined, and the bindings nothing reads."""

    status: ComparisonStatus
    functions: int = 0
    candidates: tuple[UnreadBinding, ...] = ()

    def __post_init__(self) -> None:
        if self.status == "UNKNOWN" and (self.functions or self.candidates):
            raise ValueError("an unsupported claim names no binding")


def unread_bindings(observation: Observation) -> BindingReads:
    """Return the bindings nothing reads, or UNKNOWN when the signal is missing."""
    records = observation.records("bindings")
    if records is None:
        return BindingReads("UNKNOWN")
    functions = sum(
        1 for record in observation.records("symbols") or () if record.kind in FUNCTION_KINDS
    )
    candidates = tuple(
        sorted(
            (
                UnreadBinding(
                    owner=text_value(record.data.get("owner")),
                    name=text_value(record.data.get("name")),
                    binding=text_value(record.data.get("binding")),
                    module=text_value(record.data.get("module")),
                )
                for record in records
            ),
            key=lambda item: (item.owner, item.name),
        )
    )
    return BindingReads("SUPPORTED", functions=functions, candidates=candidates)
