# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The semantic checker and the canonical form of the report v2 payload (AD-361)."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable

import pytest
from report_payload_support import run_case

from archkeel.report.payload import build_payload, evaluation
from archkeel.report.payload.canonical import encode
from archkeel.report.payload.checker import PayloadInvalid, check_payload
from archkeel.report.payload.graph import decl_text

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
