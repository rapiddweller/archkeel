# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""`validate --baseline` and `--write-baseline` through the real core (AD-546).

Each test plants one difference between a run and its baseline file and states the exit code.
UNKNOWN is never exit 0, a difference is exit 1, and a damaged file is exit 1 and never exit 2:
CE treats exit 2 as green.
"""

import json
import os
from pathlib import Path

import pytest
from core_support import HONEST, SUFFIX, case_root
from test_cli_core_only_scan import command

BROKEN = "export type T = ;\n"


def run(built: Path, root: Path, *flags: str) -> tuple[int, dict[str, object]]:
    done = command(built / f"archkeel-core{SUFFIX}", root, "--json", *flags)
    assert "Traceback" not in done.stderr, done.stderr
    return done.returncode, json.loads(done.stdout)


def baseline(result: dict[str, object]) -> dict[str, object]:
    part = result["baseline"]
    assert isinstance(part, dict)
    return part


def entries(path: Path) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))["unknowns"]


def test_a_pass_run_writes_an_empty_list_and_validates_with_exit_0(built: Path) -> None:
    with case_root(HONEST) as root:
        code, _ = run(built, root, "--write-baseline", "b.json")
        assert code == 0
        document = json.loads((root / "b.json").read_text(encoding="utf-8"))
        assert document["schema_version"] == "1.4.0"
        assert document["unknowns"] == [] and document["violations"] == []
        code, result = run(built, root, "--baseline", "b.json")
    assert code == 0 and result["status"] == "PASS"
    assert baseline(result)["state"] == "current"


def test_every_unknown_accepted_keeps_status_unknown_and_exit_2(built: Path) -> None:
    with case_root(HONEST) as root:
        (root / "src/b/t.ts").write_text(BROKEN)
        code, _ = run(built, root, "--write-baseline", "b.json")
        assert code == 2 and entries(root / "b.json")
        code, result = run(built, root, "--baseline", "b.json")
        text = command(built / f"archkeel-core{SUFFIX}", root, "--text", "--baseline", "b.json")
    assert code == 2 and result["status"] == "UNKNOWN"
    part = baseline(result)
    assert part["state"] == "current" and part["new"] == [] and part["gone"] == []
    assert part["accepted_unknowns"] >= 1
    assert 1 <= part["accepted_entries"] <= part["accepted_unknowns"]  # type: ignore[operator]
    assert part["accepted_rules"], "each UNKNOWN row of this run is accepted"
    assert text.returncode == 2
    assert "entries" in text.stdout and "stays UNKNOWN" in text.stdout
    assert "PASS" not in text.stdout.splitlines()[0]


def test_two_writes_of_one_run_are_byte_equal(built: Path) -> None:
    with case_root(HONEST) as root:
        (root / "src/b/t.ts").write_text(BROKEN)
        run(built, root, "--write-baseline", "one.json")
        run(built, root, "--write-baseline", "two.json")
        assert (root / "one.json").read_bytes() == (root / "two.json").read_bytes()


def test_a_blank_line_above_the_broken_construct_keeps_the_accepted_entry(built: Path) -> None:
    with case_root(HONEST) as root:
        (root / "src/b/t.ts").write_text(BROKEN)
        run(built, root, "--write-baseline", "b.json")
        (root / "src/b/t.ts").write_text("\n\n\n" + BROKEN)
        code, result = run(built, root, "--baseline", "b.json")
    assert code == 2, result
    assert baseline(result)["state"] == "current"


def test_a_new_gap_that_is_not_accepted_is_red_and_names_it(built: Path) -> None:
    with case_root(HONEST) as root:
        run(built, root, "--write-baseline", "b.json")
        (root / "src/b/t.ts").write_text(BROKEN)
        code, result = run(built, root, "--baseline", "b.json")
    assert code == 1, result
    part = baseline(result)
    assert part["state"] == "drift" and part["gone"] == []
    assert any("src/b/t.ts" in json.dumps(row) for row in part["new"])  # type: ignore[union-attr]


def test_an_accepted_gap_that_vanished_is_stale_and_red(built: Path) -> None:
    with case_root(HONEST) as root:
        original = (root / "src/b/t.ts").read_text(encoding="utf-8")
        (root / "src/b/t.ts").write_text(BROKEN)
        run(built, root, "--write-baseline", "b.json")
        (root / "src/b/t.ts").write_text(original)
        code, result = run(built, root, "--baseline", "b.json")
    assert code == 1, result
    part = baseline(result)
    assert part["state"] == "drift" and part["new"] == [] and part["gone"]


def test_a_fail_with_an_accepted_unknown_exits_1(built: Path) -> None:
    with case_root(HONEST) as root:
        (root / "src/b/c.ts").write_text(BROKEN)
        run(built, root, "--write-baseline", "b.json")
        (root / "src/a/a.ts").write_text(
            'import type { T } from "../b/t";\nexport const a: T = 1;\n'
        )
        code, result = run(built, root, "--baseline", "b.json")
    assert code == 1, result
    assert result["status"] in {"FAIL", "UNKNOWN"}
    assert any(row["what"] == "violation" for row in baseline(result)["new"])  # type: ignore[union-attr]


def test_an_accepted_violation_is_known_debt_and_a_removed_one_is_stale(built: Path) -> None:
    with case_root(HONEST) as root:
        original = (root / "src/a/a.ts").read_text(encoding="utf-8")
        (root / "src/a/a.ts").write_text(
            'import type { T } from "../b/t";\nexport const a: T = 1;\n'
        )
        code, _ = run(built, root, "--write-baseline", "b.json")
        document = json.loads((root / "b.json").read_text(encoding="utf-8"))
        assert document["violations"], "the violation is written as known debt"
        # The new import also leaves the marked graph stale: an UNKNOWN that the file accepts.
        assert code == 2 and document["unknowns"]
        code, result = run(built, root, "--baseline", "b.json")
        assert code == 2 and result["status"] == "FAIL", result
        assert baseline(result)["state"] == "current"
        (root / "src/a/a.ts").write_text(original)
        code, result = run(built, root, "--baseline", "b.json")
    assert code == 1
    assert any(row["what"] == "violation" for row in baseline(result)["gone"])  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "text",
    [
        "{",
        '{"schema_version": "1.4.0", "violations": [], "budgets": {}}',
        '{"schema_version": "1.4.0", "violations": [], "budgets": {}, "unknowns": '
        '[{"kind": "b", "subject": "s", "reason": "r"}, {"kind": "a", "subject": "s", '
        '"reason": "r"}]}',
        '{"schema_version": "1.4.0", "violations": [], "budgets": {}, "unknowns": '
        '[{"kind": "a", "subject": "s", "reason": "r", "count": 0}]}',
        '{"schema_version": "1.4.0", "violations": [], "budgets": {}, "unknowns": '
        '[{"kind": "a", "subject": "s", "reason": "r", "line": 3}]}',
        '{"schema_version": "9.9.9", "violations": [], "budgets": {}, "unknowns": []}',
    ],
)
def test_a_damaged_baseline_exits_1_and_never_accepts_nothing_silently(
    built: Path, text: str
) -> None:
    with case_root(HONEST) as root:
        (root / "b.json").write_text(text, encoding="utf-8")
        code, result = run(built, root, "--baseline", "b.json")
    assert code == 1, result
    part = baseline(result)
    assert part["state"] == "invalid" and part["gaps"]


def test_a_missing_baseline_is_red(built: Path) -> None:
    with case_root(HONEST) as root:
        code, result = run(built, root, "--baseline", "absent.json")
    assert code == 1 and baseline(result)["state"] == "invalid"


def test_a_file_of_schema_1_3_0_accepts_no_unknown_and_names_the_old_budgets(built: Path) -> None:
    older = {
        "schema_version": "1.3.0",
        "violations": [],
        "budgets": {"calls_unresolved": 1429, "cycle_edges": 0, "typing_positions": 178},
    }
    with case_root(HONEST) as root:
        (root / "b.json").write_text(json.dumps(older), encoding="utf-8")
        code, result = run(built, root, "--baseline", "b.json")
    assert code == 2, result
    part = baseline(result)
    kinds = {gap["kind"] for gap in part["gaps"]}  # type: ignore[union-attr]
    assert kinds == {"baseline.budget_of_older_schema", "baseline.older_schema"}
    assert part["new"] == [] and part["gone"] == []


def test_a_budget_above_the_file_is_red(built: Path) -> None:
    with case_root(HONEST) as root:
        code, result = run(built, root, "--write-baseline", "b.json")
        assert code == 0
        document = json.loads((root / "b.json").read_text(encoding="utf-8"))
        assert document["budgets"] == {"cycle_edges": 0, "private_crossings": 0}
        document["budgets"]["cycle_edges"] = 5
        (root / "b.json").write_text(json.dumps(document), encoding="utf-8")
        code, result = run(built, root, "--baseline", "b.json")
    assert code == 1, result
    assert baseline(result)["gone"][0]["subject"] == "cycle_edges"  # type: ignore[index]


def test_a_budget_that_the_core_does_not_measure_is_a_named_gap_and_never_held(
    built: Path,
) -> None:
    with case_root(HONEST) as root:
        _, _ = run(built, root, "--write-baseline", "b.json")
        document = json.loads((root / "b.json").read_text(encoding="utf-8"))
        document["budgets"]["calls_unresolved"] = 0
        (root / "b.json").write_text(json.dumps(document), encoding="utf-8")
        code, result = run(built, root, "--baseline", "b.json")
    assert code == 2, result
    assert {gap["kind"] for gap in baseline(result)["gaps"]} == {"budget.unmeasured"}  # type: ignore[union-attr]


def test_the_same_path_for_both_options_is_refused_before_any_scan(built: Path) -> None:
    with case_root(HONEST) as root:
        done = command(
            built / f"archkeel-core{SUFFIX}",
            root,
            "--json",
            "--baseline",
            "b.json",
            "--write-baseline",
            "b.json",
        )
        assert not (root / "b.json").exists()
    assert done.returncode == 2
    assert "same file" in json.loads(done.stdout)["refusal"]["message"]


@pytest.mark.parametrize("path", [os.sep + "b.json", "../b.json", "a/../../b.json", ""])
def test_a_path_outside_the_root_is_refused(built: Path, path: str) -> None:
    with case_root(HONEST) as root:
        for flag in ("--baseline", "--write-baseline"):
            done = command(built / f"archkeel-core{SUFFIX}", root, "--json", flag, path)
            assert done.returncode == 2, done.stdout
            assert json.loads(done.stdout)["refusal"]["kind"] == "invalid_input"


def test_a_run_with_a_refused_part_writes_no_baseline(built: Path) -> None:
    with case_root(HONEST) as root:
        (root / "architecture-contract.json").write_text("{", encoding="utf-8")
        code, result = run(built, root, "--write-baseline", "b.json")
        assert not (root / "b.json").exists()
        assert code == 2, result
        assert "no baseline file was written" in json.dumps(result)


def test_a_collection_that_the_core_refuses_writes_no_baseline(built: Path) -> None:
    with case_root(HONEST) as root:
        (root / "architecture-contract.json").unlink()
        code, result = run(built, root, "--write-baseline", "b.json")
        assert not (root / "b.json").exists()
    assert code == 2 and "baseline" not in result


def test_a_refused_scan_with_a_baseline_exits_1_because_exit_2_means_all_accepted(
    built: Path,
) -> None:
    with case_root(HONEST) as root:
        run(built, root, "--write-baseline", "b.json")
        (root / "architecture-contract.json").unlink()
        code, result = run(built, root, "--baseline", "b.json")
    assert code == 1, result
    assert result["refusal"]["kind"] == "collection_refused"  # type: ignore[index]


def test_a_baseline_of_release_4_0_1_prints_one_migration_command_and_no_doubled_words(
    built: Path,
) -> None:
    older = {
        "schema_version": "1.2.0",
        "violations": [{"rules": ["R"], "subjects": ["backend"], "count": 1}],
        "budgets": {"calls_unresolved": 5, "cycle_edges": 0},
    }
    with case_root(HONEST) as root:
        (root / "old.json").write_text(json.dumps(older), encoding="utf-8")
        done = command(built / f"archkeel-core{SUFFIX}", root, "--text", "--baseline", "old.json")
    lines = [line for line in done.stdout.splitlines() if line.startswith("Baseline")]
    text = "\n".join(lines)
    assert "release 4.0.1" in text and "archkeel validate --write-baseline old.json" in text
    assert "amendment file" in text and "not compared" in text
    assert "violation: violation" not in text and ":  (" not in text
    # #1354: the migration hint is the first baseline line, and the stale entries are one count.
    assert lines[0].startswith("Baseline gap a baseline file from release 4.0.1")
    assert any(line.startswith("Baseline stale: 1 entries, not listed") for line in lines)
    assert "this run has 0, the file lists 1" not in text


def test_the_call_summary_shows_the_percentage_and_the_meaning() -> None:
    from archkeel.cli.core_evidence import call_lines

    counts = {
        "calls_total": 6399,
        "calls_resolved": 370,
        "calls_partial": 0,
        "calls_builtin": 100,
        "calls_external": 200,
        "calls_unresolved": 5729,
    }
    first, meaning = call_lines(counts)
    assert first.startswith("Calls: 370 of 6399 resolved (5.8%)")
    assert "stays UNKNOWN" in meaning
    assert call_lines(None) == [] and call_lines({**counts, "calls_total": 0})[0].count("n/a")


def test_an_invalid_baseline_is_a_refusal_that_the_first_line_names(built: Path) -> None:
    """#1348: a file that fits no schema supports no comparison; the line must not say
    `nothing differs`."""
    with case_root(HONEST) as root:
        (root / "bad.json").write_text('{"schema_version": "1.4.0", "violations": 3}')
        done = command(built / f"archkeel-core{SUFFIX}", root, "--text", "--baseline", "bad.json")
    lines = done.stdout.splitlines()
    assert done.returncode == 1
    assert lines[0].startswith("validate: REFUSED -> exit 1 (baseline bad.json is not valid: ")
    assert lines[1].startswith("Problem: baseline bad.json is not valid")
    assert lines[2].startswith("Fix: write the file again with --write-baseline FILE")
    assert "nothing differs" not in done.stdout and "Baseline: invalid" not in done.stdout
