# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1054: `door_reach` and `door` are deprecated spellings of `trojan_horse_reach` and
`trojan_horse`.

A trojan horse is a place that can load code the scan does not see; it is not a claim of malice.
Consumer: a CI job that reads the rows, the notes and the exit code. A contract that still says
`door_reach` gives the same verdicts as the new spelling plus one note that names the new keys.
Both spellings of the key together are a contract problem.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from test_cli_native_python_imports import command, project, rows, verdict
from test_cli_python_gap_effects import FILES, RULES
from test_cli_python_trojan_horse_reach import GIT, TROJAN_HORSE, declaration

MODEL = "src/app/service/model.py"


def _scan(root: Path, binary: Path, declarations: dict[str, Any], version: str) -> dict[str, Any]:
    project(root, {**FILES, MODEL: TROJAN_HORSE}, contract_rules=RULES)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["schema_version"] = version
    contract["declarations"] = declarations
    path.write_text(json.dumps(contract))
    subprocess.run(["git", "-C", str(root), "commit", "-qam", "alias"], check=True, env=GIT)
    return verdict(binary, root)


def _old() -> dict[str, Any]:
    record = declaration()
    record["door"] = record.pop("trojan_horse")
    return {"door_reach": [record]}


def test_an_old_contract_gives_the_same_verdicts_and_one_note(
    release_core: Path, tmp_path: Path
) -> None:
    new = _scan(tmp_path / "new", release_core, {"trojan_horse_reach": [declaration()]}, "3.20.0")
    for version in ("3.15.0", "3.19.0", "3.20.0"):
        old = _scan(tmp_path / version, release_core, _old(), version)
        assert rows(old) == rows(new), version
        assert set(rows(old).values()) == {"PASS"}, old
        assert old["frame"]["trojan_horse_reach"] == new["frame"]["trojan_horse_reach"]
        (note,) = old["frame"]["notes"]
        assert note["code"] == "deprecated.trojan_horse_reach"
        assert "trojan_horse_reach" in note["text"] and "trojan_horse" in note["text"]
        assert old["exit_code"] == new["exit_code"] == 0
    assert "notes" not in new["frame"]
    text = command(release_core, tmp_path / "3.19.0", "--text").stdout
    assert text.count("Note (deprecated.trojan_horse_reach)") == 1, text


def test_a_mixed_spelling_inside_one_record_is_one_note(release_core: Path, tmp_path: Path) -> None:
    record = declaration()
    record["door"] = record.pop("trojan_horse")
    result = _scan(tmp_path, release_core, {"trojan_horse_reach": [record]}, "3.20.0")

    assert len(result["frame"]["notes"]) == 1, result["frame"]


def test_both_spellings_together_are_a_contract_problem(release_core: Path, tmp_path: Path) -> None:
    both = {**_old(), "trojan_horse_reach": [declaration(id="D-OTHER")]}
    result = _scan(tmp_path / "keys", release_core, both, "3.20.0")
    assert result["exit_code"] == 2 and "both door_reach and trojan_horse_reach" in json.dumps(
        result
    ), result

    record = declaration()
    record["door"] = "eval"
    result = _scan(tmp_path / "fields", release_core, {"trojan_horse_reach": [record]}, "3.20.0")
    assert result["exit_code"] == 2 and "both door and trojan_horse" in json.dumps(result), result
