# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-733: a growth entry whose finding is gone is stale. The ratchet fails; `--write` drops it."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from native_expected import main, stale, tokens  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GAP = ["collection_gap", "a", "r"]
PIN = {"rules": {"R": "UNKNOWN"}, "unknown": {"R": "scope_incomplete"}, "gaps": [GAP]}
REASON = "a new collector limit, decided on 2026-11-17 in the decision log"
LIVE = {"entry": ["gap", *GAP], "reason": REASON}
GONE = {"entry": ["violation", "R", "m.a", "m.b", "forbidden import"], "reason": REASON}


def _result() -> dict:
    frame = {
        "rules": {"R": ["forbidden_dependency", "UNKNOWN"]},
        "unknown_kinds": {"R": "scope_incomplete"},
        "collection_gaps": [{"kind": GAP[0], "subjects": [GAP[1]], "reason": GAP[2]}],
        "violations": {},
        "details": {},
        "locations": {},
    }
    return {"frame": frame, "gaps": [], "exit_code": 2}


def test_the_tokens_of_a_pin_are_its_gaps_violations_non_pass_rules_and_unknown_kinds() -> None:
    assert tokens(PIN) == {
        ("gap", *GAP),
        ("rule", "R", "UNKNOWN"),
        ("unknown", "R", "scope_incomplete"),
    }


def test_an_entry_of_a_finding_that_the_pin_does_not_hold_is_stale() -> None:
    assert stale(PIN, {"raised": [LIVE, GONE]}) == [GONE]
    assert stale(PIN, {"raised": [LIVE]}) == []


def test_check_mode_fails_on_a_stale_entry_and_write_drops_it(tmp_path: Path, capsys) -> None:
    result, pin, growth = tmp_path / "r.json", tmp_path / "p.json", tmp_path / "g.json"
    result.write_text(json.dumps(_result()))
    pin.write_text(json.dumps(PIN))
    growth.write_text(json.dumps({"raised": [LIVE, GONE]}))
    run = [str(result), str(pin), "--growth", str(growth)]
    assert main(run) == 1 and "stale growth entry" in capsys.readouterr().err
    assert main([*run, "--write"]) == 0
    assert json.loads(growth.read_text())["raised"] == [LIVE]
    assert main(run) == 0


def test_a_missing_base_ref_is_printed_not_skipped_silently(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    result, pin = tmp_path / "r.json", tmp_path / "p.json"
    result.write_text(json.dumps(_result()))
    pin.write_text(json.dumps(PIN))
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True, cwd=tmp_path)
    assert main([str(result), "p.json", "--base-ref", "origin/nowhere"]) == 0
    assert "ratchet: base origin/nowhere unavailable, skipped" in capsys.readouterr().err


@pytest.mark.parametrize(
    "path",
    ["native/expected-growth.json", "docs/architecture/target/shell-expected-growth.json"],
)
def test_the_growth_files_of_the_repository_hold_no_stale_entry(path: str) -> None:
    pins = {
        "native/expected-growth.json": "native/expected-gaps.json",
        "docs/architecture/target/shell-expected-growth.json": (
            "docs/architecture/target/shell-expected.json"
        ),
    }
    pin = json.loads((ROOT / pins[path]).read_text(encoding="utf-8"))
    listed = json.loads((ROOT / path).read_text(encoding="utf-8"))
    assert stale(pin, listed) == []


def test_the_base_of_the_growth_check_is_the_fork_point_not_the_tip_of_main(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """AD-733: main shrank the pin after this branch left it; that is no growth of the branch."""
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]

    def run(*arguments: str) -> None:
        subprocess.run([*git, *arguments], cwd=tmp_path, check=True, capture_output=True)

    clean = {"rules": {"R": "PASS"}, "unknown": {}, "gaps": [], "violations": []}
    run("init", "-q", "-b", "main")
    (tmp_path / "p.json").write_text(json.dumps(PIN))
    run("add", "-A")
    run("commit", "-q", "-m", "base")
    run("checkout", "-q", "-b", "topic")
    run("checkout", "-q", "main")
    (tmp_path / "p.json").write_text(json.dumps(clean))
    run("commit", "-q", "-am", "main shrinks the pin")
    run("checkout", "-q", "topic")
    result = tmp_path / "r.json"
    result.write_text(json.dumps(_result()))
    monkeypatch.chdir(tmp_path)
    # The branch still holds the older, larger pin and the result equals it: no growth against main.
    assert main([str(result), "p.json", "--base-ref", "main"]) == 0
    assert "growth" not in capsys.readouterr().err


RECEIVER = "A method call may reach the method kind of a type in its own file native.m.b"


def _receiver_result(files: list[str]) -> dict:
    gaps = [
        {
            "kind": "collection_gap",
            "subjects": ["native.m.a"],
            "reason": RECEIVER,
            "evidence": [f"E{i}"],
        }
        for i, _ in enumerate(files)
    ]
    frame = {
        "rules": {"R": ["forbidden_dependency", "UNKNOWN"]},
        "unknown_kinds": {"R": "scope_incomplete"},
        "collection_gaps": gaps,
        "violations": {},
        "details": {},
        "locations": {f"E{i}": {"path": path, "line": 10 + i} for i, path in enumerate(files)},
    }
    return {"frame": frame, "gaps": [], "exit_code": 2}


def test_a_new_receiver_gap_names_the_files_and_the_fix(tmp_path: Path, capsys) -> None:
    """#1571 class: the message says how many gaps, in which files, and how to write the call."""
    result, pin = tmp_path / "r.json", tmp_path / "p.json"
    result.write_text(json.dumps(_receiver_result(["native/m/src/a.rs", "native/m/src/a.rs"])))
    pin.write_text(json.dumps({**PIN, "gaps": []}))
    assert main([str(result), str(pin)]) == 1
    err = capsys.readouterr().err
    assert "your change adds 2 field-receiver gaps in native/m/src/a.rs (2);" in err
    assert "path calls" in err and "bind typed locals" in err and "make self-validate-native" in err


def test_a_pinned_receiver_gap_and_another_new_gap_give_no_receiver_message(
    tmp_path: Path, capsys
) -> None:
    result, pin = tmp_path / "r.json", tmp_path / "p.json"
    pinned = ["collection_gap", "native.m.a", RECEIVER]
    pin.write_text(json.dumps({**PIN, "gaps": [pinned]}))
    result.write_text(json.dumps(_receiver_result(["native/m/src/a.rs"])))
    main([str(result), str(pin)])
    assert "field-receiver" not in capsys.readouterr().err
    other = _receiver_result(["native/m/src/a.rs"])
    other["frame"]["collection_gaps"][0]["reason"] = "another reason"
    pin.write_text(json.dumps({**PIN, "gaps": []}))
    result.write_text(json.dumps(other))
    main([str(result), str(pin)])
    assert "field-receiver" not in capsys.readouterr().err
