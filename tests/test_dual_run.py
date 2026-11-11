# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-360: the dual run finds a planted difference and names its section, its id and its row."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

from tools import dual_run, dual_run_oracle
from tools.dual_run_oracle import Selection

CASE = "fixture/F-architecture"
REPOSITORY = Path(__file__).resolve().parent.parent


def _case(case_id: str) -> dual_run.Case:
    return next(case for case in dual_run.corpus_cases() if case.id == case_id)


@pytest.fixture(scope="module")
def run() -> tuple[dict[str, Any], dict[str, Any]]:
    """The committed oracle and a fresh Python frame, with the sections decoded."""
    case = _case(CASE)
    with dual_run.materialized(case) as root:
        frame = dual_run.run_engine(case, root, None, Selection())
    sections = dual_run_oracle.decode_sections(frame["architecture"])
    return dual_run_oracle.read_oracle(dual_run.oracle_path(case)), {
        "rules": frame["rules"],
        "sections": sections,
    }


def _planted(run: tuple[dict[str, Any], dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    return run[0], copy.deepcopy(run[1])


def test_the_python_engine_equals_its_oracle(run: tuple[dict[str, Any], dict[str, Any]]) -> None:
    oracle, frame = run
    assert dual_run_oracle.compare_case(oracle, frame, Selection()) == []


def test_a_changed_verdict_names_the_rule(run: tuple[dict[str, Any], dict[str, Any]]) -> None:
    oracle, frame = _planted(run)
    rule = sorted(frame["rules"])[0]
    frame["rules"][rule] = [frame["rules"][rule][0], "FAIL"]
    [difference] = dual_run_oracle.compare_case(oracle, frame, Selection())
    assert (difference.case, difference.scope, difference.id) == (CASE, "rules", rule)
    assert "FAIL" in difference.detail


def test_a_dropped_row_names_the_section_and_the_id(
    run: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    oracle, frame = _planted(run)
    dropped = frame["sections"]["evidence"].pop(7)
    [difference] = dual_run_oracle.compare_case(oracle, frame, Selection())
    assert (difference.scope, difference.id) == ("evidence", dropped["id"])
    assert difference.detail.startswith("row 7: the candidate drops this row")


def test_a_reordered_row_is_a_difference(run: tuple[dict[str, Any], dict[str, Any]]) -> None:
    oracle, frame = _planted(run)
    rows = frame["sections"]["declarations"]
    rows[2], rows[3] = rows[3], rows[2]
    [difference] = dual_run_oracle.compare_case(oracle, frame, Selection())
    assert (difference.scope, difference.id) == ("declarations", rows[2]["id"])
    assert "row 2: the order differs" in difference.detail


def test_a_changed_field_of_a_full_row_names_the_field(
    run: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    oracle, frame = _planted(run)
    assert "rows" in oracle["sections"]["packages"]
    frame["sections"]["packages"][1]["title"] = "planted"
    [difference] = dual_run_oracle.compare_case(oracle, frame, Selection())
    assert difference.scope == "packages"
    assert difference.detail.startswith("row 1: field title: expected")


def test_an_added_last_row_is_a_difference(run: tuple[dict[str, Any], dict[str, Any]]) -> None:
    oracle, frame = _planted(run)
    frame["sections"]["cycles"].append({"id": "CYCLE-PLANTED", "rule_ids": []})
    [difference] = dual_run_oracle.compare_case(oracle, frame, Selection())
    assert (difference.scope, difference.id) == ("cycles", "CYCLE-PLANTED")


def test_a_slice_compares_only_what_it_owns(run: tuple[dict[str, Any], dict[str, Any]]) -> None:
    oracle, frame = _planted(run)
    frame["sections"]["modules"].pop(0)
    rule, (kind, _) = next(iter(sorted(frame["rules"].items())))
    frame["rules"][rule] = [kind, "FAIL"]
    other = dual_run_oracle.selection_of("imports", "no_component_cycles")
    assert kind != "no_component_cycles"
    assert dual_run_oracle.compare_case(oracle, frame, other) == []
    owned = dual_run_oracle.selection_of("modules", kind)
    assert [d.scope for d in dual_run_oracle.compare_case(oracle, frame, owned)] == [
        "rules",
        "modules",
    ]


def test_a_family_owns_the_rule_rows_of_its_rules() -> None:
    def row(row_id: str, rule: str) -> dict[str, Any]:
        return {"id": row_id, "rule_ids": [rule]}

    oracle = {
        "case": {"id": "c"},
        "rules": {"A": ["forbidden_dependency", "FAIL"], "B": ["interface_boundary", "FAIL"]},
        "sections": {
            "violations": dual_run_oracle.oracle_section(
                "violations", [row("V1", "A"), row("V2", "B")]
            )
        },
    }
    frame = {"rules": oracle["rules"], "sections": {"violations": [row("V1", "A")]}}
    direction = dual_run_oracle.selection_of("violations", "direction")
    assert dual_run_oracle.compare_case(oracle, frame, direction) == []
    [difference] = dual_run_oracle.compare_case(
        oracle, frame, dual_run_oracle.selection_of("violations", None)
    )
    assert (difference.id, difference.detail) == ("V2", "row 1: the candidate drops this row")


def test_a_delta_oracle_reads_back_its_rows() -> None:
    rows = [{"id": f"R{index}", "n": index} for index in range(300)]
    base_entry = dual_run_oracle.oracle_section("modules", rows)
    base = dual_run_oracle.oracle_rows(base_entry)
    changed = [*rows[:100], {"id": "NEW"}, *rows[101:]]
    delta = dual_run_oracle.oracle_section("modules", changed, ("b", base_entry["digest"], base))
    assert len(delta["rows"]) == 3
    assert dual_run_oracle.oracle_rows(delta, base) == dual_run_oracle.oracle_rows(
        dual_run_oracle.oracle_section("modules", changed)
    )


def test_each_corpus_case_has_one_oracle() -> None:
    expected = {dual_run.oracle_path(case).name for case in dual_run.corpus_cases()}
    assert {path.name for path in dual_run_oracle.ORACLE_DIR.glob("*.json.gz")} == expected


def test_a_command_engine_with_a_planted_difference_fails_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command interface: `serve-python` is the reference engine; the wrapper plants."""
    script = tmp_path / "planted.py"
    script.write_text(
        "import json, subprocess, sys\n"
        "request = sys.stdin.read()\n"
        "done = subprocess.run([sys.executable, '-m', 'tools.dual_run', 'serve-python'],"
        f" input=request, capture_output=True, text=True, check=True, cwd={str(REPOSITORY)!r})\n"
        "frame = json.loads(done.stdout)\n"
        "rule = sorted(frame['rules'])[0]\n"
        "frame['rules'][rule][1] = 'FAIL'\n"
        "json.dump(frame, sys.stdout)\n"
    )
    command = f"{sys.executable} {script}"
    arguments = ["compare", "--case", "fixture/H-uml", "--jobs", "1"]
    assert dual_run.main(arguments) == 0
    assert dual_run.main([*arguments, "--engine-command", command]) == 1
    output = capsys.readouterr().out
    assert "fixture/H-uml: rules: " in output
    assert "1 differences" in output
