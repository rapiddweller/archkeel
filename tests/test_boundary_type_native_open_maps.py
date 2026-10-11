# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Explicit native payload decisions preserve every unselected contributor."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_analyzer import _observe
from test_boundary_type_opaque_map_values import _app

from archkeel.ir.codec import contract_bytes, parse_contract
from archkeel.ir.trace import trace_valid_violations
from archkeel.ir.widening import contract_widenings

Q = "sample.app.impl.read"
COMPOUND = "list[dict[str, str]] | list[JsonValue] | dict[str, JsonValue] | list[dict[str, object]]"
ARM = "list[dict[str, object]]"
ARM_SELECTOR = {
    "qualified_name": Q,
    "position": "return",
    "annotation": COMPOUND,
    "literal_mapping_arm": ARM,
}
DTO_SELECTOR = {
    "qualified_name": Q,
    "position": "return",
    "field_path": "rows",
    "annotation": "list[dict]",
    "native_mapping": True,
}
REGISTRY_SELECTOR = {
    "qualified_name": "sample.app.impl.Context.__init__",
    "position": "generators",
    "annotation": "dict | None",
    "native_mapping": True,
}


def fixture(root: Path, kind: str, selectors: list[dict], prefix: str = ""):
    sources = {
        "compound": (
            "JsonValue = str | list['JsonValue'] | dict[str, 'JsonValue']\n"
            f"def read() -> {COMPOUND}: pass\n",
            ("sample.app.impl:read",),
        ),
        "dto": (
            "class Rows:\n    rows: list[dict]\n    sibling: dict[str, int]\n"
            "    uncertain: Missing\ndef read() -> Rows | None: pass\n",
            ("sample.app.impl:Rows", "sample.app.impl:read"),
        ),
        "registry": (
            "class Context:\n    def __init__(self, generators: dict | None, "
            "control: dict[str, int], uncertain: Missing) -> None: pass\n",
            ("sample.app.impl:Context",),
        ),
    }
    source, declared = sources[kind]
    _app(root, source=prefix + source, declared=declared, allowances=tuple(selectors))
    p = root / "contract.json"
    raw = json.loads(p.read_text())
    raw["schema_version"] = "3.3.0"
    p.write_text(json.dumps(raw))
    result = _observe(root)
    assert result.observation is not None and not result.diagnostics
    return result.observation


@pytest.mark.parametrize("kind,selector", [("dto", DTO_SELECTOR), ("registry", REGISTRY_SELECTOR)])
def test_native_map_permission_selects_one_exact_bare_position(tmp_path, kind, selector):
    before = fixture(tmp_path, kind, [])
    after = fixture(tmp_path, kind, [selector])
    old = trace_valid_violations(before)
    new = trace_valid_violations(after)
    assert len(old) == 2 and len(new) == 1 and new[0] in old
    assert before.records("unknowns") == after.records("unknowns")
    facts = [r for r in after.records("typing_signals") if r.kind == "boundary_type_allowance"]
    assert len(facts) == 1 and facts[0].data.get("accepted_opacity") is True
    assert facts[0].data.get("native_mapping") is True
    assert facts[0].provenance == ("docs/architecture/sample.md",)
    for section in ("symbols", "calls", "imports", "bindings", "evidence"):
        assert before.records(section) == after.records(section)


@pytest.mark.parametrize("kind,selector", [("dto", DTO_SELECTOR), ("registry", REGISTRY_SELECTOR)])
@pytest.mark.parametrize(
    "change",
    [
        {"qualified_name": "sample.app.impl.other"},
        {"position": "control"},
        {"field_path": "missing"},
    ],
)
def test_native_map_inexact_selector_preserves_all_records(tmp_path, kind, selector, change):
    before = fixture(tmp_path, kind, [])
    after = fixture(tmp_path, kind, [{**selector, **change}])
    for section in ("violations", "unknowns", "typing_signals"):
        assert before.records(section) == after.records(section)


@pytest.mark.parametrize("kind,selector", [("dto", DTO_SELECTOR), ("registry", REGISTRY_SELECTOR)])
@pytest.mark.parametrize("prefix", ["from unavailable import dict\n", "dict = unknown\n"])
def test_unavailable_builtin_cannot_gain_native_permission(tmp_path, kind, selector, prefix):
    before = fixture(tmp_path, kind, [], prefix)
    after = fixture(tmp_path, kind, [selector], prefix)
    assert before.records("unknowns") == after.records("unknowns")
    assert not any(r.kind == "boundary_type_allowance" for r in after.records("typing_signals"))


