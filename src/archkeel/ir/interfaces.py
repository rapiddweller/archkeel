# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Derive component communication from one observation (AD-9)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .model import FUNCTION_KINDS, Observation, Record, RecordData, in_scope

_CLASS_KINDS = frozenset({"dataclass", "protocol", "enum"})


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

    @property
    def width(self) -> int:
        return len(self.names)


@dataclass(frozen=True, slots=True)
class InterfaceProfile:
    """Measurement-only facade and coupling facts derived from one observation."""

    facades: tuple[FacadeMetric, ...]
    exports: tuple[ExportUsage, ...]
    coupling: tuple[CouplingWidth, ...]


def component_owners(observation: Observation) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return each declared component's label and owned packages (also used by AD-10 flow)."""
    # project_declarations writes each component's label as title and its packages as subjects.
    declarations = observation.records("declarations") or ()
    return tuple(
        (record.title, record.subjects)
        for record in declarations
        if record.kind == "component_responsibility"
    )


def owner_of(module: str, components: tuple[tuple[str, tuple[str, ...]], ...]) -> str | None:
    """Return the one component owning a module, or None if zero or many components claim it."""
    owners = [
        label
        for label, packages in components
        if any(in_scope(module, package) for package in packages)
    ]
    return owners[0] if len(owners) == 1 else None


def _symbols_by_name(observation: Observation) -> dict[str, Record]:
    result: dict[str, Record] = {}
    for record in observation.records("symbols") or ():
        name = record.data.get("qualified_name")
        if isinstance(name, str):
            result[name] = record
    return result


def _symbol_kind(symbol: Record) -> str:
    if symbol.kind != "class":
        return symbol.kind
    class_kind = symbol.data.get("class_kind")
    return class_kind if isinstance(class_kind, str) and class_kind in _CLASS_KINDS else "class"


def _signature(symbol: Record) -> tuple[tuple[str, ...], str]:
    parameters_data = symbol.data.get("parameters")
    parameters: list[str] = []
    if isinstance(parameters_data, tuple):
        for entry in parameters_data:
            if not isinstance(entry, RecordData):
                continue
            annotation = entry.get("annotation")
            rendered = annotation if isinstance(annotation, str) and annotation else "UNKNOWN"
            parameters.append(f"{entry.get('name')}: {rendered}")
    returns = symbol.data.get("returns")
    return tuple(parameters), returns if isinstance(returns, str) and returns else "UNKNOWN"


def _interface_name(item: Record, symbols_by_name: dict[str, Record]) -> InterfaceName:
    data = item.data
    target_module = data.get("target_module")
    symbol_value = data.get("symbol")
    target = target_module if isinstance(target_module, str) else ""
    named = isinstance(symbol_value, str) and symbol_value != "*"
    name = f"{target}:{symbol_value}" if named else target
    origin = data.get("origin_definition")
    resolved = symbols_by_name.get(origin) if isinstance(origin, str) else None
    if resolved is None:
        return InterfaceName(name, "constant", (), "")
    kind = _symbol_kind(resolved)
    if kind not in FUNCTION_KINDS:
        return InterfaceName(name, kind, (), "")
    parameters, returns = _signature(resolved)
    return InterfaceName(name, kind, parameters, returns)


def interface_edges(observation: Observation) -> tuple[InterfaceEdge, ...]:
    """Return the cross-component interface each edge of one observation exercises."""
    components = component_owners(observation)
    symbols_by_name = _symbols_by_name(observation)
    grouped: dict[tuple[str, str], dict[str, InterfaceName]] = {}
    for item in observation.records("imports") or ():
        data = item.data
        source_module = data.get("source_module")
        target_module = data.get("target_module")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        source = owner_of(source_module, components)
        target = owner_of(target_module, components)
        if source is None or target is None or source == target:
            continue
        interface_name = _interface_name(item, symbols_by_name)
        grouped.setdefault((source, target), {})[interface_name.name] = interface_name
    return tuple(
        InterfaceEdge(source, target, tuple(sorted(names.values(), key=lambda n: n.name)))
        for (source, target), names in sorted(grouped.items())
    )


def _facade_declarations(observation: Observation) -> dict[tuple[str, str], frozenset[str] | None]:
    """Return declared facade modules, where None means the whole module is declared."""
    result: dict[tuple[str, str], frozenset[str] | None] = {}
    for record in observation.records("declarations") or ():
        if record.kind != "component_responsibility":
            continue
        public = record.data.get("public")
        if not isinstance(public, tuple):
            continue
        entries: dict[str, set[str] | None] = {}
        for entry in public:
            if not isinstance(entry, str):
                continue
            module, colon, name = entry.partition(":")
            if not module:
                continue
            if not colon:
                entries[module] = None
            elif module not in entries:
                entries[module] = {name}
            elif (names := entries[module]) is not None:
                names.add(name)
        for module, names in entries.items():
            result[(record.title, module)] = None if names is None else frozenset(names)
    return result


