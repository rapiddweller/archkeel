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
# A triple-slash directive is `/// <tag attribute="value" ... />`. tsc lowercases the tag name and
# reads the attributes in any order, so a directive names a file of the project when one attribute
# of the right name is there: `path` or `lib` in `reference`, `path` in `amd-dependency` (#988), and
# a `types` that names a path (#976). A `types` name only adds globals, which the catalog does not
# model (AD-274), unless a type root lies inside the project (AD-354).
_TAG: Final = re.compile(r"^///\s*<([^\s/>]+)\s(.*)")
_ATTRIBUTE: Final = re.compile(r"([^\s=]+)\s*=\s*(['\"])(.*?)\2")
_FILE_ATTRIBUTES: Final = {"reference": ("path", "lib"), "amd-dependency": ("path",)}


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
    """The quoted text of the first attribute of a triple-slash directive that names a file of the
    project, else `None`. With a type root inside the project, a `types` name is such a file too."""
    tag = _TAG.match(body)
    if tag is None:
        return None
    tag_name: str = tag[1]
    attributes: str = tag[2]
    name = tag_name.lower()
    for found in re.finditer(_ATTRIBUTE, attributes):
        attribute_name: str = found[1]
        value: str = found[3]
        attribute = attribute_name.lower()
        if attribute in _FILE_ATTRIBUTES.get(name, ()):
            return value
        if name == "reference" and attribute == "types" and _names_a_file(value, options):
            return value
    return None


def _names_a_file(value: str, options: Aliases | None) -> bool:
    return value[:1] in _PATH_START or (options is not None and options.project_type_roots)


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