def test_exact_literal_arm_object_leaf_keeps_recursive_unknown_and_other_findings(tmp_path):
    before = fixture(tmp_path, "compound", [ARM_SELECTOR])
    after = fixture(tmp_path, "compound", [ARM_SELECTOR, {**ARM_SELECTOR, "container_depth": 2}])
    old = trace_valid_violations(before)
    new = trace_valid_violations(after)
    assert len(old) == 3 and len(new) == 2
    assert all(r in old for r in new)
    assert [r.data.get("nested_annotation") for r in old if r not in new] == ["object"]
    assert before.records("unknowns") == after.records("unknowns")
    assert any(
        r.kind == "boundary_type_position"
        and r.data.get("qualified_name") == Q
        and r.data.get("position") == "return"
        and r.data.get("reason") == "other"
        for r in after.records("unknowns")
    )
    assert not any(r.data.get("nested_annotation") == "dict[str, 'JsonValue']" for r in old)
    facts = [r for r in after.records("typing_signals") if r.kind == "boundary_type_allowance"]
    assert len(facts) == 2
    leaf = next(r for r in facts if r.data.get("accepted_opacity"))
    assert leaf.data.get("literal_mapping_arm") == ARM
    assert leaf.data.get("observed_container_depth") == 2


@pytest.mark.parametrize(
    "change",
    [
        {"container_depth": 1},
        {"container_depth": 3},
        {"literal_mapping_arm": "list[dict[str, str]]"},
    ],
)
def test_wrong_literal_leaf_coordinates_keep_complete_records(tmp_path, change):
    before = fixture(tmp_path, "compound", [ARM_SELECTOR])
    after = fixture(
        tmp_path, "compound", [ARM_SELECTOR, {**ARM_SELECTOR, "container_depth": 2, **change}]
    )
    for section in ("violations", "unknowns", "typing_signals"):
        assert before.records(section) == after.records(section)


@pytest.mark.parametrize(
    "selector", [DTO_SELECTOR, REGISTRY_SELECTOR, {**ARM_SELECTOR, "container_depth": 2}]
)
def test_new_decisions_require_33_and_roundtrip(tmp_path, selector):
    fixture(tmp_path, "compound", [])
    p = tmp_path / "contract.json"
    raw = json.loads(p.read_text())
    raw["rules"][0]["allowed_positions"] = [selector]
    schema = json.loads(Path("schema/architecture-contract-3.3.schema.json").read_text())
    assert Draft202012Validator(schema).is_valid(raw)
    parsed = parse_contract(raw)
    assert parse_contract(json.loads(contract_bytes(parsed))) == parsed
    raw["schema_version"] = "3.2.0"
    with pytest.raises(ValueError, match="3.3.0"):
        parse_contract(raw)


@pytest.mark.parametrize(
    "change",
    [
        {"native_mapping": False},
        {"native_mapping": 1},
        {"annotation": "Any"},
        {"annotation": "list[list[dict]]"},
        {"container_depth": 1},
    ],
)
def test_native_mapping_schema_and_parser_refuse_other_shapes(tmp_path, change):
    fixture(tmp_path, "dto", [])
    raw = json.loads((tmp_path / "contract.json").read_text())
    raw["rules"][0]["allowed_positions"] = [{**DTO_SELECTOR, **change}]
    schema = json.loads(Path("schema/architecture-contract-3.3.schema.json").read_text())
    assert not Draft202012Validator(schema).is_valid(raw)
    with pytest.raises(ValueError):
        parse_contract(raw)


def test_direct_native_bare_map_is_explicit_not_an_implicit_allowance(tmp_path):
    selector = {
        "qualified_name": Q,
        "position": "return",
        "annotation": "dict",
        "native_mapping": True,
    }
    source = "def read() -> dict: pass\n"
    _app(tmp_path, source=source, declared=("sample.app.impl:read",))
    before = _observe(tmp_path)
    assert before.observation is not None
    p = tmp_path / "contract.json"
    raw = json.loads(p.read_text())
    raw["schema_version"] = "3.3.0"
    raw["rules"][0]["allowed_positions"] = [selector]
    p.write_text(json.dumps(raw))
    after = _observe(tmp_path)
    assert after.observation is not None
    assert len(trace_valid_violations(before.observation)) == 1
    assert not trace_valid_violations(after.observation)
    assert before.observation.records("unknowns") == after.observation.records("unknowns")


def test_native_open_map_opt_in_is_a_reported_permission_widening(tmp_path):
    fixture(tmp_path, "dto", [])
    raw = json.loads((tmp_path / "contract.json").read_text())
    before = parse_contract(raw)
    raw["rules"][0]["allowed_positions"] = [DTO_SELECTOR]
    changes = contract_widenings(before, parse_contract(raw))
    assert len(changes) == 1 and "allowed_positions" in changes[0]
    assert "native_mapping=True" in changes[0]


def test_duplicate_literal_object_occurrences_cannot_gain_opacity(tmp_path):
    annotation = f"{ARM} | {ARM}"
    selectors = [
        {**ARM_SELECTOR, "annotation": annotation},
        {**ARM_SELECTOR, "annotation": annotation, "container_depth": 2},
    ]
    _app(
        tmp_path,
        source=f"def read() -> {annotation}: pass\n",
        declared=("sample.app.impl:read",),
        allowances=tuple(selectors),
    )
    p = tmp_path / "contract.json"
    raw = json.loads(p.read_text())
    raw["schema_version"] = "3.3.0"
    p.write_text(json.dumps(raw))
    result = _observe(tmp_path)
    assert result.observation is not None
    assert trace_valid_violations(result.observation)
    assert not any(
        r.kind == "boundary_type_allowance" for r in result.observation.records("typing_signals")
    )
