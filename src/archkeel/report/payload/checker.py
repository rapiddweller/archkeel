# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The semantic checker of a payload: what JSON Schema cannot say (AD-361).

It checks equal column lengths, ids in range, the sorted string table, the node tree, the gap
list, measure verdicts, the counts of the summary, the status rule of AD-361 and that each
status other than PASS has a row that explains it. The producer runs it before it writes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from archkeel.report.payload.canonical import STRING_COLUMNS, STRING_LISTS
from archkeel.report.payload.codes import (
    DISPOSITION,
    FINDING_KIND,
    GAP,
    MEASURE_STATE,
    RELATION,
    REVOKING,
    UNKNOWN_REASON,
    UNKNOWN_SOURCE,
    VERDICT,
    code,
)

TABLES = (
    "nodes",
    "measures",
    "units",
    "variants",
    "edges",
    "crossings",
    "permissions",
    "violations",
    "unknowns",
    "findings",
    "carriers",
)
# (table, column) -> the table that the id points into, and whether -1 (absent) is allowed.
_REFERENCES: Mapping[tuple[str, str], tuple[str, bool]] = {
    ("nodes", "parent"): ("nodes", True),
    ("nodes", "package"): ("nodes", True),
    ("measures", "node"): ("nodes", False),
    ("units", "module"): ("nodes", False),
    ("units", "parent"): ("units", True),
    ("variants", "unit"): ("units", False),
    ("edges", "from"): ("nodes", False),
    ("edges", "to"): ("nodes", False),
    ("crossings", "edge"): ("module_edges", False),
    ("crossings", "unit"): ("units", True),
    ("permissions", "component"): ("nodes", False),
    ("permissions", "target"): ("nodes", False),
    ("violations", "source_component"): ("nodes", True),
    ("violations", "target_component"): ("nodes", True),
    ("violations", "node"): ("nodes", True),
    ("unknowns", "node"): ("nodes", False),
    ("findings", "subject"): ("nodes", False),
    ("carriers", "finding"): ("findings", False),
    ("carriers", "unit"): ("units", True),
}
_OFFSETS = {
    ("edges", "via_end"): "via",
    ("violations", "rules_end"): "violation_rules",
    ("violations", "subjects_end"): "violation_subjects",
    ("violations", "evidence_end"): "violation_evidence",
}
_OPTIONAL_STRINGS = {("violations", "kind"), ("unknowns", "kind"), ("unknowns", "detail")}

Table = Mapping[str, Sequence[int]]


_RULE_COUNTS = (
    ("rules_pass", "PASS"),
    ("rules_fail", "FAIL"),
    ("rules_unknown", "UNKNOWN"),
    ("rules_declaration", "DECLARATION"),
)


# The relations that a PASS status or a PASS observation depends on (AD-371): without them the
# payload has no edges, crossings or complete units, so no rule over them was seen.
PASS_NEEDS = frozenset(code(RELATION, r) for r in ("imports", "reexports", "variants"))
_UNKNOWN_REASONS = frozenset({"scope_incomplete", "no_receipt", "undecided", "ownership_blocker"})


def _reason_fits(verdict: str, reason: str) -> bool:
    """The reasons that each rule verdict can have."""
    if verdict == "PASS":
        return reason == "evaluated"
    if verdict == "FAIL":
        return reason == "violations"
    if verdict == "DECLARATION":
        return reason == "declaration"
    return verdict == "UNKNOWN" and reason in _UNKNOWN_REASONS


class PayloadInvalid(ValueError):
    """The payload breaks a rule that JSON Schema cannot state."""


def _table(payload: Mapping[str, object], name: str) -> Table:
    table = payload.get(name)
    if not isinstance(table, dict):
        raise PayloadInvalid(f"table {name} is missing")
    return table


def _ints(payload: Mapping[str, object], name: str) -> list[int]:
    values = payload.get(name)
    return [v for v in values if isinstance(v, int)] if isinstance(values, list) else []