def _public_symbol_names(observation: Observation) -> dict[str, frozenset[str]]:
    names: dict[str, set[str]] = defaultdict(set)
    for record in observation.records("symbols") or ():
        module = record.data.get("module")
        name = record.data.get("name")
        if (
            record.data.get("parent") is None
            and record.data.get("visibility") == "public_name"
            and isinstance(module, str)
            and isinstance(name, str)
        ):
            names[module].add(name)
    return {module: frozenset(values) for module, values in names.items()}


def _literal_exports(observation: Observation) -> dict[str, frozenset[str]]:
    return {
        module: frozenset(value for value in exports if isinstance(value, str))
        for record in observation.records("modules") or ()
        if isinstance((module := record.data.get("qualified_name")), str)
        and isinstance((exports := record.data.get("all_exports")), tuple)
    }


def _reexports(observation: Observation) -> dict[str, frozenset[str]]:
    names: dict[str, set[str]] = defaultdict(set)
    for record in observation.records("imports") or ():
        data = record.data
        module = data.get("source_module")
        binding = data.get("binding")
        if (
            data.get("declared_in_all") is True
            and isinstance(module, str)
            and isinstance(binding, str)
        ):
            if not binding.startswith("_") and binding != "*":
                names[module].add(binding)
    return {module: frozenset(values) for module, values in names.items()}


def _declared_facades(
    observation: Observation,
) -> tuple[tuple[FacadeMetric, ...], dict[tuple[str, str], frozenset[str]]]:
    declarations = _facade_declarations(observation)
    all_exports = _literal_exports(observation)
    symbols = _public_symbol_names(observation)
    reexports = _reexports(observation)
    exported: dict[tuple[str, str], frozenset[str]] = {}
    facade_rows: list[FacadeMetric] = []
    for (component, module), declared in sorted(declarations.items()):
        names = (
            all_exports.get(module, frozenset())
            if declared is None and all_exports.get(module)
            else declared
            if declared is not None
            else symbols.get(module, frozenset()) | reexports.get(module, frozenset())
        )
        names = frozenset(name for name in names if name and not name.startswith("_"))
        local = frozenset(name for name in symbols.get(module, frozenset()) if name in names)
        facade_reexports = frozenset(
            name for name in reexports.get(module, frozenset()) if name in names
        )
        exported[(component, module)] = names
        facade_rows.append(
            FacadeMetric(
                component,
                module,
                tuple(sorted(names)),
                tuple(sorted(facade_reexports)),
                tuple(sorted(local)),
                (),
            )
        )

    return tuple(facade_rows), exported


def _profile_parts(
    observation: Observation,
) -> tuple[
    tuple[FacadeMetric, ...],
    tuple[ExportUsage, ...],
    tuple[CouplingWidth, ...],
]:
    components = component_owners(observation)
    facade_rows, exported = _declared_facades(observation)
    consumers: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    pair_names: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in observation.records("imports") or ():
        data = record.data
        source_module = data.get("source_module")
        target_module = data.get("target_module")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        source = owner_of(source_module, components)
        target = owner_of(target_module, components)
        if source is None or target is None or source == target:
            continue
        facade = (target, target_module)
        names = exported.get(facade)
        if names is None:
            continue
        symbol = data.get("symbol")
        if symbol == "*":
            used = names
        elif symbol is None:
            continue
        elif isinstance(symbol, str):
            used = frozenset({symbol}) & names
        else:
            continue
        for name in used:
            consumers[(target, target_module, name)].add(source)
            pair_names[(source, target)].add(f"{target_module}:{name}")

    measured_facades = [
        FacadeMetric(
            row.component,
            row.module,
            row.exported_names,
            row.reexported_names,
            row.defined_names,
            tuple(
                name
                for name in row.reexported_names
                if not consumers[(row.component, row.module, name)]
            ),
        )
        for row in facade_rows
    ]
    export_rows = tuple(
        ExportUsage(component, module, name, tuple(sorted(consumers[(component, module, name)])))
        for component, module in sorted(exported)
        for name in sorted(exported[(component, module)])
    )
    coupling_rows = tuple(
        CouplingWidth(source, target, tuple(sorted(names)))
        for (source, target), names in sorted(pair_names.items())
    )
    return tuple(measured_facades), export_rows, coupling_rows


def interface_profile(observation: Observation) -> InterfaceProfile:
    """Measure declared facades, export consumers and coupling width from one observation."""
    facades, exports, coupling = _profile_parts(observation)
    return InterfaceProfile(facades, exports, coupling)
