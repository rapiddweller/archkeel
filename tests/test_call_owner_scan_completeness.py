# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Call-owner receipts require the selected source domain to be fully scanned."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_exact_module_ownership import _component, _observe_tree, _rule

from archkeel.check.report import run_saved_report
from archkeel.ir.codec import encode_canonical_model, observation_payload
from archkeel.ir.decisions import rule_assessments


def _contract(*, mounted: bool, source: str, allowed: tuple[str, ...]) -> dict[str, object]:
    rule = _rule(
        "call_owner",
        source=source,
        target="sample.safe.storage.Storage.page",
        allowed_sources=list(allowed),
        exact_sources=[],
    )
    inside = {
        "schema_version": "3.7.0",
        "components": [_component("inside", ["sample"])],
        "rules": [rule],
    }
    if not mounted:
        return {
            "schema_version": "3.7.0",
            "components": [_component("all", ["sample"])],
            "rules": [rule],
        }
    return {
        "schema_version": "3.7.0",
        "components": [_component("all", ["sample"], inside="inside.json")],
        "rules": [],
        "_inside": inside,
    }


def _observe(tmp_path: Path, *, roots: tuple[str, ...], mounted: bool, allowed: tuple[str, ...]):
    contract = _contract(mounted=mounted, source="sample", allowed=allowed)
    files = {
        "sample/__init__.py": "",
        "sample/safe/__init__.py": "",
        "sample/safe/storage.py": "class Storage:\n    def page(self): pass\n",
        "sample/safe/caller.py": ("from .storage import Storage\ndef run(): Storage().page()\n"),
        "sample/core.py": ("from .safe.storage import Storage\ndef hidden(): Storage().page()\n"),
    }
    inside = contract.pop("_inside", None)
    if inside is not None:
        files["inside.json"] = json.dumps(inside)
    return _observe_tree(
        tmp_path,
        files,
        contract,
        roots=roots,
    )


def _assessment(observation):
    [row] = [
        item
        for item in rule_assessments(observation, undecided_by_rule={})
        if item.kind == "call_owner"
    ]
    return row


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize("known_failure", [False, True])
def test_partial_source_scan_cannot_prove_call_owner_pass(
    tmp_path: Path, mounted: bool, columnar: bool, known_failure: bool
):
    allowed = () if known_failure else ("sample.safe.caller",)
    result = _observe(
        tmp_path,
        roots=("sample/safe",),
        mounted=mounted,
        allowed=allowed,
    )
    assert result.observation is not None, result.diagnostics
    row = _assessment(result.observation)
    assert row.status == ("FAIL" if known_failure else "UNKNOWN")
    assert row.evaluation_proven is False
    if known_failure:
        assert row.count == 1
        assert any(item.kind == "call_owner" for item in result.observation.records("violations"))
    else:
        assert row.count == 0
    assert any(item.kind == "call_owner_limit" for item in result.observation.records("unknowns"))

    payload = observation_payload(result.observation)
    encoded = encode_canonical_model(payload) if columnar else payload
    saved = tmp_path / "partial-report.json"
    saved.write_text(json.dumps(encoded))
    [replayed] = run_saved_report(saved).rule_assessments
    assert (replayed.status, replayed.count, replayed.evaluation_proven) == (
        row.status,
        row.count,
        row.evaluation_proven,
    )
    assert replayed.undecided > 0


@pytest.mark.parametrize("mounted", [False, True])
def test_complete_source_scan_proves_call_owner_pass(tmp_path: Path, mounted: bool):
    result = _observe(
        tmp_path,
        roots=("sample",),
        mounted=mounted,
        allowed=("sample.safe.caller", "sample.core"),
    )
    assert result.observation is not None, result.diagnostics
    row = _assessment(result.observation)
    assert row.status == "PASS" and row.evaluation_proven


def test_narrow_rule_source_can_be_complete_inside_partial_scan(tmp_path: Path):
    contract = _contract(mounted=False, source="sample.safe", allowed=("sample.safe.caller",))
    files = {
        "sample/__init__.py": "",
        "sample/safe/__init__.py": "",
        "sample/safe/storage.py": "class Storage:\n    def page(self): pass\n",
        "sample/safe/caller.py": "from .storage import Storage\ndef run(): Storage().page()\n",
        "sample/core.py": "from .safe.storage import Storage\ndef hidden(): Storage().page()\n",
    }
    result = _observe_tree(tmp_path, files, contract, roots=("sample/safe",))
    assert result.observation is not None, result.diagnostics
    row = _assessment(result.observation)
    assert row.status == "PASS" and row.evaluation_proven


def test_namespace_prefix_with_nested_physical_root_stays_incomplete(tmp_path: Path):
    files = {
        "src/sample/__init__.py": "",
        "src/sample/safe/__init__.py": "",
        "src/sample/safe/storage.py": "class Storage:\n    def page(self): pass\n",
        "src/sample/safe/caller.py": (
            "from .storage import Storage\ndef run(): Storage().page()\n"
        ),
        "src/sample/core.py": (
            "from .safe.storage import Storage\ndef hidden(): Storage().page()\n"
        ),
    }
    result = _observe_tree(
        tmp_path,
        files,
        {
            "schema_version": "3.7.0",
            "components": [_component("all", ["sample"])],
            "rules": [
                _rule(
                    "call_owner",
                    source="sample",
                    target="sample.safe.storage.Storage.page",
                    allowed_sources=["sample.safe.caller"],
                    exact_sources=[],
                )
            ],
        },
        roots=("src/sample/safe",),
    )
    assert result.observation is not None, result.diagnostics
    row = _assessment(result.observation)
    assert row.status == "UNKNOWN" and not row.evaluation_proven


def test_rule_source_is_checked_without_component_ownership(tmp_path: Path):
    result = _observe_tree(
        tmp_path,
        {
            "sample/safe/__init__.py": "",
            "sample/safe/storage.py": "class Storage:\n    def page(self): pass\n",
            "sample/safe/caller.py": (
                "from .storage import Storage\ndef run(): Storage().page()\n"
            ),
            "sample/core.py": "",
        },
        {
            "schema_version": "3.7.0",
            "components": [],
            "rules": [
                _rule(
                    "call_owner",
                    source="sample",
                    target="sample.safe.storage.Storage.page",
                    allowed_sources=["sample.safe.caller"],
                    exact_sources=[],
                )
            ],
        },
        roots=("sample/safe",),
    )
    assert result.observation is not None, result.diagnostics
    row = _assessment(result.observation)
    assert row.status == "UNKNOWN" and not row.evaluation_proven
