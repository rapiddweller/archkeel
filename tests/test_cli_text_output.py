# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The text of a run is for a person: header with exit code and reason, grouped causes, plain words.

UX issues #1317 (default output), #1318 (structure), #1319 (vocabulary), #1320 (exit table).
"""

import json
import re
from pathlib import Path

import pytest
from test_cli_core_only_boundary import HEAD, frame
from test_cli_report_output import project

from archkeel.cli import core_exit, core_only
from archkeel.cli.core_frame import GapKind, Status, UnknownKind


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "archkeel.toml").write_text('[scan]\ncontract = "contract.json"\n')
    (tmp_path / "contract.json").write_bytes(b"contract")
    monkeypatch.setattr(core_only, "identity", lambda _: (HEAD, False))
    monkeypatch.setattr(core_only, "locate_core", lambda: Path("core"))


def _run(document: dict, argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    """Run one command line against a planted frame; the core exits 3 when the frame names parts."""
    names_parts = bool(document["gaps"] or document["unsupported"]["rules"])
    code = 3 if names_parts else 0
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "exchange", lambda *_: (json.dumps(document).encode(), code))
        done = core_only.run(argv)
    return done, capsys.readouterr().out


def _baseline(state: str, exit_code: int, unknowns: int = 0, new: int = 0) -> dict:
    row = {"what": "violation", "kind": "k", "subject": "s", "reason": "r", "run": 1, "file": 0}
    return {
        "state": state,
        "exit_code": exit_code,
        "accepted_entries": unknowns,
        "accepted_unknowns": unknowns,
        "new": [row] * new,
        "gone": [],
        "gaps": [],
        "accepted_rules": [],
    }


def _matrix() -> list[tuple[str, dict, list[str], int, str]]:
    """(name, frame, argv, exit code, text that the reason must contain)."""
    cases = []
    for status, code, reason in (
        (Status.PASS, 0, "all 1 rules pass"),
        (Status.FAIL, 1, "1 violations in 1 rules"),
        (Status.UNKNOWN, 2, "1 of 1 rules cannot be decided"),
    ):
        cases.append((f"plain-{status}", json.loads(frame(status)), ["validate"], code, reason))
    accepted = json.loads(frame(Status.UNKNOWN))
    accepted["baseline"] = _baseline("current", 2, unknowns=52)
    cases.append(
        (
            "accepted-unknown",
            accepted,
            ["validate", "--baseline", "b.json"],
            2,
            "52 accepted items stay UNKNOWN",
        )
    )
    debt = json.loads(frame(Status.FAIL))
    debt["baseline"] = _baseline("current", 0)
    cases.append(
        (
            "accepted-violation",
            debt,
            ["validate", "--baseline", "b.json"],
            0,
            "1 violations are accepted by the baseline",
        )
    )
    drift = json.loads(frame(Status.PASS))
    drift["baseline"] = _baseline("drift", 1, new=2)
    cases.append(
        (
            "drift",
            drift,
            ["validate", "--baseline", "b.json"],
            1,
            "the run differs from the baseline: 2 new",
        )
    )
    return cases


NAMES = [
    "plain-PASS",
    "plain-FAIL",
    "plain-UNKNOWN",
    "accepted-unknown",
    "accepted-violation",
    "drift",
]


@pytest.mark.parametrize("name", NAMES)
def test_the_header_word_is_the_meaning_of_the_exit_code(
    name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """#1320: one exit table. The printed word, the code and the process exit agree."""
    _, document, argv, expected, reason = next(case for case in _matrix() if case[0] == name)
    done, text = _run(document, [*argv, "--text"], capsys)
    first = text.splitlines()[0]
    match = re.fullmatch(r"validate: (PASS|FAIL|UNKNOWN) -> exit (\d) \((.+)\)", first)
    assert match, text
    assert done == expected == int(match[2])
    assert match[1] == core_exit.word_of(expected) == core_exit.EXIT_TABLE[expected][0]
    assert reason in match[3]


