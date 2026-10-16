# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Native evidence checks actual collector declarations and codec control flow."""

import json
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
MODULES = ("facts", "protocol", "facts_codec", "type_shapes", "codec_observation")
GUARD = "COLLECTOR-TYPED-CONTROL"


def _collector_contract(module):
    intent = {"presence": "planned", "language": "python", "provenance": ["docs/target.md"]}
    return {
        "schema_version": "3.5.0",
        "components": [{
            "id": "ir", "label": "ir", "role": "component", "packages": ["archkeel.ir"],
            "responsibilities": ["Own immutable source facts and validated collector envelopes."],
            "forbidden_responsibilities": [], "provenance": ["docs/target.md"],
        }],
        "rules": [{
            "id": GUARD, "kind": "forbidden_construct",
            "source": f"archkeel.ir.{module}", "constructs": ["string_literal_compare"],
            "rationale": "Closed collector wire vocabulary is typed before control flow.",
            "decided_by": "architect", "provenance": ["docs/target.md"],
        }],
        "declarations": {"uml": {"schema_version": "1.0.0", "entities": [
            {**intent, "id": "module", "kind": "module", "qualified_name": "archkeel.ir.protocol",
             "parent_id": "ir", "responsibilities": ["Own source-only process envelope versions."]},
            {**intent, "id": "request", "kind": "class",
             "qualified_name": "archkeel.ir.protocol.CollectionRequest", "parent_id": "module",
             "responsibilities": ["Carry source inputs under a typed protocol version."]},
            {**intent, "id": "version", "kind": "attribute",
             "qualified_name": "archkeel.ir.protocol.CollectionRequest.protocol_version",
             "parent_id": "request", "annotation": "ProtocolVersion",
             "visibility": {"kind": "public", "basis": "declared"}},
        ], "relationships": [], "scopes": []}},
    }


def _collector_repository(tmp_path, module="facts_codec", probe="", *, weaken_version=False):
    files = {"archkeel/__init__.py": "", "archkeel/ir/__init__.py": ""}
    for name in (*MODULES, "state_facts"):
        text = (ROOT / f"src/archkeel/ir/{name}.py").read_text()
        if name == module:
            text += "\n" + probe
        if name == "protocol" and weaken_version:
            text = text.replace("protocol_version: ProtocolVersion", "protocol_version: str")
        files[f"archkeel/ir/{name}.py"] = text
    files["contract.json"] = json.dumps(_collector_contract(module))
    files["docs/target.md"] = "Collector wire vocabulary and protocol version are typed intent.\n"
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _guard(model):
    return next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == GUARD)


@pytest.mark.parametrize("module", MODULES)
def test_native_collector_codec_uses_no_raw_string_control(tmp_path, module):
    root, config = _collector_repository(tmp_path, module)
    model = _model(root, config)
    assert _guard(model).status == "PASS" and _guard(model).evaluation_proven
    assert not [row for row in trace_valid_violations(model) if GUARD in row.rule_ids]


@pytest.mark.parametrize("probe", [
    'def _control(value):\n    return value == "local"\n',
    'def _control(value):\n    return value in ("local", "external")\n',
    'def _control(value):\n    match value:\n        case "local":\n            return True\n',
    'from typing import Final\nLOCAL: Final[str] = "local"\n'
    'def _control(value):\n    return value == LOCAL\n',
], ids=["equality", "membership", "match", "final-alias"])
def test_native_collector_guard_rejects_actual_source_mutations(tmp_path, probe):
    root, config = _collector_repository(tmp_path, probe=probe)
    before = (root / "contract.json").read_bytes()
    model = _model(root, config)
    assert _guard(model).status == "FAIL"
    assert any(GUARD in row.rule_ids for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == before


def test_native_protocol_version_type_weakening_fails_fixed_authored_target(tmp_path):
    root, config = _collector_repository(tmp_path, module="protocol", weaken_version=True)
    before = (root / "contract.json").read_bytes()
    model = _model(root, config)
    assert any(
        row.kind == "uml_conformance" and row.data.get("aspect") == "annotation"
        for row in trace_valid_violations(model)
    )
    assert (root / "contract.json").read_bytes() == before
