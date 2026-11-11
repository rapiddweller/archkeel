# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-360: the dual run finds a planted difference and names its section, its id and its row."""

from __future__ import annotations

import copy
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any

import pytest

from archkeel.ir.architecture_graph import ArchitectureRuleKind
from archkeel.ir.model import CLASSIFIED_SECTIONS
from tools import dual_run, dual_run_oracle
from tools.dual_run_oracle import Selection

CASE = "fixture/F-architecture"
REPOSITORY = Path(__file__).resolve().parent.parent
Run = tuple[dict[str, Any], dict[str, Any]]


def _case(case_id: str) -> dual_run.Case:
    return next(case for case in dual_run.corpus_cases() if case.id == case_id)


@pytest.fixture(scope="module")
def run() -> Run:
    """The committed oracle and a fresh Python frame, with the sections decoded."""
    case = _case(CASE)
    with dual_run.materialized(case) as root:
        frame = dual_run.run_engine(case, root, None, Selection())
    sections = dual_run_oracle.decode_sections(frame["architecture"])
    oracle = dual_run_oracle.read_oracle(dual_run.oracle_path(case))
    return oracle, {"rules": frame["rules"], "sections": sections}


def _planted(run: Run) -> Run:
    return run[0], copy.deepcopy(run[1])


ALL = Selection()


def _compare(oracle: Any, frame: Any, selection: Selection = ALL) -> list[Any]:
    return dual_run_oracle.compare_case(oracle, frame, selection)


def test_the_python_engine_equals_its_oracle(run: Run) -> None:
    assert _compare(*run) == []


def test_a_changed_verdict_names_the_rule(run: Run) -> None:
    oracle, frame = _planted(run)
    rule = sorted(frame["rules"])[0]
    frame["rules"][rule] = [frame["rules"][rule][0], "FAIL"]
    [difference] = _compare(oracle, frame)
    assert (difference.case, difference.scope, difference.id) == (CASE, "rules", rule)
    assert "FAIL" in difference.detail


def test_a_dropped_row_of_a_large_section_shows_its_expected_content(run: Run) -> None:
    oracle, frame = _planted(run)
    assert "rows" not in oracle["sections"]["evidence"] or all(
        isinstance(item, list) for item in oracle["sections"]["evidence"]["rows"]
    )
    dropped = frame["sections"]["evidence"].pop(7)
    [difference] = _compare(oracle, frame)
    assert (difference.scope, difference.id) == ("evidence", dropped["id"])
    assert difference.detail.startswith("row 7: the candidate drops this row")
    assert dropped["file"] in difference.detail


def test_a_changed_title_of_a_large_section_names_the_field(run: Run) -> None:
    oracle, frame = _planted(run)
    frame["sections"]["modules"][2]["title"] = "planted"
    [difference] = _compare(oracle, frame)
    assert difference.scope == "modules"
    assert difference.detail.startswith("row 2: field title: expected")
    assert '"planted"' in difference.detail


def test_a_reordered_row_is_a_difference(run: Run) -> None:
    oracle, frame = _planted(run)
    rows = frame["sections"]["declarations"]
    rows[2], rows[3] = rows[3], rows[2]
    [difference] = _compare(oracle, frame)
    assert (difference.scope, difference.id) == ("declarations", rows[2]["id"])
    assert "row 2: the order differs" in difference.detail


def test_a_changed_field_of_a_full_row_names_the_field(run: Run) -> None:
    oracle, frame = _planted(run)
    assert all(isinstance(item, dict) for item in oracle["sections"]["packages"]["rows"])
    frame["sections"]["packages"][1]["title"] = "planted"
    [difference] = _compare(oracle, frame)
    assert difference.scope == "packages"
    assert difference.detail.startswith("row 1: field title: expected")


def test_an_added_last_row_is_a_difference(run: Run) -> None:
    oracle, frame = _planted(run)
    frame["sections"]["cycles"].append({"id": "CYCLE-PLANTED", "rule_ids": []})
    [difference] = _compare(oracle, frame)
    assert (difference.scope, difference.id) == ("cycles", "CYCLE-PLANTED")


