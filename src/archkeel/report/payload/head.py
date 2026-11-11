# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The head of the payload: run, summary, rules, gaps and components (AD-361).

The host prints the summary from this head and from the node 0 rows of `measures`. The status,
the rule verdicts, reasons and undecided positions come from the Decision of the evaluator
(`evaluation.py`); the producer copies them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from archkeel.report.payload.codes import (
    DISPOSITION,
    EDGE_TARGET,
    FINDING_KIND,
    GAP,
    KIND,
    LEVEL,
    MAX_BYTES,
    NOT_CARRIED,
    RELATION,
    code,
)
from archkeel.report.payload.evaluation import Evaluation, RuleRow
from archkeel.report.payload.findings import Finding
from archkeel.report.payload.graph import Edge
from archkeel.report.payload.records import Records
from archkeel.report.payload.tree import Tree


@dataclass(frozen=True)
class RowCounts:
    """The number of rows of the tables that the summary counts."""

    units: int
    violations: int
    unknowns: int
    gaps: int


def run_section(records: Records, verdicts: Evaluation) -> dict[str, object]:
    contract = records.contract
    discovered, read, parsed = records.coverage
    rollup = sum(1 for level, _, backed in records.cycles if level == "package" and not backed)
    return {
        "language": records.language,
        "source": {
            "git_head": records.git_head,
            "dirty": records.dirty,
            "scope": list(records.scope),
        },
        "contract": {"path": contract[0], "digest": contract[1], "schema_version": contract[2]}
        if contract
        else None,
        "coverage": {"files_discovered": discovered, "files_read": read, "files_parsed": parsed},
        "target": verdicts.target,
        "observation": verdicts.observation,
        "not_ranked": [{"kind": "rollup_only_package_cycle", "count": rollup}],
        "not_carried": [code(RELATION, r) for r in NOT_CARRIED],
        "payload_budget": {"max_bytes": MAX_BYTES},
    }


def rules_section(records: Records, rules: Sequence[RuleRow]) -> list[dict[str, object]]:
    titles = {d.id: d.title for d in records.rule_declarations}
    return [
        {
            "id": rule.id,
            "kind": rule.kind,
            "title": titles.get(rule.id, ""),
            "verdict": rule.verdict,
            "evaluated": rule.evaluated,
            "violations": rule.violations,
            "undecided": rule.undecided,
            "reason": rule.reason,
            "rationale": rule.rationale,
            "decided_by": rule.decided_by,
        }
        for rule in sorted(rules, key=lambda r: r.id)
    ]


def gaps_section(blocks: Mapping[str, int]) -> list[dict[str, int]]:
    return [{"gap": code(GAP, g), "blocks": blocks[g]} for g in GAP if g in blocks]


def components_section(tree: Tree) -> list[dict[str, object]]:
    return [
        {
            "node": node,
            "does": list(item.responsibilities),
            "never": list(item.forbidden),
            "decided_by": item.decided_by,
            "provenance": list(item.provenance),
            "role": item.role,
            "public_api": list(item.public_api) if item.public_api is not None else None,
        }
        for node, item in sorted(tree.component_of_node.items())
    ]


def _count(values: Sequence[int], wanted: int) -> int:
    return sum(1 for value in values if value == wanted)


def summary_section(
    records: Records,
    verdicts: Evaluation,
    tree: Tree,
    edges: Sequence[Edge],
    findings: Sequence[Finding],
    rows: RowCounts,
) -> dict[str, object]:
    levels = {name: code(LEVEL, name) for name in LEVEL}
    module_edges = [e for e in edges if e.level == levels["module"]]
    component_edges = [e for e in edges if e.level == levels["component"]]
    crossings = [c.kind for e in module_edges for c in e.crossings]
    targets = [e.target_state for e in component_edges if e.sites > 0]
    rule_verdicts = [r.verdict for r in verdicts.rules]
    dispositions = [f.disposition for f in findings]
    ranked = code(DISPOSITION, "ranked")
    counts = {
        "packages": tree.level.count(levels["package"]),
        "components": tree.level.count(levels["component"]),
        "modules": tree.level.count(levels["module"]),
        "units": rows.units,
        "module_edges": len(module_edges),
        "component_edges": len(component_edges),
        "package_edges": sum(1 for e in edges if e.level == levels["package"]),
        "crossing_names": len(crossings),
        "crossing_names_unbound": _count(crossings, code(KIND, "unknown")),
        "undeclared_edges": _count(targets, code(EDGE_TARGET, "undeclared")),
        "forbidden_edges": _count(targets, code(EDGE_TARGET, "forbidden")),
        "unused_edges": sum(1 for e in component_edges if e.sites == 0),
        "cycles": sum(
            1 for f in findings if f.kind == code(FINDING_KIND, "cycle") and f.disposition == ranked
        ),
        "unowned_modules": sum(1 for m in tree.module_node if m not in tree.chain)
        if records.contract is not None
        else 0,
        "findings_ranked": _count(dispositions, ranked),
        "findings_declared": _count(dispositions, code(DISPOSITION, "declared")),
        "findings_context": _count(dispositions, code(DISPOSITION, "context")),
        "rules_pass": rule_verdicts.count("PASS"),
        "rules_fail": rule_verdicts.count("FAIL"),
        "rules_unknown": rule_verdicts.count("UNKNOWN"),
        "rules_declaration": rule_verdicts.count("DECLARATION"),
        "violations": rows.violations,
        "unknowns": rows.unknowns,
        "undecided": sum(r.undecided for r in verdicts.rules),
        "gaps": rows.gaps,
    }
    return {"status": verdicts.status, "counts": counts}
