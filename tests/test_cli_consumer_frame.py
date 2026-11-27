# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1963 point 3: the JSON keys that the EE and CE gates read from `validate --json`.

The gates are Python scripts of the consumers. They read these keys of the document:
`status`, `exit_code`, the rules `frame.rules`, `frame.unknown_kinds`, the gap `kind` of
`frame.gaps`, `frame.measures` and `baseline.state`. A rename or a removal of one key fails here,
so a consumer sees the change in ArchKeel and not in its own gate.

The project has the `[scan]` options of the EE `archkeel.toml` (4.0.1 refused them). The EE gate
(`script/architecture`, ArchKeel 5.0 command line) runs `validate --baseline`, `report --output` for
the page and `report --output --format json` for the frame: the last test runs these commands and
decides as the gate does (an accepted UNKNOWN passes, a drift fails, a refusal fails closed).
"""

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from core_support import run

from archkeel.cli import core_only
from archkeel.cli.init_draft import draft, write_missing

# The counters that a consumer compares with its budget (#1919, `calls_unresolved` and others).
MEASURES = ("calls_total", "calls_unresolved", "typing_positions", "untyped_private_accesses")
GAP_KEYS = ("kind", "reason", "subject")
STATUSES = {"PASS", "FAIL", "UNKNOWN"}


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="module")
def documents(
    tmp_path_factory: pytest.TempPathFactory, release_core: Path
) -> Iterator[dict[str, tuple[int, dict[str, Any]]]]:
    """One drafted Python project with the EE scan options and its runs of the EE gate commands."""
    root = tmp_path_factory.mktemp("consumer") / "demo"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (root / "demo" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    write_missing(root, draft(root))
    with (root / "archkeel.toml").open("a", encoding="utf-8") as handle:
        handle.write("collector_output_limit_bytes = 268435456\ncollector_timeout_seconds = 900\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: release_core)
        found = {
            "plain": run("validate", "--root", str(root)),
            "written": run("validate", "--root", str(root), "--write-baseline", "b.json"),
            "checked": run("validate", "--root", str(root), "--baseline", "b.json"),
            "page": run("report", "--root", str(root), "--output", str(root / "page.html")),
            "frame": run(
                "report",
                "--root",
                str(root),
                "--output",
                str(root / "frame.json"),
                "--format",
                "json",
            ),
        }
        (root / "demo" / "b.py").write_text("value = eval('1')\n", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "an undeclared dynamic site")
        found["drift"] = run("validate", "--root", str(root), "--baseline", "b.json")
        yield found


def _mapping(value: Any, where: str) -> dict[str, Any]:
    assert isinstance(value, dict), f"{where} must be an object, got {type(value).__name__}"
    return value


def test_the_document_keys_the_gates_read(documents: dict[str, tuple[int, dict[str, Any]]]) -> None:
    code, document = documents["plain"]
    assert document["status"] in STATUSES
    assert document["exit_code"] == code == 2
    assert document["status"] == "UNKNOWN"
    assert isinstance(document["gaps"], list)
    frame = _mapping(document["frame"], "frame")
    assert isinstance(frame["status"], str)
    assert _mapping(frame["unknown_kinds"], "frame.unknown_kinds") == {}


def test_each_rule_is_a_kind_and_a_status(
    documents: dict[str, tuple[int, dict[str, Any]]],
) -> None:
    _, document = documents["plain"]
    rules = _mapping(document["frame"]["rules"], "frame.rules")
    assert rules, "a drafted contract has rules"
    for rule_id, row in rules.items():
        assert isinstance(rule_id, str)
        assert isinstance(row, list) and len(row) == 2, f"{rule_id}: [kind, status]"
        kind, status = row
        assert isinstance(kind, str) and kind
        assert status in STATUSES, f"{rule_id}: {status}"


def test_each_gap_has_a_kind_reason_and_subject(
    documents: dict[str, tuple[int, dict[str, Any]]],
) -> None:
    _, document = documents["plain"]
    gaps = document["frame"]["gaps"]
    assert gaps, "the drafted contract has open decisions, so it has gaps"
    for gap in gaps:
        for key in GAP_KEYS:
            assert key in gap, f"gap lacks {key!r}"
        assert isinstance(gap["kind"], str) and gap["kind"]


def test_the_measures_hold_the_counters_of_the_budgets(
    documents: dict[str, tuple[int, dict[str, Any]]],
) -> None:
    _, document = documents["plain"]
    measures = _mapping(document["frame"]["measures"], "frame.measures")
    for key in MEASURES:
        assert isinstance(measures[key], int), f"measures.{key} must be an integer"


def test_the_baseline_state_is_written_then_current(
    documents: dict[str, tuple[int, dict[str, Any]]],
) -> None:
    code, written = documents["written"]
    assert code == 2
    assert _mapping(written["baseline"], "baseline")["state"] == "written"
    code, checked = documents["checked"]
    assert code == 2
    assert _mapping(checked["baseline"], "baseline")["state"] == "current"


def _gate(document: dict[str, Any], code: int) -> int:
    """The decision of the EE gate on a `validate --baseline --json` document."""
    if "refusal" in document or document["exit_code"] != code:
        return 2
    if code in (0, 1):
        return code
    return 0 if document["baseline"]["state"] == "current" else 2


def test_the_ee_gate_commands_accept_the_baseline_and_fail_on_a_drift(
    documents: dict[str, tuple[int, dict[str, Any]]],
) -> None:
    for name in ("plain", "written", "checked", "page", "frame", "drift"):
        assert "refusal" not in documents[name][1], name  # the EE scan options are read
    assert _gate(documents["checked"][1], documents["checked"][0]) == 0
    code, drift = documents["drift"]
    assert (code, drift["baseline"]["state"], _gate(drift, code)) == (1, "drift", 1)
    # `report --output` writes the page and the JSON frame that the EE artifacts keep.
    root = Path(documents["page"][1]["root"])
    assert (
        (root / "page.html")
        .read_text(encoding="utf-8")
        .lstrip()
        .lower()
        .startswith("<!doctype html")
    )
    frame = json.loads((root / "frame.json").read_text(encoding="utf-8"))
    assert {"rules", "gaps", "measures", "contract_digest"} <= set(frame)
    assert documents["page"][0] == documents["frame"][0] == documents["plain"][0]