def test_a_section_outside_the_known_list_is_a_difference(run: Run) -> None:
    oracle, frame = _planted(run)
    frame["sections"]["new_section"] = [{"id": "N1"}]
    [difference] = _compare(oracle, frame)
    assert (difference.scope, difference.id) == ("new_section", "-")


def test_a_slice_compares_only_what_it_owns(run: Run) -> None:
    oracle, frame = _planted(run)
    frame["sections"]["modules"].pop(0)
    rule, (kind, _) = next(iter(sorted(frame["rules"].items())))
    frame["rules"][rule] = [kind, "FAIL"]
    assert kind != "no_component_cycles"
    assert _compare(oracle, frame, dual_run_oracle.selection_of("imports", "cycles")) == []
    owned = dual_run_oracle.selection_of("modules", kind)
    assert [d.scope for d in _compare(oracle, frame, owned)] == ["rules", "modules"]


def _rule_oracle(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case": {"id": "c"},
        "rules": {"A": ["forbidden_dependency", "FAIL"], "B": ["interface_boundary", "FAIL"]},
        "sections": {"unknowns": dual_run_oracle.oracle_section(rows)},
    }


def test_a_family_owns_the_rule_rows_of_its_rules() -> None:
    rows = [{"id": "V1", "rule_ids": ["A"]}, {"id": "V2", "rule_ids": ["B"]}]
    oracle = _rule_oracle(rows)
    frame = {"rules": oracle["rules"], "sections": {"unknowns": rows[:1]}}
    assert _compare(oracle, frame, dual_run_oracle.selection_of("unknowns", "direction")) == []
    [difference] = _compare(oracle, frame, dual_run_oracle.selection_of("unknowns", None))
    assert difference.id == "V2"


def test_a_family_slice_sees_a_dropped_row_without_rule_ids() -> None:
    rows = [{"id": "U0", "rule_ids": []}, {"id": "U1", "rule_ids": ["A"]}]
    oracle = _rule_oracle(rows)
    frame = {"rules": oracle["rules"], "sections": {"unknowns": rows[1:]}}
    [difference] = _compare(oracle, frame, dual_run_oracle.selection_of("unknowns", "direction"))
    assert (difference.scope, difference.id) == ("unknowns", "U0")


@pytest.mark.parametrize(
    ("sections", "families"),
    [(None, "directon"), (None, "forbidden_dependencyy"), ("modulez", None)],
)
def test_an_unknown_section_or_family_is_rejected(sections: str | None, families: str) -> None:
    with pytest.raises(ValueError, match="unknown"):
        dual_run_oracle.selection_of(sections, families)


def test_a_rule_kind_and_a_family_name_both_select() -> None:
    kinds = dual_run_oracle.selection_of(None, "cycles,layer_order").kinds
    assert kinds == {"no_component_cycles", "layer_order"}


def test_a_run_that_selects_nothing_fails(capsys: pytest.CaptureFixture[str]) -> None:
    assert dual_run.main(["compare", "--case", "fixture/H-ulm"]) == 2
    assert "no case matches fixture/H-ulm" in capsys.readouterr().out
    assert dual_run.main(["compare", "--case", "fixture/H-uml", "--families", "directon"]) == 2
    arguments = ["compare", "--case", "fixture/H-uml", "--families", "direction", "--jobs", "1"]
    assert dual_run.main(arguments) == 2
    assert "0 rules" in capsys.readouterr().out


def test_the_schema_lists_every_rule_kind_and_section() -> None:
    schema = dual_run_oracle.SCHEMA
    assert set(schema["rule_kinds"]) == {k.value for k in ArchitectureRuleKind} | {"uml_target"}
    compared = {*schema["sections"], *schema["not_compared"]}
    assert compared == {*CLASSIFIED_SECTIONS, "evidence"}
    family_kinds = [kind for kinds in schema["families"].values() for kind in kinds]
    assert sorted(family_kinds) == sorted({k.value for k in ArchitectureRuleKind})


def test_a_delta_oracle_reads_back_its_rows() -> None:
    rows = [{"id": f"R{index}", "n": index} for index in range(300)]
    base_entry = dual_run_oracle.oracle_section(rows)
    base = dual_run_oracle.oracle_rows(base_entry)
    changed = [*rows[:100], {"id": "NEW"}, *rows[101:]]
    delta = dual_run_oracle.oracle_section(changed, ("b", base_entry["digest"], base))
    assert len(delta["rows"]) == 3
    plain = dual_run_oracle.oracle_rows(dual_run_oracle.oracle_section(changed))
    assert dual_run_oracle.oracle_rows(delta, base) == plain


