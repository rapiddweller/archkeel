# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Turn the typed rows into the columnar tables of the payload (AD-361).

This module is the only place that knows the column order of each table. String cells stay
strings here; `canonical.intern_strings` replaces them with ids into the one string table.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from archkeel.report.payload.canonical import Table
from archkeel.report.payload.codes import ABSENT, CROSSING_CAP, GAP, LEVEL, code
from archkeel.report.payload.findings import Finding
from archkeel.report.payload.graph import Edge, Unit
from archkeel.report.payload.measures import MeasureRow, NodeCounts
from archkeel.report.payload.permissions import Permission
from archkeel.report.payload.reasons import UnknownRow, ViolationRow
from archkeel.report.payload.tree import Tree

NODE_COLUMNS = "level parent key name path package modules units fan_in fan_out"
MEASURE_COLUMNS = (
    "node def state value of gap budget budget_source baseline baseline_source verdict"
)
UNIT_COLUMNS = "module name kind vis line end_line parent decl static"
EDGE_COLUMNS = "level from to names sites target rationale omitted via_end"
CROSSING_COLUMNS = "edge name kind unit sites line reexport"
FINDING_COLUMNS = (
    "kind subject value pool absolute relative_permille disposition reason carrier_total gap"
)
PERMISSION_COLUMNS = "component target status rule"
VIOLATION_COLUMNS = (
    "kind rules_end subjects_end source_module target_module symbol source_component "
    "target_component evidence_end path line node"
)
UNKNOWN_COLUMNS = "source reason kind node rule detail"


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
            + (f.disposition, f.reason, f.carrier_total, code(GAP, f.gap) if f.gap else ABSENT)
            for f in findings
        ],
        FINDING_COLUMNS,
    )


def _violations(rows: Sequence[ViolationRow]) -> tuple[Table, dict[str, list[object]]]:
    """The violation table and its three flat lists; a row owns `list[end[i-1] .. end[i]]`."""
    rules: list[object] = []
    subjects: list[object] = []
    evidence: list[object] = []
    cells = []
    for r in rows:
        rules.extend(r.rules)
        subjects.extend(r.subjects)
        evidence.extend(r.evidence)
        cells.append(
            (r.kind, len(rules), len(subjects), r.source_module, r.target_module, r.symbol)
            + (r.source_component, r.target_component, len(evidence), r.path, r.line, r.node)
        )
    flat = {
        "violation_rules": rules,
        "violation_subjects": subjects,
        "violation_evidence": evidence,
    }
    return _columns(cells, VIOLATION_COLUMNS), flat


@dataclass(frozen=True)
class Rows:
    """The typed rows of every table that grows with the project."""

    measures: Sequence[MeasureRow]
    units: Sequence[Unit]
    edges: Sequence[Edge]
    permissions: Sequence[Permission]
    violations: Sequence[ViolationRow]
    unknowns: Sequence[UnknownRow]
    findings: Sequence[Finding]


def body_tables(
    tree: Tree, counts: NodeCounts, rows: Rows
) -> tuple[dict[str, Table], dict[str, list[object]]]:
    """Return the tables that grow with the project, and the flat lists (`via`, violations)."""
    measures, units, edges, findings = rows.measures, rows.units, rows.edges, rows.findings
    via: list[int] = []
    via_end: list[int] = []
    for edge in edges:
        via.extend(edge.via)
        via_end.append(len(via))
    violations, flat = _violations(rows.violations)
    tables = {
        "nodes": _nodes(tree, counts),
        "measures": _measures(measures),
        "units": _units(units),
        "variants": _columns(
            [(i, v) for i, u in enumerate(units) for v in u.variants], "unit name"
        ),
        "edges": _edges(edges, via_end),
        "crossings": _crossings(edges),
        "permissions": _columns(
            [(p.component, p.target, p.status, p.rule) for p in rows.permissions],
            PERMISSION_COLUMNS,
        ),
        "violations": violations,
        "unknowns": _columns(
            [(u.source, u.reason, u.kind, u.node, u.rule, u.detail) for u in rows.unknowns],
            UNKNOWN_COLUMNS,
        ),
        "findings": _findings(findings),
        "carriers": _columns(
            [(i, *carrier) for i, f in enumerate(findings) for carrier in f.carriers],
            "finding name importers unit",
        ),
    }
    return tables, {"via": list(via), **flat}
