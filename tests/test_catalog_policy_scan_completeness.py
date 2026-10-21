# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Catalog receipts require complete physical coverage of their source selector."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_exact_module_ownership import _component, _observe_tree, _rule

from archkeel.check.report import run_saved_report
from archkeel.ir.codec import encode_canonical_model, observation_payload
from archkeel.ir.decisions import rule_assessments, unknown_positions_by_rule


def _catalog_rule(source: str, *, match: str = "prefix") -> dict[str, object]:
    return _rule(
        "catalog_argument",
        source=source,
        source_match=match,
        target="sample.safe.catalog.read_option",
        parameter="key",
        catalog="sample.safe.catalog.OptionKey",
    )


def _contract(*, mounted: bool, source: str, match: str) -> dict[str, object]:
    rule = _catalog_rule(source, match=match)
    if not mounted:
        return {"schema_version": "3.14.0", "components": [], "rules": [rule]}
    inside = {
        "schema_version": "3.14.0",
        "components": [_component("inside", ["sample"])],
        "rules": [rule],
    }
    return {
        "schema_version": "3.14.0",
        "components": [_component("all", ["sample"], inside="inside.json")],
        "rules": [],
        "_inside": inside,
    }


def _observe(
    tmp_path: Path,
    *,
    roots: tuple[str, ...],
    mounted: bool,
    bad_visible: bool,
    source: str = "sample",
    match: str = "prefix",
    bad_hidden: bool = True,
):
    contract = _contract(mounted=mounted, source=source, match=match)
    visible_actual = '"unknown"' if bad_visible else "OptionKey.PAGE_SIZE"
    hidden_actual = "'unknown'" if bad_hidden else "'page_size'"
    files = {
        "sample/__init__.py": "",
        "sample/safe/__init__.py": "",
        "sample/safe/catalog.py": (
            "from enum import StrEnum\n"
            "class OptionKey(StrEnum):\n"
            "    PAGE_SIZE = 'page_size'\n"
            "def read_option(key: str) -> None: pass\n"
        ),
        "sample/safe/consumer.py": (
            "from .catalog import OptionKey, read_option\n"
            "def consume():\n"
            f"    read_option({visible_actual})\n"
            "class Worker:\n"
            "    def consume(self): read_option(OptionKey.PAGE_SIZE)\n"
        ),
        "sample/core.py": (
            f"from .safe.catalog import read_option\ndef hidden(): read_option({hidden_actual})\n"
        ),
    }
    inside = contract.pop("_inside", None)
    if inside is not None:
        files["inside.json"] = json.dumps(inside)
    return _observe_tree(tmp_path, files, contract, roots=roots)


def _assessment(observation):
    rows = rule_assessments(observation, undecided_by_rule=unknown_positions_by_rule(observation))
    [row] = [item for item in rows if item.kind == "catalog_argument"]
    return row


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize("bad_visible", [False, True])
def test_broad_partial_catalog_source_cannot_prove_pass(
    tmp_path: Path, mounted: bool, columnar: bool, bad_visible: bool
):
    result = _observe(
        tmp_path,
        roots=("sample/safe",),
        mounted=mounted,
        bad_visible=bad_visible,
    )
    assert result.observation is not None, result.diagnostics
    row = _assessment(result.observation)
    assert row.status == ("FAIL" if bad_visible else "UNKNOWN")
    assert not row.evaluation_proven
    if bad_visible:
        assert row.count == 1 and row.undecided > 0
        assert any(
            item.kind == "catalog_argument"
            for item in result.observation.records("violations") or ()
        )
    assert any(
        item.kind == "catalog_limit" for item in result.observation.records("unknowns") or ()
    )
    assert not any(
        item.kind == "rule_evaluation" and "CATALOG-0" in item.rule_ids
        for item in result.observation.records("scope_observations") or ()
    )

    raw = observation_payload(result.observation)
    encoded = encode_canonical_model(raw) if columnar else raw
    saved = tmp_path / "partial-catalog.json"
    saved.write_text(json.dumps(encoded))
    [replayed] = run_saved_report(saved).rule_assessments
    assert (replayed.status, replayed.count, replayed.evaluation_proven) == (
        row.status,
        row.count,
        row.evaluation_proven,
    )


@pytest.mark.parametrize("mounted", [False, True])
def test_fully_covered_narrow_catalog_source_keeps_pass(tmp_path: Path, mounted: bool):
    result = _observe(
        tmp_path,
        roots=("sample/safe",),
        mounted=mounted,
        bad_visible=False,
        source="sample.safe",
    )
    assert result.observation is not None, result.diagnostics
    row = _assessment(result.observation)
    assert row.status == "PASS" and row.evaluation_proven


@pytest.mark.parametrize(
    ("source", "match"),
    [
        ("sample.safe.consumer.consume", "prefix"),
        ("sample.safe.consumer.consume", "exact"),
        ("sample.safe.consumer.Worker", "prefix"),
    ],
)
def test_function_or_class_selector_uses_its_covered_module(
    tmp_path: Path, source: str, match: str
):
    result = _observe(
        tmp_path,
        roots=("sample/safe",),
        mounted=False,
        bad_visible=False,
        source=source,
        match=match,
    )
    assert result.observation is not None, result.diagnostics
    row = _assessment(result.observation)
    assert row.status == "PASS" and row.evaluation_proven


def test_complete_root_catalog_source_proves_pass(tmp_path: Path):
    result = _observe(
        tmp_path,
        roots=("sample",),
        mounted=False,
        bad_visible=False,
        bad_hidden=False,
    )
    assert result.observation is not None, result.diagnostics
    row = _assessment(result.observation)
    assert row.status == "PASS" and row.evaluation_proven
