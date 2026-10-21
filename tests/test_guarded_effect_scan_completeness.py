# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Guarded-effect receipts require full coverage of their selected source domain."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_exact_module_ownership import _component, _observe_tree, _rule

from archkeel.check.report import run_saved_report
from archkeel.ir.codec import encode_canonical_model, observation_payload
from archkeel.ir.decisions import rule_assessments


def _guard_rule(source: str) -> dict[str, object]:
    return _rule(
        "forbidden_effect_under_condition",
        id="NO-EFFECT-WHEN-SEEDED",
        source=source,
        target="sample.safe.core._effect",
        condition={"kind": "parameter", "owner": "sample.safe.core.generate", "name": "seeded"},
    )


def _contract(*, mounted: bool, source: str) -> dict[str, object]:
    rule = _guard_rule(source)
    inside = {
        "schema_version": "3.13.0",
        "components": [_component("inside", ["sample"])],
        "rules": [rule],
    }
    if not mounted:
        return {
            "schema_version": "3.13.0",
            "components": [_component("all", ["sample"])],
            "rules": [rule],
        }
    return {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"], inside="inside.json")],
        "rules": [],
        "_inside": inside,
    }


def _observe(
    tmp_path: Path,
    *,
    roots: tuple[str, ...],
    mounted: bool,
    source: str,
    violating: bool,
):
    contract = _contract(mounted=mounted, source=source)
    branch = "if seeded" if violating else "if not seeded"
    files = {
        "sample/__init__.py": "",
        "sample/safe/__init__.py": "",
        "sample/safe/core.py": f"""def _effect():
    return None

def generate(seeded: bool):
    {branch}:
        _effect()
""",
        "sample/core.py": """from .safe.core import _effect

def hidden(seeded: bool):
    if seeded:
        _effect()
""",
    }
    inside = contract.pop("_inside", None)
    if inside is not None:
        files["inside.json"] = json.dumps(inside)
    return _observe_tree(tmp_path, files, contract, roots=roots)


def _assessment(observation):
    [row] = [
        item
        for item in rule_assessments(observation, undecided_by_rule={})
        if item.kind == "forbidden_effect_under_condition"
    ]
    return row


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize("violating", [False, True])
def test_omitted_sibling_keeps_guarded_effect_unknown_and_known_failure(
    tmp_path: Path, mounted: bool, columnar: bool, violating: bool
) -> None:
    result = _observe(
        tmp_path,
        roots=("sample/safe",),
        mounted=mounted,
        source="sample",
        violating=violating,
    )
    assert result.observation is not None, result.diagnostics
    row = _assessment(result.observation)
    assert row.status == ("FAIL" if violating else "UNKNOWN")
    assert not row.evaluation_proven
    assert row.count == (1 if violating else 0)
    assert any(
        item.kind == "guarded_effect_limit" for item in result.observation.records("unknowns")
    )

    payload = observation_payload(result.observation)
    encoded = encode_canonical_model(payload) if columnar else payload
    saved = tmp_path / "guarded-partial-report.json"
    saved.write_text(json.dumps(encoded))
    [replayed] = run_saved_report(saved).rule_assessments
    assert (replayed.status, replayed.count, replayed.evaluation_proven) == (
        row.status,
        row.count,
        row.evaluation_proven,
    )


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_narrow_guarded_effect_source_can_pass_inside_partial_scan(
    tmp_path: Path, mounted: bool, columnar: bool
) -> None:
    result = _observe(
        tmp_path,
        roots=("sample/safe",),
        mounted=mounted,
        source="sample.safe",
        violating=False,
    )
    assert result.observation is not None, result.diagnostics
    row = _assessment(result.observation)
    assert row.status == "PASS" and row.count == 0 and row.evaluation_proven
    assert not any(
        item.kind == "guarded_effect_limit" for item in result.observation.records("unknowns")
    )

    payload = observation_payload(result.observation)
    encoded = encode_canonical_model(payload) if columnar else payload
    saved = tmp_path / "guarded-narrow-report.json"
    saved.write_text(json.dumps(encoded))
    [replayed] = run_saved_report(saved).rule_assessments
    assert (replayed.status, replayed.count, replayed.evaluation_proven) == (
        "PASS",
        0,
        True,
    )
