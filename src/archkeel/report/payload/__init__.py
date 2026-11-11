# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Python oracle producer of the report v2 payload (AD-361).

It reads the record sections of a persisted architecture.json and the rule rows of the
evaluator, and it writes canonical bytes. The Rust core writes the same bytes as its `Report`
frame; a test compares both byte for byte.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from archkeel.report.payload.canonical import check_tables, encode, intern_strings
from archkeel.report.payload.codes import MAX_BYTES, SCHEMA_VERSION
from archkeel.report.payload.graph import build_edges, build_units
from archkeel.report.payload.head import (
    Evaluation,
    RuleRow,
    components_section,
    evaluation,
    gaps_section,
    rules_section,
    run_section,
    summary_section,
)
from archkeel.report.payload.measures import build_findings, build_measures, gap_blocks, node_counts
from archkeel.report.payload.records import read_records
from archkeel.report.payload.tables import body_tables
from archkeel.report.payload.tree import build_tree

__all__ = ["Evaluation", "PayloadTooLarge", "RuleRow", "build_payload", "evaluation"]


class PayloadTooLarge(ValueError):
    """The payload is above its byte budget. The producer never truncates in silence."""


def build_payload(
    document: Mapping[str, object], verdicts: Evaluation, *, max_bytes: int = MAX_BYTES
) -> bytes:
    """Return the canonical payload bytes of one parsed architecture.json and its evaluation."""
    records = read_records(document)
    if not verdicts.target:
        records = replace(records, contract=None)
    tree = build_tree(records)
    units = build_units(records, tree)
    edges = build_edges(records, tree, units)
    findings = build_findings(records, tree, edges)
    measures = build_measures(
        records,
        tree,
        units,
        edges,
        findings,
        frozenset(r.id for r in verdicts.rules if r.evaluated),
    )
    counts = node_counts(tree, units, edges)
    trend: list[object] = []
    gaps = gaps_section(gap_blocks(measures), len(trend))
    tables, via = body_tables(tree, counts, measures, units, edges, findings)
    strings = intern_strings(tables)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run": run_section(records),
        "summary": summary_section(records, verdicts, tree, len(units), edges, findings, len(gaps)),
        "rules": rules_section(records, verdicts.rules),
        "gaps": gaps,
        "components": components_section(tree),
        "trend": trend,
        "strings": strings,
        "nodes": tables["nodes"],
        "measures": tables["measures"],
        "units": tables["units"],
        "variants": tables["variants"],
        "edges": tables["edges"],
        "via": via,
        "crossings": tables["crossings"],
        "findings": tables["findings"],
        "carriers": tables["carriers"],
    }
    check_tables(payload)
    data = encode(payload)
    if len(data) > max_bytes:
        raise PayloadTooLarge(
            f"the report payload has {len(data)} bytes, above the budget of {max_bytes}"
        )
    return data