def test_each_corpus_case_has_one_oracle() -> None:
    expected = {dual_run.oracle_path(case).name for case in dual_run.corpus_cases()}
    assert {path.name for path in dual_run_oracle.ORACLE_DIR.glob("*.json.gz")} == expected


def test_the_corpus_has_rust_cases_and_false_pass_probes() -> None:
    ids = [case.id for case in dual_run.corpus_cases()]
    assert "rust/native" in ids
    assert any(i.startswith("probe/rust_impls-") for i in ids)
    assert any(i.startswith("probe/gate-") for i in ids)


def test_the_rule_kinds_with_few_fail_cases_are_the_named_gap() -> None:
    """A FAIL case of a kind is its own when its violation rows differ from the other cases. A
    kind below `fail_case_minimum` is the named gap: its slice adds FAIL cases before it deletes
    Python code (AD-360)."""
    own: dict[str, set[frozenset[str]]] = {kind: set() for kind in dual_run_oracle.RULE_KINDS}
    for path in dual_run_oracle.ORACLE_DIR.glob("*.json.gz"):
        oracle = dual_run_oracle.read_oracle(path)
        if oracle["sections"] is None:
            continue
        rows = dual_run_oracle.section_rows(oracle, "violations")
        for rule, (kind, status) in oracle["rules"].items():
            if status == "FAIL":
                own[kind].add(frozenset(row.digest for row in rows if rule in row.rule_ids))
    minimum = dual_run_oracle.SCHEMA["fail_case_minimum"]
    gap = {kind for kind, cases in own.items() if len(cases) < minimum}
    assert gap == set(dual_run_oracle.SCHEMA["fail_case_gap"])


def test_the_fixture_corpus_equals_its_oracles() -> None:
    """The fast subset of the PR suite: a change of the Python result makes it fail."""
    assert dual_run.main(["compare", "--case", "fixture/*"]) == 0


