# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Immutable interface and coupling measurements, independent of their derivation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InterfaceName:
    name: str
    kind: str
    parameters: tuple[str, ...]
    returns: str


@dataclass(frozen=True, slots=True)
class InterfaceEdge:
    source: str
    target: str
    names: tuple[InterfaceName, ...]


@dataclass(frozen=True, slots=True)
class FacadeMetric:
    """One declared facade module and the names it makes available."""

    component: str
    module: str
    exported_names: tuple[str, ...]
    reexported_names: tuple[str, ...]
    defined_names: tuple[str, ...]
    unused_reexports: tuple[str, ...]
    # AD-99: False for a whole-module entry whose `__all__` the analyzer did not prove to be one
    # non-empty literal: its imports, computed assignments or later `__all__` additions go
    # unlisted, and `interface_boundary` reads an empty `__all__` as none at all.
    enumerated: bool

    @property
    def exported_name_count(self) -> int:
        return len(self.exported_names)

    @property
    def reexport_count(self) -> int:
        return len(self.reexported_names)


@dataclass(frozen=True, slots=True)
class ExportUsage:
    """One facade export and the distinct components consuming it."""

    component: str
    module: str
    name: str
    consumers: tuple[str, ...]

    @property
    def consumer_count(self) -> int:
        return len(self.consumers)


@dataclass(frozen=True, slots=True)
class CouplingWidth:
    """Distinct declared facade names used by one ordered component pair."""

    source: str
    target: str
    names: tuple[str, ...]
    # AD-99: imports that reach the target without naming what they use - a whole module, a
    # star outside an enumerated facade, or a name a non-enumerated facade does not list - so
    # `width` is a lower bound while this is not empty.
    uncounted: tuple[str, ...]

    @property
    def width(self) -> int:
        return len(self.names)


@dataclass(frozen=True, slots=True)
class InterfaceProfile:
    """Measurement-only facade and coupling facts derived from one observation."""

    facades: tuple[FacadeMetric, ...]
    exports: tuple[ExportUsage, ...]
    coupling: tuple[CouplingWidth, ...]
