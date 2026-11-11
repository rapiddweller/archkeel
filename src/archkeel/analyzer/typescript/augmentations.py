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

import re
from collections.abc import Iterable
from typing import Final, Protocol

from .syntax import Concern, Span

_PATH_START: Final = frozenset("./")
# A directive that names a file of the project: `path`, `lib`, `amd-dependency` (#988) and a `types`
# directive that names a path (#976). A `types` name only adds globals, which the catalog does not
# model (AD-274), unless a type root lies inside the project (AD-354).
_DIRECTIVE: Final = re.compile(
    r"^///\s*<(?:reference\s+(?:path|lib|types(?=\s*=\s*['\"][./]))|amd-dependency\s+path)"
    r"\s*=\s*(['\"])(.*?)\1"
)
_TYPES_NAME: Final = re.compile(r"^///\s*<reference\s+types\s*=\s*(['\"])(.*?)\1")


class Aliases(Protocol):
    """The compiler options that map a bare name to a file: `baseUrl`, `paths` and `typeRoots`."""

    @property
    def base_url(self) -> str | None: ...

    @property
    def paths(self) -> tuple[tuple[str, tuple[str, ...]], ...]: ...

    @property
    def project_type_roots(self) -> bool: ...


def has_aliases(options: Aliases) -> bool:
    """The project sets `paths` or `baseUrl`, so a bare name can reach a file of the project."""
    return options.base_url is not None or bool(options.paths)


def triple_slash(body: str, options: Aliases | None) -> str | None:
    """The quoted text of a triple-slash directive that names a file of the project, else `None`.
    With a type root inside the project, a `types` name is such a file too."""
    found = _DIRECTIVE.match(body)
    if found is None and options is not None and options.project_type_roots:
        found = _TYPES_NAME.match(body)
    return found[2] if found is not None else None


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
