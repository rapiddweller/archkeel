# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Every FAIL, UNKNOWN, gap and permission of a run has a row in the report v2 payload (AD-361).

Each test compares the payload with what the current report shows for the same run:
architecture.json, the printed result and `report --only architecture`.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence

import pytest
from report_payload_support import CASES, run_case

from archkeel.api import load_violations
from archkeel.report.payload import build_payload, evaluation
from archkeel.report.payload.checker import recomputed_status
from archkeel.report.payload.codes import (
    FINDING_KIND,
    GAP,
    MEASURE,
    PERMISSION,
    UNKNOWN_REASON,
    UNKNOWN_SOURCE,
)

Payload = dict[str, object]


@pytest.fixture(scope="session")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> str:
    return str(tmp_path_factory.mktemp("report-payload-reasons"))


def _payload(case: str, workdir: str) -> Payload:
    run = run_case(case, workdir)
    loaded: Payload = json.loads(build_payload(run.document, evaluation(run.result)))
    return loaded


def _table(payload: Payload, name: str) -> dict[str, list[int]]:
    table = payload[name]
    assert isinstance(table, dict)
    return table


def _strings(payload: Payload) -> list[str]:
    strings = payload["strings"]
    assert isinstance(strings, list)
    return strings


def _flat(payload: Payload, name: str, ends: Sequence[int], row: int) -> list[str]:
    values = payload[name]
    assert isinstance(values, list)
    start = ends[row - 1] if row else 0
    return [_strings(payload)[i] for i in values[start : ends[row]]]


@pytest.mark.parametrize("case", CASES)
def test_violation_rows_equal_the_violations_of_the_report(case: str, workdir: str) -> None:
    run = run_case(case, workdir)
    payload = _payload(case, workdir)
    rows = _table(payload, "violations")
    strings, nodes = _strings(payload), _table(payload, "nodes")

    def text(index: int) -> str | None:
        return strings[index] if index >= 0 else None

    def component(index: int) -> str | None:
        return strings[nodes["name"][index]] if index >= 0 else None

    actual = sorted(
        (
            tuple(_flat(payload, "violation_rules", rows["rules_end"], i)),
            tuple(_flat(payload, "violation_subjects", rows["subjects_end"], i)),
            text(rows["source_module"][i]),
            text(rows["target_module"][i]),
            text(rows["symbol"][i]),
            component(rows["source_component"][i]),
            component(rows["target_component"][i]),
            tuple(_flat(payload, "violation_evidence", rows["evidence_end"], i)),
        )
        for i in range(len(rows["kind"]))
    )
    expected = sorted(
        (
            tuple(item.fingerprint.rules),
            tuple(item.fingerprint.subjects),
            item.source_module,
            item.target_module,
            item.symbol,
            item.source_component,
            item.target_component,
            tuple(item.evidence_ids),
        )
        for item in load_violations(run.path)
    )
    assert actual == expected


@pytest.mark.parametrize("case", CASES)
def test_every_unknown_record_and_diagnostic_has_a_row(case: str, workdir: str) -> None:
    run = run_case(case, workdir)
    payload = _payload(case, workdir)
    rows = _table(payload, "unknowns")
    sources = Counter(UNKNOWN_SOURCE[code] for code in rows["source"])
    document = run.document
    records = document["unknowns"]
    assert isinstance(records, list)
    diagnostics = run.result["diagnostics"]
    assert isinstance(diagnostics, list)

    assert sources["record"] == len(records)
    assert sources["diagnostic"] == len(diagnostics)
    assert sources["run"] == (0 if run.result.get("target") != "unavailable" else 1)
    assert "other" not in {UNKNOWN_REASON[code] for code in rows["reason"]}


@pytest.mark.parametrize("case", CASES)
def test_the_status_follows_the_stated_rule_and_each_non_pass_status_has_a_row(
    case: str, workdir: str
) -> None:
    payload = _payload(case, workdir)
    summary = payload["summary"]
    assert isinstance(summary, dict)
    rules = payload["rules"]
    assert isinstance(rules, list)
    violations, unknowns = _table(payload, "violations"), _table(payload, "unknowns")

    assert recomputed_status(payload) == summary["status"]
    if summary["status"] == "FAIL":
        assert violations["kind"]
    if summary["status"] == "UNKNOWN":
        assert unknowns["source"] or any(r["verdict"] == "UNKNOWN" or r["undecided"] for r in rules)
    for rule in rules:
        cited = sum(
            rule["id"] in _flat(payload, "violation_rules", violations["rules_end"], i)
            for i in range(len(violations["kind"]))
        )
        assert cited == rule["violations"], rule["id"]


