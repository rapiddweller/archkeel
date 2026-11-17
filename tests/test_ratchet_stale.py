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
