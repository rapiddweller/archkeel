# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Owned Python binding controls; no name resolution or namespace inference."""

from __future__ import annotations

import builtins
from dataclasses import dataclass
from enum import Enum


class ImportKind(Enum):
    MODULE = "module"
    SYMBOL = "symbol"


@dataclass(frozen=True)
class AliasBinding:
    target: str
    kind: ImportKind
    imported_name: str | None = None

    def __post_init__(self) -> None:
        builtins.object.__setattr__(self, "kind", ImportKind(self.kind))


class BindingKind(Enum):
    UNKNOWN = "unknown"
    LOCAL = "local"
    UNBOUND = "unbound"
    DECLARATION = "declaration"
    MODULE = "module"
    SYMBOL = "symbol"
    MIXED = "mixed"


class CompilerScopeKind(Enum):
    MODULE = "module"
    FUNCTION = "function"
    CLASS = "class"


_IMPORT_KINDS = {
    ImportKind.MODULE: BindingKind.MODULE,
    ImportKind.SYMBOL: BindingKind.SYMBOL,
}


def lexical_import_kind(kind: ImportKind) -> BindingKind:
    """Translate the narrower import API into the lexical binding vocabulary."""
    return _IMPORT_KINDS[kind]


def compiler_scope_kind(raw: str) -> CompilerScopeKind | None:
    """Classify the compiler protocol once; an unknown scope authorizes nothing."""
    try:
        return CompilerScopeKind(raw)
    except ValueError:
        return None