def test_record_needs_a_reason_and_a_committed_source(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert dual_run.main(["record", "--case", "fixture/E-runtime"]) == 2
    assert "--reason" in capsys.readouterr().out
    monkeypatch.setattr(dual_run, "dirty_sources", lambda: ["src/archkeel/x.py"])
    assert dual_run.main(["record", "--case", "fixture/E-runtime", "--reason", "test"]) == 2
    assert "not committed" in capsys.readouterr().out


def test_record_shows_the_differences_that_it_overwrites(tmp_path: Path) -> None:
    case = _case("fixture/H-uml")
    previous, output = tmp_path / "previous", tmp_path / "output"
    previous.mkdir()
    old = dual_run_oracle.read_oracle(dual_run.oracle_path(case))
    rule = next(iter(old["rules"]))
    old["rules"][rule] = [old["rules"][rule][0], "FAIL"]
    dual_run_oracle.write_oracle(dual_run_oracle.oracle_file(previous, case.id), old)
    [difference] = dual_run.record_case((case, previous, output))
    assert (difference.scope, difference.id) == ("rules", rule)
    assert dual_run_oracle.oracle_file(output, case.id).is_file()


def test_an_engine_that_does_not_answer_is_a_difference(
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = ["compare", "--case", "fixture/E-runtime", "--jobs", "1"]
    assert dual_run.main([*arguments, "--engine-command", "sleep 5", "--engine-timeout", "1"]) == 1
    output = capsys.readouterr().out
    assert "fixture/E-runtime: engine: -: the engine did not answer in 1 s" in output
    assert dual_run.main([*arguments, "--engine-command", "exit 4"]) == 1
    assert "the engine exits with 4" in capsys.readouterr().out


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
    assert f"engine: {command}" in output
    assert "1 differences" in output


def _python_with(tmp_path: Path, version: str, source: Path | None = None) -> Path:
    """An interpreter whose installed `archkeel` metadata says `version`, and that imports
    `archkeel` from `source` when given. The host and each collector process that it starts see
    both (`-I` still reads the site-packages)."""
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)
    [site] = (venv / "lib").glob("python*/site-packages")
    dist = site / f"archkeel-{version}.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(f"Metadata-Version: 2.1\nName: archkeel\nVersion: {version}\n")
    real = sysconfig.get_paths()["purelib"]
    lines = [f"import site; site.addsitedir({real!r})"]
    if source is not None:
        lines.append(f"import sys; sys.path.insert(0, {str(source)!r})")
    (site / "installed.pth").write_text("\n".join(lines) + "\n")
    return venv / "bin" / "python"


INVENTORY_CASES = ["--case", "fixture/J-compass", "--case", "fixture/L-nest-realworld"]


def _compare_with(python: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(python), "-m", "tools.dual_run", "compare", *INVENTORY_CASES, "--jobs", "2"],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(sys.platform == "win32", reason="the venv layout of the test is POSIX")
def test_the_oracles_hold_for_any_installed_version(tmp_path: Path) -> None:
    """CI installs a version from Git (for example `4.0.2.dev293+g...`), a local install can
    have `0.0.0`. The member inventory binding reads the adapter version, so the harness pins it."""
    python = _python_with(tmp_path, "9.9.9.dev1+gplanted")
    version = subprocess.run(
        [str(python), "-I", "-c", "import importlib.metadata as m; print(m.version('archkeel'))"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert version == "9.9.9.dev1+gplanted"
    done = _compare_with(python)
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]


@pytest.mark.skipif(sys.platform == "win32", reason="the venv layout of the test is POSIX")
def test_the_oracles_hold_when_the_python_source_changes(tmp_path: Path) -> None:
    """The binding reads the code digest of the package and of the collector. A comment in a
    collector file changes both digests; the harness pins them, so the oracles stay valid."""
    source = tmp_path / "src"
    shutil.copytree(REPOSITORY / "src", source, ignore=shutil.ignore_patterns("__pycache__"))
    changed = source / "archkeel/analyzer/typescript/__init__.py"
    changed.write_text(changed.read_text() + "# A planted comment changes the code digest.\n")
    python = _python_with(tmp_path, "0.0.0", source)
    imported = subprocess.run(
        [str(python), "-I", "-c", "import archkeel; print(archkeel.__file__)"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert imported.startswith(str(source))
    done = _compare_with(python)
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]


def test_a_changed_member_inventory_row_still_fails() -> None:
    """The pin fixes the inputs of the binding; it masks no row. A changed row is a difference."""
    case = _case("fixture/L-nest-realworld")
    with dual_run.materialized(case) as root:
        frame = dual_run.run_engine(case, root, None, Selection())
    oracle = dual_run_oracle.read_oracle(dual_run.oracle_path(case))
    sections = dual_run_oracle.decode_sections(frame["architecture"])
    assert _compare(oracle, {"rules": frame["rules"], "sections": sections}) == []
    rows = sections["scope_observations"]
    [index] = [i for i, row in enumerate(rows) if row["id"].startswith("MEMBER-INVENTORY-")]
    rows[index]["data"]["binding"] = "0" * 64
    [difference] = _compare(oracle, {"rules": frame["rules"], "sections": sections})
    assert (difference.scope, difference.id) == ("scope_observations", rows[index]["id"])
    assert "differs" in difference.detail


def test_the_pin_changes_only_the_adapter_identity_of_this_install() -> None:
    import json
    import zlib

    from tools.dual_run_python import PINNED_DIGEST, PINNED_VERSION, with_pinned_version

    reply = {"facts": {"adapter": {"name": "x", "version": "4.0.2.dev1+g1"}, "files": [1]}}
    plain = json.dumps(reply).encode()
    assert json.loads(with_pinned_version(plain, "4.0.2.dev1+g1"))["facts"] == {
        "adapter": {"name": "x", "version": PINNED_VERSION, "code_digest": PINNED_DIGEST},
        "files": [1],
    }
    pinned = with_pinned_version(zlib.compress(plain), "4.0.2.dev1+g1")
    assert json.loads(zlib.decompress(pinned))["facts"]["adapter"]["version"] == PINNED_VERSION
    # Another producer (a native collector of its own version) and a reply that is no JSON stay.
    assert with_pinned_version(plain, "5.0.0") == plain
    assert with_pinned_version(b"not json", "4.0.2.dev1+g1") == b"not json"


def test_a_run_with_no_owned_rule_and_no_section_fails(capsys: pytest.CaptureFixture[str]) -> None:
    """58 corpus cases have no rule: with no section either, such a run compares nothing."""
    case = _case("fixture/E-runtime")
    assert dual_run.report([(case, 0, [])], Selection((), None), None, 0.0) == 2
    assert "compares nothing" in capsys.readouterr().out
    assert dual_run.report([(case, 0, [])], Selection(("modules",), None), None, 0.0) == 0


def test_none_owns_no_section_and_no_family() -> None:
    selection = dual_run_oracle.selection_of("none", "none")
    assert (selection.sections, selection.kinds, selection.owns_nothing()) == ((), set(), True)
    assert not dual_run_oracle.selection_of("modules", "none").owns_nothing()


def test_an_unsupported_part_of_the_frame_is_a_named_difference(run: Run) -> None:
    """AD-363: an engine that names a part unsupported is never equal on that part."""
    oracle, _ = run
    rule = sorted(oracle["rules"])[0]
    frame = {
        "rules": {},
        "unsupported": {
            "rules": {rule: "unsupported: rule kind X"},
            "sections": {"modules": "unsupported: section modules: slice S1 ports it"},
        },
    }
    selection = dual_run_oracle.selection_of("modules", oracle["rules"][rule][0])
    got = [(d.scope, d.id, d.detail) for d in _compare(oracle, frame, selection)]
    assert got[0][:2] == ("rules", rule) and "are unsupported" in got[0][2]
    assert ("modules", "-", "unsupported: section modules: slice S1 ports it") in got
    frame["unsupported"]["rules"] = "unsupported: contract declarations"
    [first, *_] = _compare(oracle, frame, selection)
    assert (first.scope, first.id) == ("rules", "-")


def test_the_self_test_compares_the_rule_kinds_that_the_engine_read(run: Run) -> None:
    oracle, _ = run
    kinds = {rule: kind for rule, (kind, _) in oracle["rules"].items()}
    frame = {"rules": {}, "self_test": {"contract": {"rules": kinds}, "reply": {"files": 3}}}
    selection = Selection((), frozenset(), self_test=True)
    assert _compare(oracle, frame, selection) == []
    rule = sorted(kinds)[0]
    frame["self_test"]["contract"]["rules"][rule] = "layer_order"
    frame["self_test"]["reply"] = {"refused": "not compressed"}
    got = [(d.scope, d.id) for d in _compare(oracle, frame, selection)]
    assert got == [("self_test", rule), ("self_test", "reply")]


def test_a_self_test_run_owns_no_part_and_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    """AD-363: the wiring check owns no rule and no section, and its summary says self-test."""
    case = _case("fixture/E-runtime")
    self_test = Selection((), frozenset(), self_test=True)
    assert dual_run.report([(case, 0, [])], self_test, None, 0.0) == 0
    assert "dual run: self-test; " in capsys.readouterr().out


@pytest.mark.parametrize(
    ("unsupported", "code", "accepted"),
    [
        ({"rules": {"R": "unsupported: rule kind X"}}, 3, True),
        ({"rules": {}, "sections": {}, "report": None}, 3, False),
        ({"sections": {"modules": "unsupported: section modules"}}, 0, False),
        ({}, 0, True),
    ],
)
def test_exit_3_goes_only_with_a_frame_that_names_a_gap(
    tmp_path: Path, unsupported: dict[str, Any], code: int, accepted: bool
) -> None:
    """AD-363: a frame without verdicts is never a plain success, and exit 3 is never empty."""
    import json

    frame = {"rules": {}, "unsupported": unsupported}
    if accepted and not unsupported:
        frame["self_test"] = {"contract": {"rules": {}}, "reply": {"files": 1}}
    script = tmp_path / "engine.py"
    script.write_text(f"import sys\nprint({json.dumps(json.dumps(frame))})\nsys.exit({code})\n")
    case = _case("fixture/E-runtime")
    with dual_run.materialized(case) as root:
        got = dual_run.run_engine(case, root, f"{sys.executable} {script}", Selection())
    assert ("error" not in got) is accepted, got
