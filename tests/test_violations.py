# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-54: the typed read surface over one report's violations, read back from disk."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_codec import raw_observation

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.ir.baseline import ViolationFingerprint, observed_violations, violation_rows
from archkeel.ir.codec import load_observation
from fixtures.architecture_demo import CATALOG

CONFIG = ScanConfig(("shop",), "shop", "architecture-contract.json", "0" * 64)


def _tour_report(tmp_path: Path) -> Path:
    """Run `report` on the `tour` variant (AD-51's own demo) and write its bytes to disk."""
    tour = next(variant for variant in CATALOG if variant.id == "tour")
    root = _prepare_repo(tmp_path, dict(tour.files))
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    report_path = tmp_path / "architecture.json"
    report_path.write_bytes(architecture)
    return report_path


def test_load_observation_reads_the_canonical_report_bytes_back(tmp_path: Path) -> None:
    """`load_observation` is the one supported way in: a path, not the columnar internals."""
    report_path = _tour_report(tmp_path)

    observation = load_observation(report_path)

    assert observation.schema_version == "1.3.0"
    assert len(observation.records("violations") or ()) == 14


def test_violation_rows_type_an_import_violation(tmp_path: Path) -> None:
    """A dependency violation names its modules, its symbol and both components, typed."""
    observation = load_observation(_tour_report(tmp_path))

    row = next(
        row
        for row in violation_rows(observation)
        if row.fingerprint.rules == ("DEP-STORE-NO-MONEY",)
    )

    assert row.source_module == "shop.store.repository"
    assert row.target_module == "shop.model.entities"
    assert row.symbol == "Money"
    assert row.source_component == "store"
    assert row.target_component == "model"


def test_violation_rows_leave_construct_fields_none(tmp_path: Path) -> None:
    """A construct violation crosses no import, so its import fields stay None, not guessed."""
    observation = load_observation(_tour_report(tmp_path))

    row = next(
        row
        for row in violation_rows(observation)
        if row.fingerprint.rules == ("CONSTRUCT-NO-ASSERT",)
    )

    assert row.source_module is None
    assert row.target_module is None
    assert row.symbol is None
    assert row.source_component is None
    assert row.target_component is None


def test_violation_rows_fingerprints_agree_with_ir_baseline(tmp_path: Path) -> None:
    """AD-52: a row's fingerprint is exactly what `ir.baseline` derives, counted the same way."""
    observation = load_observation(_tour_report(tmp_path))

    counted: dict[ViolationFingerprint, int] = {}
    for row in violation_rows(observation):
        counted[row.fingerprint] = counted.get(row.fingerprint, 0) + 1

    assert counted == {item.fingerprint: item.count for item in observed_violations(observation)}


def test_reference_md_snippet_reads_a_report_and_lists_its_rows(tmp_path: Path) -> None:
    """The docs/reference.md snippet, kept in lockstep with this test by hand: same three calls."""
    report_path = _tour_report(tmp_path)

    # --- docs/reference.md snippet begins ---
    from archkeel.ir.baseline import violation_rows
    from archkeel.ir.codec import load_observation

    observation = load_observation(report_path)
    rows = [
        (row.fingerprint, row.source_component, row.target_component)
        for row in violation_rows(observation)
    ]
    # --- docs/reference.md snippet ends ---

    assert len(rows) == 14
    assert all(isinstance(fingerprint, ViolationFingerprint) for fingerprint, _, _ in rows)


def test_load_observation_rejects_a_violation_with_no_rule_ids(tmp_path: Path) -> None:
    """A hand-edited or truncated file must fail loudly, not with an `IndexError` from a count.

    `schema/architecture-ir-common.schema.json` promises `minItems: 1` on a VIOLATION record's
    `rule_ids`, but nothing enforced that at runtime before this: `load_observation` reads an
    arbitrary file, not one this process just wrote, so the promise has to be checked here.
    """
    raw = raw_observation()
    raw["violations"] = [
        {
            "id": "VIO-bad",
            "evidence_class": "VIOLATION",
            "area": "dependency_violations",
            "kind": "forbidden_dependency",
            "title": "bad violation record",
            "subjects": ["a", "b"],
            "evidence_ids": [],
            "rule_ids": [],
            "fact_ids": ["F1"],
            "provenance": [],
            "data": {},
        }
    ]
    report_path = tmp_path / "architecture.json"
    report_path.write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="rule_ids"):
        load_observation(report_path)
