# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The semantic checker and the canonical form of the report v2 payload (AD-361)."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from report_payload_support import run_case

from archkeel.report.payload import build_payload, evaluation
from archkeel.report.payload.canonical import encode
from archkeel.report.payload.checker import PayloadInvalid, check_payload
from archkeel.report.payload.graph import decl_text

TESTDATA = Path(__file__).resolve().parents[1] / "native" / "report" / "testdata"

Payload = dict[str, object]
CASE = "fixtures/K-python-realworld/archkeel.toml"


@pytest.fixture(scope="session")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> str:
    return str(tmp_path_factory.mktemp("report-checker"))


@pytest.fixture
def payload(workdir: str) -> Payload:
    run = run_case(CASE, workdir)
    loaded: Payload = json.loads(build_payload(run.document, evaluation(run.result)))
    return loaded


def _swap_strings(p: Payload) -> None:
    strings = p["strings"]
    assert isinstance(strings, list)
    strings[1], strings[2] = strings[2], strings[1]


def _parent_loop(p: Payload) -> None:
    nodes = p["nodes"]
    assert isinstance(nodes, dict)
    nodes["parent"][1] = len(nodes["parent"]) - 1


def _pass_with_unknown_rule(p: Payload) -> None:
    summary = p["summary"]
    assert isinstance(summary, dict)
    summary["status"] = "PASS"


def _duplicate_gap(p: Payload) -> None:
    gaps = p["gaps"]
    assert isinstance(gaps, list)
    gaps.append(dict(gaps[0]))


def _dangling_unit(p: Payload) -> None:
    crossings = p["crossings"]
    assert isinstance(crossings, dict)
    units = p["units"]
    assert isinstance(units, dict)
    crossings["unit"][0] = len(units["module"])


def _flip_verdict(p: Payload) -> None:
    measures = p["measures"]
    assert isinstance(measures, dict)
    row = next(i for i, b in enumerate(measures["budget"]) if b >= 0)
    measures["verdict"][row] = 3 - measures["verdict"][row]


def _short_column(p: Payload) -> None:
    edges = p["edges"]
    assert isinstance(edges, dict)
    edges["names"].pop()


def _wrong_cycle_count(p: Payload) -> None:
    summary = p["summary"]
    assert isinstance(summary, dict)
    summary["counts"]["cycles"] += 1


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        (_swap_strings, "strings"),
        (_parent_loop, "parent"),
        (_pass_with_unknown_rule, "status"),
        (_duplicate_gap, "gaps"),
        (_dangling_unit, "crossings.unit"),
        (_flip_verdict, "verdict"),
        (_short_column, "edges"),
        (_wrong_cycle_count, "cycles"),
    ],
)
def test_the_checker_rejects_hostile_payloads(
    payload: Payload, fault: Callable[[Payload], None], message: str
) -> None:
    check_payload(payload)
    broken = copy.deepcopy(payload)
    fault(broken)

    with pytest.raises(PayloadInvalid, match=message):
        check_payload(broken)


def test_canonical_strings_escape_only_what_json_requires() -> None:
    text = 'line\nnext\ttab "q" \\ \x01 \x7f é 😀 /'

    data = encode({"s": text})

    assert data == '{"s":"line\\nnext\\ttab \\"q\\" \\\\ \\u0001 \x7f é 😀 /"}\n'.encode()


def test_decl_is_cut_at_72_code_points_without_normalisation() -> None:
    line = "\t  " + "😀" * 80 + "é"

    cut = decl_text(line)

    assert cut == "😀" * 72
    assert decl_text("  café  ") == "café"


def _testdata(name: str) -> Payload:
    loaded: Payload = json.loads((TESTDATA / f"{name}.report-v2.json").read_bytes())
    return loaded


@pytest.mark.parametrize("name", ["H-uml-dart", "G-dart"])
@pytest.mark.parametrize("relation", [0, 1, 2])
def test_a_pass_without_a_part_that_it_needs_is_refused(name: str, relation: int) -> None:
    p = _testdata(name)
    run = p["run"]
    assert isinstance(run, dict) and run["observation"] == "PASS"
    run["not_carried"] = sorted([relation, *run["not_carried"]])
    with pytest.raises(PayloadInvalid, match="does not carry imports"):
        check_payload(p)


def test_a_fail_rule_without_a_violation_row_is_refused() -> None:
    p = _testdata("python-newer-syntax-demo")
    rules = p["rules"]
    assert isinstance(rules, list)
    rule = next(r for r in rules if r["verdict"] == "PASS")
    rule.update(verdict="FAIL", reason="violations")
    counts = p["summary"]["counts"]  # type: ignore[index]
    counts["rules_pass"] -= 1
    counts["rules_fail"] += 1
    with pytest.raises(PayloadInvalid, match="is FAIL and no violation row cites it"):
        check_payload(p)


def test_a_reason_that_the_verdict_cannot_have_is_refused() -> None:
    p = _testdata("H-uml-dart")
    rules = p["rules"]
    assert isinstance(rules, list)
    rules[0]["reason"] = "no_receipt"
    with pytest.raises(PayloadInvalid, match="reason that its verdict cannot have"):
        check_payload(p)
