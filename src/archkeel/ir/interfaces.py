# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Derive component communication from one observation (AD-9)."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Observation, Record, RecordData, in_scope

_FUNCTION_KINDS = frozenset({"function", "method"})
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


def _components(observation: Observation) -> tuple[tuple[str, tuple[str, ...]], ...]:
    # project_declarations writes each component's label as title and its packages as subjects.
    declarations = observation.records("declarations") or ()
    return tuple(
        (record.title, record.subjects)
        for record in declarations
        if record.kind == "component_responsibility"
    )


def _owner(module: str, components: tuple[tuple[str, tuple[str, ...]], ...]) -> str | None:
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
    if kind not in _FUNCTION_KINDS:
        return InterfaceName(name, kind, (), "")
    parameters, returns = _signature(resolved)
    return InterfaceName(name, kind, parameters, returns)


def interface_edges(observation: Observation) -> tuple[InterfaceEdge, ...]:
    """Return the cross-component interface each edge of one observation exercises."""
    components = _components(observation)
    symbols_by_name = _symbols_by_name(observation)
    grouped: dict[tuple[str, str], dict[str, InterfaceName]] = {}
    for item in observation.records("imports") or ():
        data = item.data
        source_module = data.get("source_module")
        target_module = data.get("target_module")
        if not isinstance(source_module, str) or not isinstance(target_module, str):
            continue
        source = _owner(source_module, components)
        target = _owner(target_module, components)
        if source is None or target is None or source == target:
            continue
        interface_name = _interface_name(item, symbols_by_name)
        grouped.setdefault((source, target), {})[interface_name.name] = interface_name
    return tuple(
        InterfaceEdge(source, target, tuple(sorted(names.values(), key=lambda n: n.name)))
        for (source, target), names in sorted(grouped.items())
    )
