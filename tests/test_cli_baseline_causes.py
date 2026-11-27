# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1330 (#2184): a baseline does not drift when only the way a rule shows its causes changes.

A rule can have several causes and its row shows the first. Before AD-1330 the baseline keyed that
first cause only, so resolving it showed the next cause as new debt (thousands of entries on a real
tree). A collector gap is matched by its exact key. Plants: an interface rule with an unread import
(the first cause) and a dynamic import (a collector gap and a later cause).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from python_interface_plants import DEFINES, IMPL, LIB, Plant, build
from test_cli_native_python_imports import verdict

SINK = "def sink(value: object) -> None:\n    pass\n"
ENTRY = ("app.lib.impl:f",)
FILES = {LIB: "", IMPL: DEFINES, "src/app/sink.py": SINK}
HEAD = "from app.lib.impl import f\nimport importlib\n"
LOAD = "def load(name):\n    return importlib.import_module(name)\n"
UNREAD = "import app.lib as pkg\nfrom app.sink import sink\nsink(pkg)\n"
BASELINE = "baseline.json"


def tree(root: Path, consumer: str) -> Path:
    root.mkdir(parents=True)
    plant = Plant("causes", consumer, ENTRY, FILES, core=("UNKNOWN",))
    return build(root, plant)


def write(release_core: Path, root: Path) -> dict[str, Any]:
    verdict(release_core, root, "validate", "--write-baseline", BASELINE)
    return json.loads((root / BASELINE).read_text(encoding="utf-8"))


def compare(release_core: Path, root: Path, document: dict[str, Any]) -> dict[str, Any]:
    (root / BASELINE).write_text(json.dumps(document), encoding="utf-8")
    result = verdict(release_core, root, "validate", "--baseline", BASELINE)
    return result["frame"]["baseline"]


def kinds(rows: list[dict[str, Any]]) -> set[str]:
    return {row["kind"] for row in rows}


def test_a_file_names_every_cause_of_a_rule_and_stays_current(
    release_core: Path, tmp_path: Path
) -> None:
    root = tree(tmp_path / "a", HEAD + UNREAD + "f()\n" + LOAD)
    document = write(release_core, root)
    assert document["schema_version"] == "1.5.0"
    rule = {e["kind"] for e in document["unknowns"] if e["subject"] == "BOUNDARY"}
    assert {"interface_gap", "gap_effect", "incomplete_scope"} <= rule, rule
    found = compare(release_core, root, document)
    assert (found["state"], found["new"], found["gone"]) == ("current", [], [])


def test_resolving_the_first_cause_is_gone_and_never_a_new_cause(
    release_core: Path, tmp_path: Path
) -> None:
    document = write(release_core, tree(tmp_path / "a", HEAD + UNREAD + "f()\n" + LOAD))
    resolved = tree(tmp_path / "b", HEAD + "f()\n" + LOAD)
    found = compare(release_core, resolved, document)
    assert found["new"] == [], found["new"]
    assert "interface_gap" in kinds(found["gone"])


def test_a_file_of_1_4_0_names_the_first_cause_only_and_stays_current(
    release_core: Path, tmp_path: Path
) -> None:
    root = tree(tmp_path / "a", HEAD + UNREAD + "f()\n" + LOAD)
    document = write(release_core, root)
    document["schema_version"] = "1.4.0"
    first = {"interface_gap", "hygiene.interface.usage_unknown"}
    document["unknowns"] = [
        e for e in document["unknowns"] if e["subject"] != "BOUNDARY" or e["kind"] in first
    ]
    found = compare(release_core, root, document)
    assert (found["state"], found["new"], found["gone"]) == ("current", [], [])


def test_a_swap_of_one_collector_gap_for_another_is_drift_never_current(
    release_core: Path, tmp_path: Path
) -> None:
    """A baseline never takes one gap for another: an entry is matched by its exact key."""
    document = write(release_core, tree(tmp_path / "a", HEAD + "f()\n" + LOAD))
    swapped = HEAD + "f()\ndef load(name):\n    return importlib.reload(name)\n"
    found = compare(release_core, tree(tmp_path / "b", swapped), document)
    assert found["state"] == "drift"
    assert [row["reason"] for row in found["new"] if row["kind"] == "source_resolution_gap"] == [
        "dynamic_import: importlib.reload"
    ], found["new"]
    assert len([row for row in found["gone"] if row["kind"] == "source_resolution_gap"]) == 1


def test_a_reworded_collector_text_is_one_new_and_one_gone_entry(
    release_core: Path, tmp_path: Path
) -> None:
    root = tree(tmp_path / "a", HEAD + "f()\n" + LOAD)
    document = write(release_core, root)
    for entry in document["unknowns"]:
        if entry["kind"] == "source_resolution_gap":
            entry["reason"] = "an older text of the same gap"
    found = compare(release_core, root, document)
    assert found["state"] == "drift"
    assert len(found["new"]) == 1 and len(found["gone"]) == 1, found


def test_validate_and_report_give_the_same_gap_list(release_core: Path, tmp_path: Path) -> None:
    root = tree(tmp_path / "a", HEAD + UNREAD + "f()\n" + LOAD)
    checked = verdict(release_core, root, "validate")
    reported = verdict(release_core, root, "report")

    def listed(result: dict[str, Any]) -> tuple[list[str], list[str]]:
        frame = result["frame"]
        collection = [json.dumps(g, sort_keys=True) for g in frame["collection_gaps"]]
        return collection, [json.dumps(g, sort_keys=True) for g in result["gaps"]]

    assert listed(checked) == listed(reported)
    assert listed(checked)[0], "the plant has a collector gap"
    shutil.rmtree(root)
