# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Native import facts must prove the exact required port, including uncertainty."""

import copy
import json
from pathlib import Path

import pytest
from test_analyzer import _component
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import RequiredComponent, requires_covers

ROOT = Path(__file__).parents[1]

RULE = {
    "id": "REQUIRES",
    "kind": "complete_requires",
    "rationale": "Only the requested import ports may be used.",
    "provenance": ["docs/architecture/sample.md"],
    "decided_by": "architect",
}


def _report(tmp_path, statement, *, through=("sample.core:Command",), exports=None, mounted=False):
    caller = _component("caller")
    caller["requires"] = [
        {"component": "core", "through": list(through), "rationale": "Use this API."}
    ]
    core = _component("core", packages=["sample.core", "sample.other"])
    source = "class Command:\n    pass\n\nclass Other:\n    pass\n"
    if exports is not None:
        source += "__all__ = " + repr(exports) + "\n"
    contract = {"schema_version": "2.2.0", "components": [caller, core], "rules": [RULE]}
    outer = {
        "schema_version": "2.2.0",
        "components": [{**_component("app", packages=["sample"]), "inside": "inside.json"}],
        "rules": [],
    }
    root = _prepare_repo(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/caller.py": statement + "\n",
            "sample/core.py": source,
            "sample/other.py": "class Command:\n    pass\n",
            "contract.json": json.dumps(outer if mounted else contract),
            "inside.json": json.dumps(contract),
            "docs/architecture/sample.md": "Exact API responsibilities.\n",
        },
    )
    config = ScanConfig(("sample",), "sample", "contract.json", "0" * 64)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None, result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    identity = "app:" + RULE["id"] if mounted else RULE["id"]
    rows = [row for row in result.rule_assessments or () if row.id == identity]
    assert len(rows) == 1, result.rule_assessments
    return root, rows[0], model


def test_existing_requires_query_remains_compatible_and_symbol_query_is_precise():
    entries = (RequiredComponent("core", "Use one port.", ("sample.core:Command",)),)
    assert requires_covers(entries, "core")
    assert requires_covers(entries, "core", "sample.core", "Command")
    assert not requires_covers(entries, "core", "sample.core", "Other")
    assert not requires_covers(entries, "core", "sample.core.child", "Command")
    assert not requires_covers(entries, "core", "sample.core")
    legacy = (RequiredComponent("core", "Use module.", ("sample.core",)),)
    assert requires_covers(legacy, "core", "sample.core.child")
    assert requires_covers(legacy, "core", "sample.core", "Other")


def _api_repository(tmp_path):
    intent = copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text()))
    intent.pop("$schema", None)
    intent["declarations"]["uml"]["entities"] = [
        row
        for row in intent["declarations"]["uml"]["entities"]
        if row["id"].startswith("IR-REQUIRES-")
        or row["id"] in {"IR-DEPENDENCY-model", "IR-DEPENDENCY-dependency"}
    ]
    intent["declarations"]["uml"]["relationships"] = []
    intent["declarations"]["uml"]["scopes"] = []
    intent["rules"] = [
        {
            "id": "REQUIRES-SELECTED-CONTROL",
            "kind": "forbidden_construct",
            "source": "archkeel.ir",
            "constructs": ["string_literal_compare"],
            "rationale": "Protect the actual selected matcher and marker in this fixture.",
            "provenance": ["docs/architecture/symbol-requires-ports.md"],
            "decided_by": "architect",
        }
    ]
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/ir/dependency.py": (ROOT / "src/archkeel/ir/dependency.py").read_text(),
        "archkeel/ir/facts.py": _source_members("src/archkeel/ir/facts.py", {"in_scope"}),
        "archkeel/ir/architecture_graph.py": "from enum import StrEnum\n"
        + _source_members("src/archkeel/ir/architecture_graph.py", {"AssessmentStatus"}),
        "archkeel/ir/model.py": (
            "from __future__ import annotations\nimport builtins\n"
            "from dataclasses import dataclass\n"
            "from .dependency import ImportSymbolMarker as _ImportSymbolMarker\n"
            "from .facts import in_scope\n"
            "from .architecture_graph import AssessmentStatus as AssessmentStatus\n"
            + _source_members(
                "src/archkeel/ir/model.py",
                {
                    "RequiredComponent",
                    "ContractComponent",
                    "requires_covers",
                    "_required_port_assessment",
                    "requires_import_assessment",
                },
            )
        ),
        "contract.json": json.dumps(intent),
        "docs/architecture/symbol-requires-ports.md": "Exact required API intent.\n",
    }
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_required_symbol_port_uses_wire_text_even_for_overridden_string_partition():
    from archkeel.ir.codec import parse_required_component

    class MisleadingPort(str):
        def partition(self, separator):
            return ("sample.other", separator, "Other")

    port = MisleadingPort("sample.core:Command")
    raw = {"component": "core", "rationale": "Use exactly this wire port.", "through": [port]}
    entry = parse_required_component(raw)
    assert json.loads(json.dumps(raw))["through"] == ["sample.core:Command"]
    assert requires_covers((entry,), "core", "sample.core", "Command")
    assert not requires_covers((entry,), "core", "sample.other", "Other")