def _rules(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    rules = payload.get("rules")
    return [r for r in rules if isinstance(r, dict)] if isinstance(rules, list) else []


def _flat(payload: Mapping[str, object], name: str, ends: Sequence[int], row: int) -> list[int]:
    return _ints(payload, name)[ends[row - 1] if row else 0 : ends[row]]


def recomputed_status(payload: Mapping[str, object]) -> str:
    """The status rule of AD-361, computed from the payload's own rows.

    1. No Target: UNKNOWN. 2. A violation row: FAIL, unless the observation is incomplete and a
    diagnostic revokes the proofs. 3. An incomplete observation: UNKNOWN. 4. A rule with an
    undecided position or an UNKNOWN verdict: UNKNOWN. 5. Else PASS.
    """
    run = payload.get("run")
    run = run if isinstance(run, dict) else {}
    unknowns = _table(payload, "unknowns")
    diagnostic = code(UNKNOWN_SOURCE, "diagnostic")
    revoking = {code(UNKNOWN_REASON, kind) for kind in REVOKING}
    complete = run.get("observation") == "PASS"
    revoked = not complete and any(
        s == diagnostic and r in revoking
        for s, r in zip(unknowns["source"], unknowns["reason"], strict=False)
    )
    if run.get("target") is not True:
        return "UNKNOWN"
    if _table(payload, "violations")["kind"] and not revoked:
        return "FAIL"
    if not complete:
        return "UNKNOWN"
    if any(r.get("undecided") or r.get("verdict") == "UNKNOWN" for r in _rules(payload)):
        return "UNKNOWN"
    return "PASS"


def _structure(payload: Mapping[str, object], problems: list[str]) -> dict[str, int]:
    sizes: dict[str, int] = {}
    for name in TABLES:
        lengths = {len(column) for column in _table(payload, name).values()}
        if len(lengths) > 1:
            problems.append(f"the columns of table {name} have different lengths")
        sizes[name] = max(lengths, default=0)
    strings = payload.get("strings")
    strings = strings if isinstance(strings, list) else []
    sizes["strings"] = len(strings)
    if strings != sorted(set(strings)):
        problems.append("strings are not unique and sorted by UTF-8 bytes")
    sizes["module_edges"] = sum(1 for level in _table(payload, "edges")["level"] if level == 3)
    for (name, column), (target, optional) in _REFERENCES.items():
        _ids(_table(payload, name)[column], sizes[target], optional, f"{name}.{column}", problems)
    for name, columns in STRING_COLUMNS.items():
        for column in columns:
            required = (name, column) in _OPTIONAL_STRINGS
            _ids(
                _table(payload, name)[column],
                sizes["strings"],
                not required,
                f"{name}.{column}",
                problems,
            )
    for name in STRING_LISTS:
        _ids(_ints(payload, name), sizes["strings"], False, name, problems)
    _ids(_ints(payload, "via"), sizes["module_edges"], False, "via", problems)
    for (name, column), flat in _OFFSETS.items():
        ends = list(_table(payload, name)[column])
        if ends != sorted(ends) or (ends and ends[-1] != len(_ints(payload, flat))):
            problems.append(f"{name}.{column} does not end at the length of {flat}")
    nodes = _table(payload, "nodes")
    parents = list(nodes["parent"])
    if parents[:1] != [-1] or any(not 0 <= p < i for i, p in enumerate(parents) if i):
        problems.append("nodes.parent must point to an earlier node: a loop or a late parent")
    return sizes


def _ids(values: Sequence[int], size: int, optional: bool, where: str, problems: list[str]) -> None:
    low = -1 if optional else 0
    bad = [
        v for v in values if not isinstance(v, int) or isinstance(v, bool) or v < low or v >= size
    ]
    if bad:
        problems.append(f"{where} holds {bad[0]!r}, outside {low}..{size - 1}")


def _measures(payload: Mapping[str, object], problems: list[str]) -> None:
    m = _table(payload, "measures")
    measured = code(MEASURE_STATE, "measured")
    budgets = code(GAP, "G-BUDGETS")
    rows = zip(
        m["state"], m["value"], m["gap"], m["budget"], m["baseline"], m["verdict"], strict=False
    )
    for i, (state, value, gap, budget, baseline, verdict) in enumerate(rows):
        if budget >= 0:
            wanted = code(VERDICT, "within" if value >= budget else "over")
        else:
            wanted = code(VERDICT, "none") if baseline < 0 else verdict
        if verdict != wanted:
            problems.append(f"measures row {i}: the verdict does not follow value and budget")
        if state != measured and gap < 0:
            problems.append(f"measures row {i}: an unknown or undeclared measure names no gap")
        if state == measured and budget < 0 and baseline < 0 and gap != budgets:
            problems.append(
                f"measures row {i}: a measure without budget or baseline must name G-BUDGETS"
            )


def _gaps(payload: Mapping[str, object], problems: list[str]) -> None:
    gaps = payload.get("gaps")
    listed = (
        [g["gap"] for g in gaps if isinstance(g, dict) and isinstance(g.get("gap"), int)]
        if isinstance(gaps, list)
        else []
    )
    if listed != sorted(set(listed)):
        problems.append("gaps must be unique and sorted by code")
    used = {g for g in _table(payload, "measures")["gap"] if g >= 0}
    used |= {g for g in _table(payload, "findings")["gap"] if g >= 0}
    if not used <= set(listed):
        problems.append("gaps does not list every gap that a row names")


def _summary(payload: Mapping[str, object], problems: list[str]) -> None:
    summary = payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    counts = summary.get("counts")
    counts = counts if isinstance(counts, dict) else {}
    findings = _table(payload, "findings")
    cycle = code(FINDING_KIND, "cycle")
    pairs = list(zip(findings["kind"], findings["disposition"], strict=False))
    ranked = sum(1 for k, d in pairs if k == cycle and d == code(DISPOSITION, "ranked"))
    rollup = sum(1 for k, d in pairs if k == cycle and d == code(DISPOSITION, "context"))
    run = payload.get("run")
    not_ranked = run.get("not_ranked") if isinstance(run, dict) else None
    counted = (
        sum(n.get("count", 0) for n in not_ranked if isinstance(n, dict))
        if isinstance(not_ranked, list)
        else 0
    )
    if counts.get("cycles") != ranked or counted != rollup:
        problems.append("summary.counts.cycles or run.not_ranked differs from the cycle findings")
    rules = _rules(payload)
    expected = {
        "violations": len(_table(payload, "violations")["kind"]),
        "unknowns": len(_table(payload, "unknowns")["source"]),
        "undecided": sum(u for r in rules if isinstance(u := r.get("undecided"), int)),
        **{key: sum(1 for r in rules if r.get("verdict") == v) for key, v in _RULE_COUNTS},
    }
    for key, value in expected.items():
        if counts.get(key) != value:
            problems.append(f"summary.counts.{key} is {counts.get(key)!r}, the rows give {value}")
    status = summary.get("status")
    if status != recomputed_status(payload):
        problems.append(
            f"summary.status {status!r} differs from the status rule ({recomputed_status(payload)})"
        )
    _explained(payload, str(status), problems)


def _explained(payload: Mapping[str, object], status: str, problems: list[str]) -> None:
    """Each status other than PASS has a row that explains it (AD-361)."""
    run = payload.get("run")
    run = run if isinstance(run, dict) else {}
    unknowns = _table(payload, "unknowns")
    sources = {UNKNOWN_SOURCE[s] for s in unknowns["source"] if 0 <= s < len(UNKNOWN_SOURCE)}
    rules = _rules(payload)
    violations = _table(payload, "violations")
    if status == "FAIL" and not violations["kind"]:
        problems.append("status FAIL has no violation row")
    if run.get("target") is not True and "run" not in sources:
        problems.append("a run without Target has no unknown row that says so")
    if run.get("observation") != "PASS" and not sources & {"diagnostic", "record"}:
        problems.append("an incomplete observation has no unknown row that explains it")
    if (
        status == "UNKNOWN"
        and not sources
        and not any(r.get("undecided") or r.get("verdict") == "UNKNOWN" for r in rules)
    ):
        problems.append("status UNKNOWN has no row that explains it")
    not_carried = run.get("not_carried")
    missing = PASS_NEEDS & set(not_carried if isinstance(not_carried, list) else [])
    if missing and (status == "PASS" or run.get("observation") == "PASS"):
        problems.append(
            "a PASS status or observation does not carry imports, reexports and variants"
        )
    for rule in rules:
        if not _reason_fits(str(rule.get("verdict")), str(rule.get("reason"))):
            problems.append(f"rule {rule.get('id')} has a reason that its verdict cannot have")
        if rule.get("verdict") == "FAIL" and not rule.get("violations"):
            problems.append(f"rule {rule.get('id')} is FAIL and no violation row cites it")
    strings = _strings(payload)
    citations: dict[str, int] = {}
    for row in range(len(violations["kind"])):
        for name in {
            strings[i] for i in _flat(payload, "violation_rules", violations["rules_end"], row)
        }:
            citations[name] = citations.get(name, 0) + 1
    for rule in rules:
        cited = citations.get(str(rule.get("id")), 0)
        if cited != rule.get("violations"):
            problems.append(
                f"rule {rule.get('id')} counts {rule.get('violations')} violations, "
                f"{cited} rows cite it"
            )


def _strings(payload: Mapping[str, object]) -> list[str]:
    strings = payload.get("strings")
    return [s for s in strings if isinstance(s, str)] if isinstance(strings, list) else []


def check_payload(payload: Mapping[str, object]) -> None:
    """Raise PayloadInvalid with every problem that the payload has."""
    problems: list[str] = []
    _structure(payload, problems)
    if not problems:
        _measures(payload, problems)
        _gaps(payload, problems)
        _summary(payload, problems)
    if problems:
        raise PayloadInvalid("; ".join(problems))
