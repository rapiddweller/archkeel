# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Deterministic recorded Atlas deviations and their existing wire value."""

from dataclasses import dataclass
from enum import StrEnum

from archkeel.ir.model import stable_id


class AtlasDeviationKind(StrEnum):
    ALLOWED_UNUSED = "allowed_unused"
    UNDECLARED = "undeclared"


@dataclass(frozen=True, slots=True)
class AtlasDeviation:
    id: str
    kind: AtlasDeviationKind
    source_id: str
    target_id: str
    level_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", AtlasDeviationKind(self.kind))

    def to_wire(self) -> dict[str, str | None]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "level_id": self.level_id,
        }


def level_deviations(
    level_id: str | None,
    declared: set[tuple[str, str]],
    used: set[tuple[str, str]],
) -> tuple[AtlasDeviation, ...]:
    return tuple(
        AtlasDeviation(
            stable_id("atlas-deviation", level_id, kind, source, target),
            kind,
            source,
            target,
            level_id,
        )
        for kind, pairs in (
            (AtlasDeviationKind.ALLOWED_UNUSED, sorted(declared - used)),
            (AtlasDeviationKind.UNDECLARED, sorted(used - declared)),
        )
        for source, target in pairs
    )
