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
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import RequiredComponent, requires_covers
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

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
    imports = [
        item
        for item in model.records("imports") or ()
        if item.data.get("source_module") == "sample.caller"
    ]
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
    imports = [
        item
        for item in model.records("imports") or ()
        if item.data.get("source_module") == "sample.caller"
    ]
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
            "from __future__ import annotations\nfrom dataclasses import dataclass\n"
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


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("target_symbol: str | None = None", "target_symbol: object = None"),
        (") -> AssessmentStatus:", ") -> str:"),
        ("class ImportSymbolMarker(StrEnum):", "class ImportSymbolMarker(str):"),
    ],
)
def test_native_requires_api_is_independent_and_rejects_source_widening(tmp_path, old, new):
    root, config = _api_repository(tmp_path)
    value = _model(root, config)
    comparison = architecture_report(value).comparison
    assert comparison.status == "PASS", [
        (row.aspect, row.status, row.reason, row.subject_id)
        for row in comparison.assessments
        if row.status != "PASS"
    ]
    assert not trace_valid_violations(value)
    source = root / (
        "archkeel/ir/dependency.py" if old.startswith("class") else "archkeel/ir/model.py"
    )
    original = source.read_text()
    assert old in original
    intent = (root / "contract.json").read_bytes()
    source.write_text(original.replace(old, new, 1))
    changed = _model(root, config)
    assert any(row.status == "FAIL" for row in architecture_report(changed).comparison.assessments)
    assert trace_valid_violations(changed)
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("from sample.core import Command", "PASS"),
        ("from sample.core import Other", "FAIL"),
        ("from sample.core import *", "UNKNOWN"),
    ],
)
def test_exact_port_assessments_survive_nested_scope_and_saved_replay(
    tmp_path, mounted, statement, expected
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes

    _, row, model = _report(tmp_path, statement, mounted=mounted)
    assert row.status == expected
    saved = tmp_path / "saved.json"
    saved.write_bytes(canonical_report_bytes(model))
    replay = run_saved_report(saved)
    assert next(item for item in replay.rule_assessments if item.id == row.id).status == expected


@pytest.mark.parametrize(
    "probe",
    [
        'def _probe(symbol):\n    return symbol == "*"\n',
        'def _probe(symbol):\n    return symbol in ("*",)\n',
        'def _probe(symbol):\n    match symbol:\n        case "*":\n'
        "            return True\n        case _:\n            return False\n",
        'from typing import Final\nSTAR: Final[str] = "*"\n'
        "def _probe(symbol):\n    return symbol == STAR\n",
    ],
)
def test_native_selected_requires_code_rejects_raw_wildcard_dispatch(tmp_path, probe):
    root, config = _api_repository(tmp_path)
    assert not trace_valid_violations(_model(root, config))
    source = root / "archkeel/ir/model.py"
    source.write_text(source.read_text() + "\n" + probe)
    value = _model(root, config)
    assert any("REQUIRES-SELECTED-CONTROL" in row.rule_ids for row in trace_valid_violations(value))
