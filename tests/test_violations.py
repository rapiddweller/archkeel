# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-54/AD-64: the typed read surface over one report's violations, read back from disk."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_codec import raw_observation

from archkeel.analyzer import observe
from archkeel.api import ViolationFingerprint as ApiViolationFingerprint
from archkeel.api import ViolationRow, load_violations
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.ir.baseline import ViolationFingerprint, observed_violations
from archkeel.ir.codec import decode_canonical_model, parse_contract, parse_observation
from fixtures.architecture_demo import CATALOG

CONFIG = ScanConfig(("shop",), "shop", "architecture-contract.json", "0" * 64)
ROOT = Path(__file__).parents[1]


def _tour_report(tmp_path: Path) -> Path:
    """Run `report` on the `tour` variant (AD-51's own demo) and write its bytes to disk."""
    tour = next(variant for variant in CATALOG if variant.id == "tour")
    root = _prepare_repo(tmp_path, dict(tour.files))
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    report_path = tmp_path / "architecture.json"
    report_path.write_bytes(architecture)
    return report_path


def test_load_violations_reads_the_canonical_report_bytes_back(tmp_path: Path) -> None:
    """`archkeel.api.load_violations` is the one supported way in (AD-64, AD-70): a path in,
    typed rows out, and no `Observation` crossing the boundary in between."""
    report_path = _tour_report(tmp_path)

    rows = load_violations(report_path)

    assert len(rows) == 20
    assert all(isinstance(row, ViolationRow) for row in rows)


def test_violation_rows_type_an_import_violation(tmp_path: Path) -> None:
    """A dependency violation names its modules, its symbol and both components, typed."""
    rows = load_violations(_tour_report(tmp_path))

    row = next(row for row in rows if row.fingerprint.rules == ("DEP-STORE-NO-MONEY",))

    assert row.source_module == "shop.store.repository"
    assert row.target_module == "shop.model.entities"
    assert row.symbol == "Money"
    assert row.source_component == "store"
    assert row.target_component == "model"


def test_violation_rows_leave_construct_fields_none(tmp_path: Path) -> None:
    """A construct violation crosses no import, so its import fields stay None, not guessed."""
    rows = load_violations(_tour_report(tmp_path))

    row = next(row for row in rows if row.fingerprint.rules == ("CONSTRUCT-NO-ASSERT",))

    assert row.source_module is None
    assert row.target_module is None
    assert row.symbol is None
    assert row.source_component is None
    assert row.target_component is None


def test_violation_rows_fingerprints_agree_with_ir_baseline(tmp_path: Path) -> None:
    """AD-52: a row's fingerprint is exactly what `ir.baseline` derives, counted the same way."""
    report_path = _tour_report(tmp_path)
    observation = parse_observation(decode_canonical_model(json.loads(report_path.read_text())))

    counted: dict[ViolationFingerprint, int] = {}
    for row in load_violations(report_path):
        counted[row.fingerprint] = counted.get(row.fingerprint, 0) + 1

    assert counted == {item.fingerprint: item.count for item in observed_violations(observation)}


def test_reference_md_snippet_reads_a_report_and_lists_its_rows(tmp_path: Path) -> None:
    """The docs/reference.md snippet, kept in lockstep with this test by hand: one call."""
    report_path = _tour_report(tmp_path)

    # --- docs/reference.md snippet begins ---
    from archkeel.api import load_violations

    rows = [
        (row.fingerprint, row.source_component, row.target_component)
        for row in load_violations(report_path)
    ]
    # --- docs/reference.md snippet ends ---

    assert len(rows) == 20
    assert all(isinstance(fingerprint, ViolationFingerprint) for fingerprint, _, _ in rows)


def test_api_all_matches_the_names_reference_md_documents() -> None:
    """AD-66: the module and docs must both match the contract's external API declaration."""
    import archkeel.api as api

    contract = parse_contract(json.loads((ROOT / "architecture-contract.json").read_text()))
    declared_names = {
        module.partition(":")[2]
        for module in contract.declarations.public_api
        if module.partition(":")[0] == "archkeel.api"
    }
    reference = (ROOT / "docs/reference.md").read_text()
    marker = "<!-- archkeel-public-api -->"
    assert reference.count(marker) == 1
    documented = reference.partition(marker)[2]
    fence = "```json\n"
    assert documented.count(fence) == 1
    json_block, closing, _ = documented.partition(fence)[2].partition("\n```")
    assert closing
    documented_entries = json.loads(json_block)
    assert isinstance(documented_entries, list)
    assert all(isinstance(entry, str) for entry in documented_entries)
    reference_md_names = set(documented_entries)

    assert set(contract.declarations.public_api) == reference_md_names
    assert declared_names == {entry.rpartition(":")[2] for entry in reference_md_names}
    assert set(api.__all__) == declared_names
    assert api.ViolationRow is ViolationRow
    # The promise includes the type row.fingerprint hands out, or it is undeclared (AD-70).
    assert ApiViolationFingerprint is ViolationFingerprint
    assert api.load_violations is load_violations


def test_old_ir_codec_import_path_is_gone() -> None:
    """AD-64: `ir.codec.load_observation` (AD-54) is removed, not deprecated - the surface was
    days old at 0.4.x, so the facade replaces it outright instead of carrying two supported
    ways in."""
    import archkeel.ir.codec as codec

    assert not hasattr(codec, "load_observation")


def test_ir_codec_no_longer_reads_a_file(tmp_path: Path) -> None:
    """AD-64: `ir` performs no I/O (AD-17); decoding a report is `decode_json` plus already
    read bytes, never a `Path` `ir.codec` opens itself."""
    from archkeel.ir.codec import decode_canonical_model, decode_json, parse_observation

    report_path = _tour_report(tmp_path)
    raw = decode_json(report_path.read_bytes())
    assert isinstance(raw, dict)
    observation = parse_observation(decode_canonical_model(raw))
    assert observation.schema_version == "1.3.0"


def test_load_violations_rejects_a_violation_with_no_rule_ids(tmp_path: Path) -> None:
    """A hand-edited or truncated file must fail loudly, not with an `IndexError` from a count.

    `schema/architecture-ir-common.schema.json` promises `minItems: 1` on a VIOLATION record's
    `rule_ids`, but nothing enforced that at runtime before this: `load_violations` reads an
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
        load_violations(report_path)
