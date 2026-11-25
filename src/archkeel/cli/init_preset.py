# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The presets of `archkeel init --preset` (AD-1087): a layered or hexagonal draft.

The user names the layers; the preset never guesses a name. It adds `layer` to the named
components and writes only rule kinds that exist: `forbidden_dependency` for each inner layer and
each outer layer (this checks imports), `sibling_isolation` for the adapters of a hexagonal draft,
and `layer_order`. `layer_order` checks declared `requires` only, so it keeps a later `requires`
honest and does not check imports itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations, product
from typing import Final, TypeAlias

from .init_areas import NothingToDraft, _slug

# One layer that holds all adapters: they sit outside the core, side by side.
_ADAPTERS: Final = "adapters"

PresetRule: TypeAlias = tuple[str, str, str, dict[str, object]]


class Preset(StrEnum):
    """The shape of the intended architecture."""

    LAYERED = "layered"
    HEXAGONAL = "hexagonal"


@dataclass(frozen=True)
class Shape:
    """A preset and the names of the user. `layers` run from the outermost to the innermost."""

    preset: Preset
    layers: tuple[str, ...]
    adapters: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        names = (*self.layers, *self.adapters)
        if not all(names):
            raise ValueError("a name in --layers or --adapters is empty")
        if len(set(names)) != len(names):
            raise ValueError("--layers and --adapters name a component twice")
        match self.preset:
            case Preset.LAYERED:
                if len(self.layers) < 2 or self.adapters:
                    raise ValueError("--preset layered needs --layers with two or more names")
            case Preset.HEXAGONAL:
                if not self.layers or len(self.adapters) < 2:
                    raise ValueError(
                        "--preset hexagonal needs --layers (the core) and --adapters (two or more)"
                    )
                if _ADAPTERS in self.layers:
                    raise ValueError(f"a core layer cannot be named {_ADAPTERS}")

    def _levels(self) -> list[tuple[str, tuple[str, ...]]]:
        """The layers from the innermost to the outermost, each with its component labels."""
        levels: list[tuple[str, tuple[str, ...]]] = [
            (name, (name,)) for name in reversed(self.layers)
        ]
        return [*levels, (_ADAPTERS, self.adapters)] if self.adapters else levels

    def layer_of(self) -> dict[str, str]:
        """The layer of each named component."""
        return {label: layer for layer, labels in self._levels() for label in labels}

    def rules(self, packages: Mapping[str, tuple[str, ...]]) -> list[PresetRule]:
        """The rules as (id, kind, rationale, fields). `packages` maps each component label of
        the layout to the names that it owns."""
        named = self.layer_of()
        if missing := [label for label in named if label not in packages]:
            raise NothingToDraft(
                f"the layout has no component named {', '.join(missing)}; "
                f"its components are {', '.join(packages)}."
            )
        if many := [label for label in named if len(packages[label]) != 1]:
            raise NothingToDraft(f"{', '.join(many)} must own exactly one package or module.")
        owned = {label: packages[label][0] for label in named}
        levels = self._levels()
        rules: list[PresetRule] = []
        for (_, inner), (_, outer) in combinations(levels, 2):
            for near, far in product(inner, outer):
                rules.append(
                    (
                        f"LAYER-{_slug(near)}-NOT-{_slug(far)}",
                        "forbidden_dependency",
                        f"The inner layer {near} does not depend on the outer layer {far}.",
                        {
                            "source": owned[near],
                            "target": owned[far],
                            "include_type_checking": True,
                        },
                    )
                )
        if self.adapters:
            rules.append(
                (
                    "ADAPTERS-ISOLATED",
                    "sibling_isolation",
                    "Adapters reach each other through the core and never import each other.",
                    {"members": [owned[label] for label in self.adapters]},
                )
            )
        rules.append(
            (
                "LAYER-ORDER",
                "layer_order",
                "A declared requirement points from an outer layer to an inner layer, never back.",
                {"layers": [layer for layer, _ in levels], "components": list(named)},
            )
        )
        return rules
