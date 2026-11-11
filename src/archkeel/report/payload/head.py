# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The head of the payload: run, summary, rules, gaps and components (AD-361).

The host prints the summary from this head and from the node 0 rows of `measures`. The status
and the rule rows are an input: the evaluator decides each verdict, and the producer only copies
it. This is the `HostRules` input of the Rust core (WP6-0, section B).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from archkeel.report.payload.codes import (
    DISPOSITION,
    EDGE_TARGET,
    GAP,
    KIND,
    LEVEL,
    MAX_BYTES,
    NOT_CARRIED,
    RELATION,
    RULE_VERDICT,
    code,
)
from archkeel.report.payload.graph import Edge
from archkeel.report.payload.measures import Finding
from archkeel.report.payload.records import Records
from archkeel.report.payload.tree import Tree


@dataclass(frozen=True)
class RuleRow:
    """One evaluated rule: the verdict comes from the evaluator, never from the producer."""

    id: str
    kind: str
    verdict: str
    evaluated: bool
    violations: int
    rationale: str
    decided_by: str | None


@dataclass(frozen=True)
class Evaluation:
    """The verdicts of the evaluator: the declared-rules status and one row per rule.

    `target` is false when the run has no Target, as in explore (AD-285): a layout contract
    then groups the modules, and the payload treats the run as a run without a contract.
    """

    status: str
    rules: tuple[RuleRow, ...]
    target: bool = True


def evaluation(result: Mapping[str, object]) -> Evaluation:
    """Read the evaluation of a command result (`archkeel report --json`)."""
    status = result.get("declared_rules")
    if status not in ("PASS", "FAIL", "UNKNOWN"):
        raise ValueError(f"the command result has the unknown declared_rules status {status!r}")
    return Evaluation(str(status), _rule_rows(result), result.get("target") != "unavailable")


def _rule_rows(result: Mapping[str, object]) -> tuple[RuleRow, ...]:
    rows = result.get("rule_assessments")
    out = []
    for item in rows if isinstance(rows, list) else ():
        if not isinstance(item, dict):
            continue
        verdict = str(item.get("status"))
        if verdict not in RULE_VERDICT:
            raise ValueError(f"rule {item.get('id')!r} has the unknown verdict {verdict!r}")
        count = item.get("count")
        rationale = item.get("rationale")
        decided_by = item.get("decided_by")
        out.append(
            RuleRow(
                id=str(item.get("id")),
                kind=str(item.get("kind")),
                verdict=verdict,
                evaluated=item.get("evaluation_proven") is True,
                violations=count if isinstance(count, int) else 0,
                rationale=rationale if isinstance(rationale, str) else "",
                decided_by=decided_by if isinstance(decided_by, str) else None,
            )
        )
    return tuple(out)


def run_section(records: Records) -> dict[str, object]:
    contract = records.contract
    discovered, read, parsed = records.coverage
    rollup = records.metrics.get("rollup_only_package_cycles", 0)
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
            "rationale": rule.rationale,
            "decided_by": rule.decided_by,
        }
        for rule in sorted(rules, key=lambda r: r.id)
    ]


def gaps_section(blocks: Mapping[str, int], trend_points: int) -> list[dict[str, int]]:
    found = dict(blocks)
    if trend_points < 2:
        found.setdefault("G-TREND", 0)
    return [{"gap": code(GAP, g), "blocks": found[g]} for g in GAP if g in found]


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


def summary_section(
    records: Records,
    verdicts: Evaluation,
    tree: Tree,
    units: int,
    edges: Sequence[Edge],
    findings: Sequence[Finding],
    gaps: int,
) -> dict[str, object]:
    levels = {name: code(LEVEL, name) for name in LEVEL}
    module_edges = [e for e in edges if e.level == levels["module"]]
    component_edges = [e for e in edges if e.level == levels["component"]]
    crossings = [c for e in module_edges for c in e.crossings]
    unknown_kind = code(KIND, "unknown")
    rule_verdicts = [r.verdict for r in verdicts.rules]
    cycles = max(0, len(records.cycles) - records.metrics.get("rollup_only_package_cycles", 0))
    counts = {
        "packages": tree.level.count(levels["package"]),
        "components": tree.level.count(levels["component"]),
        "modules": tree.level.count(levels["module"]),
        "units": units,
        "module_edges": len(module_edges),
        "component_edges": len(component_edges),
        "package_edges": sum(1 for e in edges if e.level == levels["package"]),
        "crossing_names": len(crossings),
        "crossing_names_unbound": sum(1 for c in crossings if c.kind == unknown_kind),
        "undeclared_edges": sum(
            1 for e in component_edges if e.target_state == code(EDGE_TARGET, "undeclared")
        ),
        "unused_edges": sum(1 for e in component_edges if e.sites == 0),
        "cycles": cycles,
        "unowned_modules": sum(1 for m in tree.module_node if m not in tree.chain)
        if records.contract is not None
        else 0,
        "findings_ranked": sum(1 for f in findings if f.disposition == code(DISPOSITION, "ranked")),
        "findings_declared": sum(
            1 for f in findings if f.disposition == code(DISPOSITION, "declared")
        ),
        "findings_context": sum(
            1 for f in findings if f.disposition == code(DISPOSITION, "context")
        ),
        "rules_pass": rule_verdicts.count("PASS"),
        "rules_fail": rule_verdicts.count("FAIL"),
        "rules_unknown": rule_verdicts.count("UNKNOWN"),
        "rules_declaration": rule_verdicts.count("DECLARATION"),
        "gaps": gaps,
    }
    return {"status": verdicts.status, "counts": counts}
