# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read which `declare module "x"` names of a file can reach a file of the project (#976).

tsc resolves the name of a module augmentation like an import. A relative or absolute name reaches
a file of the project. A bare name reaches one only through `paths` or `baseUrl`, and only in a
module file: in a script, `declare module "x"` declares an ambient module. A wildcard name is a
pattern, not a module (TS2664). The resolver is not asked: when `paths` or `baseUrl` is set, a bare
name is a concern, as an unproved reference is. This module takes names and spans and reads no tree.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from .syntax import Concern, Span

_PATH_START: Final = frozenset("./")


def augmentation_concerns(
    names: Iterable[tuple[str, Span]], module_file: bool, aliased: bool
) -> list[Concern]:
    """The concerns of the augmentation names of one file; `aliased` is whether the project sets
    `paths` or `baseUrl`."""
    return [
        Concern(f"Unobserved module augmentation: {name}", span)
        for name, span in names
        if name[:1] in _PATH_START or (module_file and aliased and name and "*" not in name)
    ]