def test_legacy_module_only_import_records_need_no_symbol_fields():
    from archkeel.check.evaluation.rules import requires_violations
    from archkeel.ir.codec import parse_contract
    from archkeel.ir.facts import EvidenceClass
    from archkeel.ir.source_records import RawData, classified

    caller = _component("caller")
    caller["requires"] = [
        {"component": "core", "through": ["sample.core"], "rationale": "Use module."}
    ]
    raw = {"schema_version": "2.2.0", "components": [caller, _component("core")], "rules": [RULE]}
    data: RawData = {
        "source_module": "sample.caller",
        "target_module": "sample.core",
        "under_type_checking": False,
    }
    record = classified(
        item_id="LEGACY-IMPORT",
        evidence_class=EvidenceClass.FACT,
        area="dependencies",
        kind="import",
        title="Legacy module import",
        data=data,
    )
    assert record["data"] is data
    assert requires_violations([record], parse_contract(raw)) == []
    caller["requires"] = []
    [violation] = requires_violations([record], parse_contract(raw))
    assert violation["rule_ids"] == [RULE["id"]]


@pytest.mark.parametrize(
    ("descriptor", "exact_expected"),
    [
        ({"symbol": "Command", "symbols_known": True}, "PASS"),
        ({"symbol": "Command", "symbols_known": False}, "UNKNOWN"),
        ({"symbol": "Command", "symbols_known": None}, "UNKNOWN"),
        ({"symbol": "Command"}, "UNKNOWN"),
        ({"symbol": None, "symbols_known": True}, "FAIL"),
        ({"symbol": None, "symbols_known": False}, "UNKNOWN"),
        ({}, "UNKNOWN"),
    ],
)
@pytest.mark.parametrize("exact", [False, True])
def test_raw_data_ingress_preserves_boolean_null_and_missing_name_evidence(
    descriptor, exact_expected, exact
):
    from archkeel.check.evaluation.rules import requires_violations, symbol_limits
    from archkeel.ir.codec import parse_contract
    from archkeel.ir.facts import EvidenceClass
    from archkeel.ir.source_records import RawData, classified

    caller = _component("caller")
    caller["requires"] = [
        {
            "component": "core",
            "through": ["sample.core:Command" if exact else "sample.core"],
            "rationale": "Use this API.",
        }
    ]
    contract = parse_contract(
        {"schema_version": "2.2.0", "components": [caller, _component("core")], "rules": [RULE]}
    )
    data: RawData = {
        "source_module": "sample.caller",
        "target_module": "sample.core",
        "under_type_checking": False,
        "reexport": False,
        **descriptor,
    }
    record = classified(
        item_id="RAW-IMPORT",
        evidence_class=EvidenceClass.FACT,
        area="dependencies",
        kind="import",
        title="Direct raw import builder",
        data=data,
    )
    assert record["data"] is data
    expected = exact_expected if exact else "PASS"
    assert bool(requires_violations([record], contract)) is (expected == "FAIL")
    assert bool(symbol_limits([record], contract, {})) is (expected == "UNKNOWN")


@pytest.mark.parametrize(("symbol", "expected"), [("Command", "PASS"), ("Other", "FAIL")])
def test_raw_dictionary_subclass_cannot_spoof_the_stored_import_name(symbol, expected):
    from archkeel.check.evaluation.rules import requires_violations, symbol_limits
    from archkeel.ir.codec import parse_contract
    from archkeel.ir.facts import EvidenceClass
    from archkeel.ir.source_records import RawData, classified

    class MisleadingData(dict):
        def get(self, key, default=None):
            return None

    caller = _component("caller")
    caller["requires"] = [
        {"component": "core", "through": ["sample.core:Command"], "rationale": "Use this API."}
    ]
    contract = parse_contract(
        {"schema_version": "2.2.0", "components": [caller, _component("core")], "rules": [RULE]}
    )
    data: RawData = MisleadingData(
        source_module="sample.caller",
        target_module="sample.core",
        under_type_checking=False,
        reexport=False,
        symbol=symbol,
        symbols_known=True,
    )
    record = classified(
        item_id="RAW-SUBCLASS-IMPORT",
        evidence_class=EvidenceClass.FACT,
        area="dependencies",
        kind="import",
        title="Actual stored dictionary fields",
        data=data,
    )
    assert record["data"] is data
    assert json.loads(json.dumps(data))["symbol"] == symbol
    assert bool(requires_violations([record], contract)) is (expected == "FAIL")
    assert not symbol_limits([record], contract, {})
