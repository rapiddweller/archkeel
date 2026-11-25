# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1963 point 3: the JSON keys that the EE and CE gates read from `validate --json`.

The gates are Python scripts of the consumers. They read these keys of the document:
`status`, `exit_code`, the rules `frame.rules`, `frame.unknown_kinds`, the gap `kind` of
`frame.gaps`, `frame.measures` and `baseline.state`. A rename or a removal of one key fails here,
so a consumer sees the change in ArchKeel and not in its own gate.
"""

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
    """One drafted Python project and its three runs: plain, written baseline, checked baseline."""
    root = tmp_path_factory.mktemp("consumer") / "demo"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (root / "demo" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    write_missing(root, draft(root))
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: release_core)
        yield {
            "plain": run("validate", "--root", str(root)),
            "written": run("validate", "--root", str(root), "--write-baseline", "b.json"),
            "checked": run("validate", "--root", str(root), "--baseline", "b.json"),
        }


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
