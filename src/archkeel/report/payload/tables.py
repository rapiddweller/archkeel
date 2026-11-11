# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Turn the typed rows into the columnar tables of the payload (AD-361).

This module is the only place that knows the column order of each table. String cells stay
strings here; `canonical.intern_strings` replaces them with ids into the one string table.
"""

from __future__ import annotations

from collections.abc import Sequence

from archkeel.report.payload.canonical import Table
from archkeel.report.payload.codes import ABSENT, CROSSING_CAP, GAP, LEVEL, code
from archkeel.report.payload.graph import Edge, Unit
from archkeel.report.payload.measures import Finding, MeasureRow, NodeCounts
from archkeel.report.payload.tree import Tree

NODE_COLUMNS = "level parent key name path package modules units fan_in fan_out"
MEASURE_COLUMNS = (
    "node def state value of gap budget budget_source baseline baseline_source verdict"
)
UNIT_COLUMNS = "module name kind vis line end_line parent decl static"
EDGE_COLUMNS = "level from to names sites target rationale omitted via_end"
CROSSING_COLUMNS = "edge name kind unit sites line reexport"
FINDING_COLUMNS = (
    "kind subject value pool absolute relative_permille disposition reason carrier_total"
)


def _columns(rows: Sequence[Sequence[object]], names: str) -> Table:
    return {name: [row[i] for row in rows] for i, name in enumerate(names.split())}


def _nodes(tree: Tree, counts: NodeCounts) -> Table:
    columns = (tree.level, tree.parent, tree.key, tree.name, tree.path, tree.package)
    numbers = (counts.modules, counts.units, counts.fan_in, counts.fan_out)
    return _columns(list(zip(*columns, *numbers, strict=True)), NODE_COLUMNS)


def _measures(rows: Sequence[MeasureRow]) -> Table:
    return _columns(
        [
            (r.node, r.measure, r.state, r.value, r.of, code(GAP, r.gap) if r.gap else ABSENT)
            + (r.budget, r.budget_source, ABSENT, None, r.verdict)
            for r in rows
        ],
        MEASURE_COLUMNS,
    )


def _units(units: Sequence[Unit]) -> Table:
    return _columns(
        [
            (u.module, u.name, u.kind, u.vis, u.line, ABSENT, u.parent, u.decl, u.static)
            for u in units
        ],
        UNIT_COLUMNS,
    )


def _edges(edges: Sequence[Edge], via_end: Sequence[int]) -> Table:
    return _columns(
        [
            (e.level, e.source, e.target, e.names, e.sites, e.target_state, e.rationale)
            + (max(0, len(e.crossings) - CROSSING_CAP), end)
            for e, end in zip(edges, via_end, strict=True)
        ],
        EDGE_COLUMNS,
    )


def _crossings(edges: Sequence[Edge]) -> Table:
    modules = [e for e in edges if e.level == code(LEVEL, "module")]
    return _columns(
        [
            (i, c.name, c.kind, c.unit, c.sites, c.line, c.reexport)
            for i, e in enumerate(modules)
            for c in e.crossings[:CROSSING_CAP]
        ],
        CROSSING_COLUMNS,
    )


def _findings(findings: Sequence[Finding]) -> Table:
    return _columns(
        [
            (f.kind, f.subject, f.value, f.pool, f.absolute, f.relative_permille)
            + (f.disposition, f.reason, f.carrier_total)
            for f in findings
        ],
        FINDING_COLUMNS,
    )


def body_tables(
    tree: Tree,
    counts: NodeCounts,
    measures: Sequence[MeasureRow],
    units: Sequence[Unit],
    edges: Sequence[Edge],
    findings: Sequence[Finding],
) -> tuple[dict[str, Table], list[int]]:
    """Return the tables that grow with the project, and the flat `via` list."""
    via: list[int] = []
    via_end: list[int] = []
    for edge in edges:
        via.extend(edge.via)
        via_end.append(len(via))
    tables = {
        "nodes": _nodes(tree, counts),
        "measures": _measures(measures),
        "units": _units(units),
        "variants": _columns(
            [(i, v) for i, u in enumerate(units) for v in u.variants], "unit name"
        ),
        "edges": _edges(edges, via_end),
        "crossings": _crossings(edges),
        "findings": _findings(findings),
        "carriers": _columns(
            [(i, *carrier) for i, f in enumerate(findings) for carrier in f.carriers],
            "finding name importers unit",
        ),
    }
    return tables, via
