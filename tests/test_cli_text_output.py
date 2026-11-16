# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The text of a run is for a person: header with exit code and reason, grouped causes, plain words.

UX issues #1317 (default output), #1318 (structure), #1319 (vocabulary), #1320 (exit table).
"""

import json
import re
import subprocess
from collections.abc import Callable
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
    assert lines[1].startswith(
        "Next: 1. 59 x a name or import that the scan cannot resolve; 2. 19 x"
    )
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


def _scan(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mutate: Callable[[Path], None],
) -> list[str]:
    root = project(tmp_path / "p", release_core, "rust", "PASS")
    mutate(root)
    monkeypatch.undo()
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    core_only.run(["validate", "--root", str(root), "--text"])
    return capsys.readouterr().out.splitlines()


def test_a_broken_contract_names_the_file_the_place_and_the_fix(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#1324: file, what the core read, what to write; the error is the second line."""
    lines = _scan(
        tmp_path,
        release_core,
        monkeypatch,
        capsys,
        lambda root: (root / "architecture-contract.json").write_text("{ broken"),
    )
    assert lines[1].startswith("Problem: architecture-contract.json: invalid JSON: ")
    assert lines[1].endswith("at line 1 column 3")
    assert lines[2].startswith("Fix: fix the JSON syntax at line 1, column 3")


def test_a_requires_entry_that_is_no_object_says_what_the_object_holds(
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def mutate(root: Path) -> None:
        path = root / "architecture-contract.json"
        contract = json.loads(path.read_text())
        contract["components"][0]["requires"] = ["X"]
        path.write_text(json.dumps(contract))

    lines = _scan(tmp_path, release_core, monkeypatch, capsys, mutate)
    assert lines[1].endswith("components[0].requires[0] must be an object")
    assert '{"component": "model", "rationale"' in lines[2]


@pytest.mark.parametrize(
    ("make", "expected"),
    [
        (lambda path: None, "the file does not exist in the current folder"),
        (lambda path: path.mkdir(), "is a folder, not a file"),
    ],
    ids=["missing", "folder"],
)
def test_a_configuration_error_says_missing_or_not_a_file(
    make: Callable[[Path], None],
    expected: str,
    tmp_path: Path,
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#1324: `cannot read archkeel.toml` is split into its causes, each with the way forward."""
    (tmp_path / "archkeel.toml").unlink()
    make(tmp_path / "archkeel.toml")
    (tmp_path / "README").write_text("x")
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "x"]):
        subprocess.run(
            ["git", "-c", "user.email=a@b", "-c", "user.name=n", *step], cwd=tmp_path, check=True
        )
    monkeypatch.undo()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    core_only.run(["validate", "--text"])
    text = capsys.readouterr().out
    assert text.splitlines()[0] == "validate: REFUSED -> exit 2"
    assert expected in text and "archkeel.toml" in text
    assert "archkeel init" in text or "--config" in text


def test_a_violation_that_has_a_usual_cause_names_the_fix_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#1351: `module has no unique owner` says what to add to the contract."""
    document = json.loads(frame(Status.FAIL))
    row = document["details"]["R1"][0]
    row["cause"], row["target"] = "module has no unique owner", None
    document["details"]["R1"].append(dict(row, source="backend.api"))
    document["violations"] = {"R1": 2}
    _, text = _run(document, ["validate", "--text"], capsys)
    assert text.count("Fix for 'module has no unique owner'") == 1
    assert "`packages` of one component" in text and "backend/__init__.py" in text


def test_the_next_step_names_at_most_three_jobs_with_counts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#1354: the jobs are in order, each with its count, and the rest is counted."""
    document = _many_gaps(40)
    for number, gap in enumerate(document["collection_gaps"]):
        gap["kind"] = ("a_gap", "b_gap", "c_gap", "d_gap")[number % 4] if number < 30 else "d_gap"
    _, text = _run(document, ["validate", "--text"], capsys)
    next_line = next(line for line in text.splitlines() if line.startswith("Next:"))
    assert next_line.startswith("Next: 1. 17 x d gap; 2. 8 x a gap; 3. 8 x b gap")
    assert "3. " in next_line and "4. " not in next_line and "(1 more below)" in next_line


def test_the_summary_is_text_in_a_pipe_and_has_at_most_fifteen_lines(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#1355: `--summary` is the CI path, also when stdout is no terminal."""
    document = json.loads(frame(Status.FAIL))
    row = document["details"]["R1"][0]
    document["details"]["R1"] = [dict(row, source=f"app.m{n}") for n in range(40)]
    document["violations"] = {"R1": 40}
    done, text = _run(document, ["validate", "--summary"], capsys)
    lines = text.splitlines()
    assert done == 1 and 3 <= len(lines) <= 15 and not text.startswith("{")
    assert lines[0].startswith("validate: FAIL -> exit 1 (40 violations")
    assert any("and 35 more violations" in line for line in lines)
    assert lines[-1].startswith("Details: archkeel validate --text")


def test_the_readme_ci_example_prints_at_most_one_screen() -> None:
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    section = readme.split("### In CI", 1)[1].split("\n### ", 1)[0].split("\n## ", 1)[0]
    assert "archkeel validate --summary" in section
    printed = section.split("```text", 1)[1].split("```", 1)[0].strip().splitlines()
    assert len(printed) <= 15
    assert core_only.help_for(core_only.Command.VALIDATE).count("--summary") >= 3


@pytest.mark.parametrize(
    "kind",
    ["collection_refused", "request_mismatch", "invalid_input", "io_error",
     "core_binary_not_found", "not_on_this_development_line", "core_error", "internal_error"],
)  # fmt: skip
def test_each_refusal_kind_has_plain_words_and_its_own_fix(
    kind: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """#1353: no OS error code, no `development line`, and a fix for the kind."""
    from archkeel.cli.core_frame import RefusalKind

    message = "cannot open x [Errno 2] No such file or directory: 'x' (os error 2)"
    core_only._refused(core_only.Command.VALIDATE, RefusalKind(kind), message, False)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "validate: REFUSED -> exit 2"
    assert not re.search(r"Errno|os error|development line|No such file", "\n".join(lines))
    assert "file or folder not found" in lines[1] and lines[2].startswith("Fix: ")
    FIXED.setdefault(lines[2], kind)
    assert FIXED[lines[2]] == kind, f"{kind} shares its fix with {FIXED[lines[2]]}"


FIXED: dict[str, str] = {}