def test_a_refused_scan_has_the_same_documented_exit_with_and_without_a_baseline(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#1320: a scan that did not run exits 2; with a baseline it exits 1, and the help says so."""
    document = json.loads(frame(Status.UNKNOWN))
    _refuse(document, "config: gone")
    plain, text = _run(document, ["validate", "--text"], capsys)
    based, text_with = _run(document, ["validate", "--text", "--baseline", "b.json"], capsys)
    assert (plain, based) == (2, 1)
    assert text.splitlines()[0] == "validate: REFUSED -> exit 2"
    assert text_with.splitlines()[0] == "validate: REFUSED -> exit 1"
    assert "with --baseline and 2 without" in core_only.help_for(core_only.Command.VALIDATE)


def _refuse(document: dict, reason: str) -> None:
    """Make the frame the one of a scan that did not run (`scan::refused`)."""
    document.update(rules={}, explained={}, violations={}, details={}, unknown_kinds={})
    document["gaps"] = [{"kind": "collect", "subject": "the whole contract", "reason": reason}]
    document["unsupported"]["rules"] = reason
    document["self_test"]["collect"] = {"refused": reason}


def _many_gaps(count: int = 78) -> dict:
    document = json.loads(frame(Status.UNKNOWN))
    places = {f"E{n}": {"path": f"src/m{n}.py", "line": n} for n in range(1, count + 1)}
    document["locations"].update(places)
    document["collection_gaps"] = [
        {
            "kind": "source_resolution_gap" if n % 4 else "import_system_change",
            "subjects": [f"app.m{n}"],
            "reason": "A name cannot be resolved by the scan",
            "evidence": [f"E{n}"],
        }
        for n in range(1, count + 1)
    ]
    document["scope"] = f"incomplete scope: the collector reports {count} coverage gaps"
    return document


def test_a_project_with_78_gaps_fits_two_screens_and_names_the_top_cause_first(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#1318: the verdict, the top cause and the next action come first; gaps are grouped."""
    _, text = _run(_many_gaps(), ["validate", "--text"], capsys)
    lines = text.splitlines()
    assert len(lines) <= 40, text
    assert lines[0].startswith("validate: UNKNOWN -> exit 2 (")
    assert lines[1].startswith("Next: Resolve the largest cause first: a name or import")
    assert "59 x a name or import that the scan cannot resolve" in text
    assert "and 56 more (--all lists them)" in text
    assert text.count("Next:") == 1 and "Action:" not in text


def test_all_lists_every_item(capsys: pytest.CaptureFixture[str]) -> None:
    _, text = _run(_many_gaps(), ["validate", "--text", "--all"], capsys)
    assert "src/m78.py:78" in text and "more (--all" not in text


def test_an_error_of_the_command_comes_before_the_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#1318: a file that could not be written is the second line, not the last."""
    document = json.loads(frame(Status.UNKNOWN))
    _, text = _run(document, ["report", "--text", "--output", "missing/dir/r.html"], capsys)
    assert text.splitlines()[1].startswith("Problem: ")


def test_no_internal_word_reaches_the_text(capsys: pytest.CaptureFixture[str]) -> None:
    """#1319: machine codes, issue numbers and decision numbers stay in the JSON."""
    document = _many_gaps(8)
    document["gaps"] = [
        {"kind": "rule_kind_not_ported", "subject": "R2", "reason": "rule kind X (#880) AD-522"}
    ]
    document["unsupported"]["rules"] = {"R2": "rule kind X (#880) AD-522"}
    document["unknown_kinds"] = {"R1": "scope_incomplete"}
    _, text = _run(document, ["validate", "--text", "--all"], capsys)
    machine = [str(kind) for kind in (*UnknownKind, *GapKind) if "_" in kind or "." in kind]
    machine += ["import_system_change", "source_resolution_gap", "collect: unsupported"]
    for word in machine:
        assert word not in text, word
    assert not re.search(r"#\d+|AD-\d+|Core:|archkeel-core|contract hygiene", text)
    machine_json = json.loads(_run(document, ["validate", "--json"], capsys)[1])
    assert "rule_kind_not_ported" in json.dumps(machine_json)


def test_the_core_binary_is_named_only_with_verbose(capsys: pytest.CaptureFixture[str]) -> None:
    _, plain = _run(json.loads(frame()), ["validate", "--text"], capsys)
    _, loud = _run(json.loads(frame()), ["validate", "--text", "--verbose"], capsys)
    assert "Core:" not in plain and "Core: core;" in loud and "code digest:" in loud


def test_a_path_is_shown_as_typed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """#1319: the resolved `/private/...` path of the root does not replace what was typed."""
    real = tmp_path.resolve()
    document = json.loads(frame(Status.UNKNOWN))
    _refuse(document, f"cannot read {real}/x")
    _, text = _run(document, ["validate", "--text", "--root", "."], capsys)
    assert str(real) not in text and "cannot read ./x" in text


def test_report_output_prints_one_line_and_json_stays_available(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#1317: with --output the default is one line; --json prints the object; --text, the text."""
    root = project(tmp_path / "p", release_core, "rust", "PASS")
    monkeypatch.undo()
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    target = tmp_path / "report.html"
    base = ["report", "--root", str(root), "--output", str(target)]
    code = core_only.run(base)
    out = capsys.readouterr().out
    assert code == 0 and out.count("\n") == 1 and target.read_bytes()
    assert out.startswith("report: PASS -> exit 0 (") and f"report written to {target}" in out
    assert core_only.run([*base, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["frame"]
    assert core_only.run([*base, "--text"]) == 0
    assert f"Report written to {target}" in capsys.readouterr().out


def test_a_reason_of_the_core_is_put_in_plain_words() -> None:
    from archkeel.cli.core_words import plain

    reason = "contract hygiene boundary_type_position: c.json/rules/39 a.b: unresolved_name: Order"
    assert plain(reason) == "c.json/rules/39 a.b: name not resolved: Order"
    assert plain("collect: unsupported: config: cannot read x (#880) AD-522") == (
        "config: cannot read x"
    )
