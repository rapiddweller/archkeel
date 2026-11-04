# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: derive the call graph of the Studio from the decoded explore snapshot. No I/O."""

from collections.abc import Mapping, Sequence
from os.path import commonprefix

from .api import (
    CallStatus,
    ComponentRow,
    DeclarationKind,
    Declare,
    EdgeRow,
    Graph,
    Json,
    ModuleRow,
    ScopeKind,
    SymbolKind,
    SymbolRow,
    UnknownRow,
    member,
)

UNOWNED = "(unowned)"
_UNOWNED_TEXT = "Modules that no component owns."
_TEXT_LENGTH = 80
_EXPRESSION_LENGTH = 60
_UNKNOWN_PER_SYMBOL = 4
_PARTIAL_TARGETS = 2

_Row = Mapping[str, Json]
_Component = tuple[str, str, Sequence[str]]


def _rows(model: Mapping[str, Json], section: str) -> list[_Row]:
    rows = model.get(section)
    return [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def _text(value: Json) -> str:
    return value if isinstance(value, str) else ""


def _number(value: Json) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _texts(value: Json) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _data(row: _Row) -> _Row:
    data = row.get("data")
    return data if isinstance(data, Mapping) else {}


def _layout(model: Mapping[str, Json]) -> list[_Component]:
    """The top-level components that explore declared in its own layout, with their modules."""
    owned = {
        _text(_data(row).get("component_id")): _texts(_data(row).get("modules"))
        for row in _rows(model, "scope_observations")
        if member(ScopeKind, row.get("kind")) is ScopeKind.DECLARED
    }
    return [
        (_text(row.get("title")), "", owned.get(_text(row.get("id")), []))
        for row in _rows(model, "declarations")
        if member(DeclarationKind, row.get("kind")) is DeclarationKind.COMPONENT
    ]


def _components(
    model: Mapping[str, Json], names: Sequence[str], declare: Declare
) -> list[_Component]:
    """Contract components, else the explore layout; a module without an owner joins UNOWNED."""
    found = [*declare(names)] or _layout(model)
    components = [component for component in found if component[2]]
    placed = {name for _, _, modules in components for name in modules}
    rest = [name for name in names if name not in placed]
    return [*components, (UNOWNED, _UNOWNED_TEXT, rest)] if rest else components


def _relative(name: str, prefix: Sequence[str]) -> str:
    """The dotted name below the shared prefix of its component; the last part if none is left."""
    parts = name.split(".")
    return ".".join(parts[len(prefix) :]) or parts[-1]


def _modules(
    model: Mapping[str, Json], declare: Declare
) -> tuple[tuple[ComponentRow, ...], tuple[ModuleRow, ...], dict[str, int]]:
    files = {
        _text(row.get("title")): _text(_data(row).get("file")) for row in _rows(model, "modules")
    }
    names = sorted(files)
    components = _components(model, names, declare)
    modules: dict[str, ModuleRow] = {}
    for index, (_, _, found) in enumerate(components):
        owned = [name for name in found if name in files]
        prefix: Sequence[str] = commonprefix([name.split(".") for name in owned])
        for name in owned:
            modules.setdefault(name, ModuleRow(name, files[name], index, _relative(name, prefix)))
    ordered = [modules[name] for name in names]
    return (
        tuple(ComponentRow(label, text) for label, text, _ in components),
        tuple(ordered),
        {row.name: index for index, row in enumerate(ordered)},
    )


def _evidence(model: Mapping[str, Json]) -> dict[str, tuple[int, str]]:
    return {
        _text(row.get("id")): (_number(row.get("line")), _text(row.get("excerpt")).strip())
        for row in _rows(model, "evidence")
    }


def _first(ids: Json, evidence: dict[str, tuple[int, str]]) -> tuple[int, str]:
    return evidence.get(_texts(ids)[0], (0, "")) if _texts(ids) else (0, "")


def _symbols(
    model: Mapping[str, Json], position: dict[str, int], evidence: dict[str, tuple[int, str]]
) -> tuple[tuple[SymbolRow, ...], dict[str, int]]:
    symbols: list[SymbolRow] = []
    index: dict[str, int] = {}
    for row in _rows(model, "symbols"):
        data = _data(row)
        kind = member(SymbolKind, row.get("kind"))
        module, qualified = _text(data.get("module")), _text(data.get("qualified_name"))
        if kind is None or module not in position or not qualified or qualified in index:
            continue
        line, text = _first(row.get("evidence_ids"), evidence)
        name = qualified.removeprefix(f"{module}.")
        index[qualified] = len(symbols)
        symbols.append(SymbolRow(position[module], name, line, kind, text[:_TEXT_LENGTH]))
    return tuple(symbols), index


def _calls(
    model: Mapping[str, Json], index: dict[str, int], evidence: dict[str, tuple[int, str]]
) -> tuple[tuple[EdgeRow, ...], tuple[UnknownRow, ...]]:
    edges: list[EdgeRow] = []
    unknown: list[UnknownRow] = []
    counted: dict[int, int] = {}
    for row in _rows(model, "calls"):
        data = _data(row)
        source = index.get(_text(data.get("source_scope")))
        if source is None:
            continue
        line, _ = _first(row.get("evidence_ids"), evidence)
        status = member(CallStatus, data.get("status"))
        targets = [index[name] for name in _texts(data.get("targets")) if name in index]
        if status is CallStatus.RESOLVED:
            edges += [EdgeRow(source, target, False, line) for target in targets[:1]]
        elif status is CallStatus.PARTIALLY_RESOLVED and targets:
            edges += [EdgeRow(source, target, True, line) for target in targets[:_PARTIAL_TARGETS]]
        elif counted.get(source, 0) < _UNKNOWN_PER_SYMBOL:
            counted[source] = counted.get(source, 0) + 1
            expression = _text(data.get("expression"))[:_EXPRESSION_LENGTH]
            reason = _text(data.get("reason"))[:_EXPRESSION_LENGTH]
            unknown.append(UnknownRow(source, expression, reason, line))
    return tuple(edges), tuple(unknown)


def build_graph(model: Mapping[str, Json], declare: Declare) -> Graph:
    """The components, modules, symbols, call edges and unknown calls of one snapshot."""
    components, modules, position = _modules(model, declare)
    evidence = _evidence(model)
    symbols, index = _symbols(model, position, evidence)
    edges, unknown = _calls(model, index, evidence)
    return Graph(components, modules, symbols, edges, unknown)
