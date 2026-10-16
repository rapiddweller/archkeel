# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Native import facts must prove the exact required port, including uncertainty."""

import json

import pytest
from test_analyzer import _component
from test_architecture_demo import _prepare_repo

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import RequiredComponent, requires_covers

RULE = {
    "id": "REQUIRES",
    "kind": "complete_requires",
    "rationale": "Only the requested import ports may be used.",
    "provenance": ["docs/architecture/sample.md"],
    "decided_by": "architect",
}


def _report(tmp_path, statement, *, through=("sample.core:Command",), exports=None):
    caller = _component("caller")
    caller["requires"] = [
        {"component": "core", "through": list(through), "rationale": "Use this API."}
    ]
    core = _component("core", packages=["sample.core", "sample.other"])
    source = "class Command:\n    pass\n\nclass Other:\n    pass\n"
    if exports is not None:
        source += "__all__ = " + repr(exports) + "\n"
    contract = {"schema_version": "2.2.0", "components": [caller, core], "rules": [RULE]}
    root = _prepare_repo(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/caller.py": statement + "\n",
            "sample/core.py": source,
            "sample/other.py": "class Command:\n    pass\n",
            "contract.json": json.dumps(contract),
            "docs/architecture/sample.md": "Exact API responsibilities.\n",
        },
    )
    config = ScanConfig(("sample",), "sample", "contract.json", "0" * 64)
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None, result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    rows = [row for row in result.rule_assessments or () if row.id == RULE["id"]]
    assert len(rows) == 1, result.rule_assessments
    return root, rows[0], model


@pytest.mark.parametrize(
    ("statement", "through", "expected"),
    [
        ("from sample.core import Command", ("sample.core:Command",), "PASS"),
        ("from sample.core import Command as Selected", ("sample.core:Command",), "PASS"),
        ("from sample.core import Other", ("sample.core:Command",), "FAIL"),
        ("from sample.other import Command", ("sample.core:Command",), "FAIL"),
        ("from sample.core import Other", ("sample.core",), "PASS"),
        ("from sample.other import Command", (), "PASS"),
    ],
)
def test_actual_named_import_port_is_exact_and_legacy_module_permissions_stay(
    tmp_path, statement, through, expected
):
    _, row, model = _report(tmp_path, statement, through=through)
    assert row.status == expected
    violations = [item for item in model.records("violations") or () if RULE["id"] in item.rule_ids]
    assert bool(violations) is (expected == "FAIL")
    imports = [item for item in model.records("imports") or () if item.data.get("source_module") == "sample.caller"]
    assert imports and all(item.data.get("symbols_known") is True for item in imports)


def test_source_mutation_to_sibling_cannot_borrow_approved_command_port(tmp_path):
    root, row, _ = _report(tmp_path, "from sample.core import Command")
    assert row.status == "PASS"
    intent = (root / "contract.json").read_bytes()
    (root / "sample/caller.py").write_text("from sample.core import Other\n")
    result, _ = run_report(
        root, config=ScanConfig(("sample",), "sample", "contract.json", "0" * 64), analyzer=observe
    )
    assert next(item for item in result.rule_assessments if item.id == RULE["id"]).status == "FAIL"
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize(
    "exports",
    [None, ["Command"], ["Command", "Other"]],
)
def test_unexpanded_wildcard_cannot_invent_name_proof_from_export_list(tmp_path, exports):
    _, row, model = _report(tmp_path, "from sample.core import *", exports=exports)
    imports = [item for item in model.records("imports") or () if item.data.get("source_module") == "sample.caller"]
    assert imports and all(item.data.get("symbols_known") is True for item in imports)
    assert {item.data.get("symbol") for item in imports} == {"*"}
    assert {item.data.get("target_module") for item in imports} == {"sample.core"}
    assert row.status == "UNKNOWN"
    limits = [item for item in model.records("unknowns") or () if RULE["id"] in item.rule_ids]
    assert limits


def test_unknown_wildcard_from_other_module_is_still_decisively_forbidden(tmp_path):
    _, row, _ = _report(tmp_path, "from sample.other import *")
    assert row.status == "FAIL"


def test_existing_requires_query_remains_compatible_and_symbol_query_is_precise():
    entries = (RequiredComponent("core", "Use one port.", ("sample.core:Command",)),)
    assert requires_covers(entries, "core")
    assert requires_covers(entries, "core", "sample.core", "Command")
    assert not requires_covers(entries, "core", "sample.core", "Other")
    assert not requires_covers(entries, "core", "sample.core")
    legacy = (RequiredComponent("core", "Use module.", ("sample.core",)),)
    assert requires_covers(legacy, "core", "sample.core.child")
    assert requires_covers(legacy, "core", "sample.core", "Other")
