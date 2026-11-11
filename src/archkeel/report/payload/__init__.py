# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Python oracle producer of the report v2 payload (AD-361).

It reads the record sections of a persisted architecture.json and the rule rows of the
evaluator, and it writes canonical bytes. The Rust core writes the same bytes as its `Report`
frame; a test compares both byte for byte.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import replace

from archkeel.report.payload.canonical import encode, intern_strings
from archkeel.report.payload.checker import check_payload
from archkeel.report.payload.codes import EDGE_TARGET, LEVEL, MAX_BYTES, SCHEMA_VERSION, code
from archkeel.report.payload.evaluation import Evaluation, RuleRow, evaluation
from archkeel.report.payload.findings import Finding, build_findings
from archkeel.report.payload.graph import Edge, build_edges, build_units
from archkeel.report.payload.head import (
    RowCounts,
    components_section,
    gaps_section,
    rules_section,
    run_section,
    summary_section,
)
from archkeel.report.payload.measures import MeasureRow, build_measures, gap_blocks, node_counts
from archkeel.report.payload.permissions import build_permissions
from archkeel.report.payload.reasons import build_unknowns, build_violations
from archkeel.report.payload.records import read_records
from archkeel.report.payload.tables import Rows, body_tables
from archkeel.report.payload.tree import build_tree

__all__ = ["Evaluation", "PayloadTooLarge", "RuleRow", "build_payload", "evaluation"]
TABLE_ORDER = ("nodes", "measures", "units", "variants", "edges")
LIST_ORDER = ("violation_rules", "violation_subjects", "violation_evidence")


class PayloadTooLarge(ValueError):
    """The payload is above its byte budget. The producer never truncates in silence."""


def _blocks(
    measures: Sequence[MeasureRow], findings: Sequence[Finding], edges: Sequence[Edge], trend: int
) -> Counter[str]:
    """How many rows each gap blocks: measures, findings, contract lines of edges, trend."""
    blocks: Counter[str] = Counter(gap_blocks(measures))
    blocks.update(f.gap for f in findings if f.gap)
    lines = sum(
        1
        for e in edges
        if e.level == code(LEVEL, "component") and e.target_state != code(EDGE_TARGET, "no_target")
    )
    blocks["G-CONTRACT-LINES"] += lines
    if trend < 2:
        blocks["G-TREND"] += 0
    return blocks


def build_payload(
    document: Mapping[str, object], verdicts: Evaluation, *, max_bytes: int = MAX_BYTES
) -> bytes:
    """Return the canonical payload bytes of one parsed architecture.json and its evaluation."""
    records = read_records(document)
    if not verdicts.target:
        records = replace(records, contract=None)
    tree = build_tree(records)
    units = build_units(records, tree)
    permissions = build_permissions(records, tree)
    edges = build_edges(records, tree, units, permissions)
    findings = build_findings(records, tree, edges, permissions)
    evaluated = frozenset(r.id for r in verdicts.rules if r.evaluated)
    measures = build_measures(records, tree, units, edges, findings, evaluated)
    violations = build_violations(records, tree)
    unknowns = build_unknowns(records, tree, verdicts)
    trend: list[object] = []
    gaps = gaps_section(_blocks(measures, findings, edges, len(trend)))
    rows = Rows(measures, units, edges, permissions, violations, unknowns, findings)
    tables, lists = body_tables(tree, node_counts(tree, units, edges), rows)
    strings = intern_strings(tables, lists)
    counted = RowCounts(len(units), len(violations), len(unknowns), len(gaps))
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run": run_section(records, verdicts),
        "summary": summary_section(records, verdicts, tree, edges, findings, counted),
        "rules": rules_section(records, verdicts.rules),
        "gaps": gaps,
        "components": components_section(tree),
        "trend": trend,
        "strings": strings,
        **{name: tables[name] for name in TABLE_ORDER},
        "via": lists["via"],
        "crossings": tables["crossings"],
        "permissions": tables["permissions"],
        "violations": tables["violations"],
        **{name: lists[name] for name in LIST_ORDER},
        "unknowns": tables["unknowns"],
        "findings": tables["findings"],
        "carriers": tables["carriers"],
    }
    check_payload(payload)
    data = encode(payload)
    if len(data) > max_bytes:
        raise PayloadTooLarge(
            f"the report payload has {len(data)} bytes, above the budget of {max_bytes}"
        )
    return data