@pytest.mark.parametrize("case", CASES)
def test_permissions_and_level_counts_equal_report_only_architecture(
    case: str, workdir: str
) -> None:
    run = run_case(case, workdir)
    projection = json.loads(run.projection)["architecture_projection"]
    payload = _payload(case, workdir)
    strings, nodes = _strings(payload), _table(payload, "nodes")
    permissions, edges = _table(payload, "permissions"), _table(payload, "edges")

    def ident(node: int) -> str:
        return strings[nodes["key"][node]].removeprefix("component:")

    actual = {
        (ident(a), ident(b), PERMISSION[s])
        for a, b, s in zip(
            permissions["component"], permissions["target"], permissions["status"], strict=True
        )
    }
    listed = [c for c in projection["components"] if "permissions" in c]
    expected = {
        (c["id"], target, p["status"])
        for c in listed
        for p in c["permissions"]
        for target in p["target_ids"]
    }
    assert {row for row in actual if row[0] in {c["id"] for c in listed}} == expected
    for level in projection["levels"]:
        ids = set(level["component_ids"])
        declared = {(a, b) for a, b, s in actual if a in ids and s == "allowed"}
        used = {
            (ident(f), ident(t))
            for lv, f, t, sites in zip(
                edges["level"], edges["from"], edges["to"], edges["sites"], strict=True
            )
            if lv == 2 and sites > 0 and ident(f) in ids
        }
        assert len(declared) == level["declared"], level["component_ids"]
        assert sum(1 for a, _, s in actual if a in ids and s == "undecided") == level["undecided"]
        if level["used"] is not None:
            assert (len(used), len(declared - used), len(used - declared)) == (
                level["used"],
                level["unused"],
                level["undeclared"],
            ), level["component_ids"]


@pytest.mark.parametrize("case", CASES)
def test_every_counted_cycle_has_a_finding_row(case: str, workdir: str) -> None:
    run = run_case(case, workdir)
    payload = _payload(case, workdir)
    findings = _table(payload, "findings")
    cycles = run.document["cycles"]
    assert isinstance(cycles, list)
    summary = payload["summary"]
    assert isinstance(summary, dict)
    rows = [
        d
        for k, d in zip(findings["kind"], findings["disposition"], strict=True)
        if FINDING_KIND[k] == "cycle"
    ]

    assert len(rows) == len(cycles)
    assert rows.count(0) == summary["counts"]["cycles"]


@pytest.mark.parametrize("case", CASES)
def test_the_system_node_names_each_gap_that_blocks_a_measure(case: str, workdir: str) -> None:
    payload = _payload(case, workdir)
    measures = _table(payload, "measures")
    system = {
        MEASURE[d]: (s, GAP[g] if g >= 0 else None, v, b, verdict)
        for n, d, s, g, v, b, verdict in zip(
            measures["node"],
            measures["def"],
            measures["state"],
            measures["gap"],
            measures["value"],
            measures["budget"],
            measures["verdict"],
            strict=True,
        )
        if n == 0
    }

    nodes = _table(payload, "nodes")
    assert system["E.excluded"][:2] == (1, "G-EXCLUDED")
    if nodes["modules"][0]:
        assert system["R.size"][:2] == (1, "G-CODE-LINES")
    for name, (state, gap, value, budget, verdict) in system.items():
        if state == 0 and budget < 0:
            assert gap == "G-BUDGETS", name
        if budget >= 0:
            assert verdict == (1 if value >= budget else 2), name


@pytest.mark.parametrize(
    ("case", "language"),
    [
        ("fixtures/H-typescript/archkeel.toml", "typescript"),
        ("fixtures/G-dart/archkeel.toml", "dart"),
        ("fixtures/K-python-realworld/archkeel.toml", "python"),
    ],
)
def test_the_run_names_the_collected_language(case: str, language: str, workdir: str) -> None:
    run = _payload(case, workdir)["run"]
    assert isinstance(run, dict)

    assert run["language"] == language
