# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Native call proofs stay valid for the exact syntax and binding they certify."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_exact_module_ownership import _component, _observe_tree, _rule

from archkeel.check.report import run_saved_report
from archkeel.ir.codec import canonical_report_bytes, observation_payload
from archkeel.ir.decisions import rule_assessments

_STORAGE = "sample.storage.Storage.page"
_STORAGE_SOURCE = "class Storage:\n    def page(self): pass\n"


def _observe_call(tmp_path: Path, caller: str, *, target: str, mounted: bool):
    contract = {
        "schema_version": "3.7.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "call_owner",
                source="sample",
                target=target,
                allowed_sources=[],
                exact_sources=[],
            )
        ],
    }
    files = {
        "sample/__init__.py": "",
        "sample/storage.py": _STORAGE_SOURCE,
        "sample/caller.py": caller,
    }
    if mounted:
        files["inside.json"] = json.dumps(contract)
        contract = {
            "schema_version": "3.7.0",
            "components": [_component("all", ["sample"], inside="inside.json")],
            "rules": [],
        }
    result = _observe_tree(tmp_path, files, contract)
    if result.observation is None:
        return result, None
    [row] = [
        row
        for row in rule_assessments(result.observation, undecided_by_rule={})
        if row.kind == "call_owner"
    ]
    return result, row


def _assert_saved_replay(tmp_path: Path, result, row, *, columnar: bool) -> None:
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    report = tmp_path / "architecture.json"
    report.write_bytes(saved)
    [replayed] = run_saved_report(report).rule_assessments
    assert replayed.status == row.status
    assert replayed.evaluation_proven == row.evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    "caller,target,expression",
    [
        (
            "from .storage import Storage\ndef run():\n    x = Storage()\n    (x.page)()\n",
            _STORAGE,
            "x.page",
        ),
        (
            "from .storage import Storage\nclass Holder:\n"
            "    def __init__(self, client: Storage): self.client = client\n"
            "    def run(self): (self.client.page)()\n",
            _STORAGE,
            "self.client.page",
        ),
        (
            "import random\ndef run(): (random.random)()\n",
            "random.random",
            "random.random",
        ),
        (
            'import random\ndef run():\n    globals()["random"] = fake\n    random.random()\n',
            "random.random",
            "random.random",
        ),
    ],
    ids=[
        "parenthesized-constructed",
        "parenthesized-stored",
        "parenthesized-native-import",
        "globals-rebinding",
    ],
)
def test_unsupported_native_call_proofs_are_unknown_and_replay(
    tmp_path, caller, target, expression, mounted, columnar
):
    result, row = _observe_call(tmp_path, caller, target=target, mounted=mounted)

    assert result.observation is not None, result.diagnostics
    assert not result.diagnostics
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    focus = [
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == expression
    ]
    assert len(focus) == 1
    assert focus[0].data.get("call_binding") is None
    _assert_saved_replay(tmp_path, result, row, columnar=columnar)


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    "caller,target,expression",
    [
        (
            "from .storage import Storage\ndef run():\n    x = Storage()\n    x.page()\n",
            _STORAGE,
            "x.page",
        ),
        (
            "import random\ndef run(): random.random()\n",
            "random.random",
            "random.random",
        ),
    ],
    ids=["constructed-receiver", "stable-native-import"],
)
def test_supported_native_call_proofs_keep_policy_results_and_replay(
    tmp_path, caller, target, expression, mounted, columnar
):
    result, row = _observe_call(tmp_path, caller, target=target, mounted=mounted)

    assert result.observation is not None, result.diagnostics
    assert not result.diagnostics
    assert row.status == "FAIL" and row.evaluation_proven
    focus = [
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == expression
    ]
    assert len(focus) == 1
    assert focus[0].data.get("call_binding") is not None
    _assert_saved_replay(tmp_path, result, row, columnar=columnar)
