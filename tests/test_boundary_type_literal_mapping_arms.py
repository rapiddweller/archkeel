# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exact literal map arms preserve member findings and every other contributor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_types_nested_dtos import _write_app

from archkeel.ir.codec import contract_bytes, parse_contract
from archkeel.ir.model import ObservationResult
from archkeel.ir.trace import trace_valid_violations

QUALNAME = "sample.app.impl.read"
ANNOTATION = (
    "list[dict[str, str]] | list[JsonValue] | dict[str, JsonValue] | list[dict[str, object]]"
)
ROOT = "dict[str, JsonValue]"
CSV = "list[dict[str, str]]"
MEMSTORE = "list[dict[str, object]]"
SOURCE = (
    "JsonValue = str | list['JsonValue'] | dict[str, 'JsonValue']\n"
    f"def read() -> {ANNOTATION}: pass\n"
)


def _fixture(
    root: Path,
    *,
    arms: tuple[str, ...] = (),
    version: str = "3.2.0",
    source: str = SOURCE,
    annotation: str = ANNOTATION,
) -> None:
    selectors = tuple(
        {
            "qualified_name": QUALNAME,
            "position": "return",
            "field_path": "",
            "annotation": annotation,
            **({"literal_mapping_arm": arm} if arm != "old-root" else {}),
        }
        for arm in arms
    )
    _write_app(
        root,
        implementation=source,
        declared=("sample.app.impl:read",),
        allowed_positions=selectors,
    )
    path = root / "contract.json"
    contract = json.loads(path.read_text())
    contract["schema_version"] = version
    path.write_text(json.dumps(contract))


def _findings(result: ObservationResult) -> set[tuple[object, object]]:
    assert result.observation is not None, result.diagnostics
    return {
        (item.data.get("nested_annotation"), item.data.get("container_depth", 0))
        for item in trace_valid_violations(result.observation)
    }


def test_literal_mapping_arm_requires_32_and_roundtrips(tmp_path: Path) -> None:
    _fixture(tmp_path, arms=(CSV,))
    raw = json.loads((tmp_path / "contract.json").read_text())
    contract = parse_contract(raw)
    assert contract.rules[0].allowed_positions[0].literal_mapping_arm == CSV
    assert parse_contract(json.loads(contract_bytes(contract))) == contract
    for version in ("2.1.0", "2.2.0", "2.3.0", "3.0.0", "3.1.0"):
        raw["schema_version"] = version
        with pytest.raises(ValueError, match="literal_mapping_arm.*3.2.0"):
            parse_contract(raw)


@pytest.mark.parametrize(
    ("version", "arms", "removed"),
    [
        ("2.1.0", ("old-root",), {(ROOT, 0)}),
        ("3.2.0", (), set()),
        ("3.2.0", (ROOT,), {(ROOT, 0)}),
        ("3.2.0", (CSV,), {("dict[str, str]", 1)}),
        ("3.2.0", (MEMSTORE,), {("dict[str, object]", 1)}),
        (
            "3.2.0",
            (ROOT, CSV, MEMSTORE),
            {(ROOT, 0), ("dict[str, str]", 1), ("dict[str, object]", 1)},
        ),
    ],
)
def test_literal_mapping_arm_ce_migration_matrix(
    tmp_path: Path, version: str, arms: tuple[str, ...], removed: set[tuple[str, int]]
) -> None:
    _fixture(tmp_path, version="3.1.0")
    baseline = _observe(tmp_path)
    expected = {
        ("dict[str, str]", 1),
        ("dict[str, object]", 1),
        ("object", 2),
        (ROOT, 0),
    }
    assert _findings(baseline) == expected
    assert baseline.observation is not None
    unknowns = baseline.observation.records("unknowns")
    assert unknowns
    _fixture(tmp_path, version=version, arms=arms)
    result = _observe(tmp_path)
    assert _findings(result) == expected - removed
    assert result.observation is not None
    assert result.observation.records("unknowns") == unknowns
    facts = [
        item
        for item in result.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    assert len(facts) == len(removed)
    if version == "3.2.0":
        assert {item.data.get("literal_mapping_arm") for item in facts} == set(arms)
        assert {item.data.get("observed_container_depth") for item in facts} == {
            depth for _, depth in removed
        }


@pytest.mark.parametrize(
    "change",
    [
        {"field_path": "rows"},
        {"container_depth": 1},
        {"mapping_depth": 1},
        {"alias_body": {"origin": "sample.app.impl:Rows", "shape": "dict[str, str]"}},
        {"key_alias_body": {"origin": "sample.app.impl:Key", "shape": "str"}},
        {"literal_mapping_arm": ""},
        {"literal_mapping_arm": " "},
        {"literal_mapping_arm": {"annotation": CSV, "depth": 1}},
    ],
)
def test_literal_mapping_arm_refuses_other_selector_coordinates(
    tmp_path: Path, change: dict[str, object]
) -> None:
    _fixture(tmp_path, arms=(CSV,))
    raw = json.loads((tmp_path / "contract.json").read_text())
    raw["rules"][0]["allowed_positions"][0].update(change)
    with pytest.raises(ValueError):
        parse_contract(raw)


@pytest.mark.parametrize(
    ("annotation", "arm", "prefix", "change"),
    [
        (ANNOTATION, CSV, SOURCE.split("def read")[0], {"qualified_name": "sample.app.impl.wrong"}),
        (ANNOTATION, CSV, SOURCE.split("def read")[0], {"position": "value"}),
        (ANNOTATION, CSV, SOURCE.split("def read")[0], {"annotation": "list[dict[str, str]]"}),
        ("dict[str, str] | None", CSV, "", {}),
        ("list[dict[str, str]] | None", "dict[str, str]", "", {}),
        ("list[dict[int, str]] | None", "list[dict[int, str]]", "", {}),
        ("list[dict[str, int]] | None", "list[dict[str, int]]", "", {}),
        ("list[dict[str, Missing]] | None", "list[dict[str, Missing]]", "", {}),
        ("list[dict[str, Value]] | None", "list[dict[str, Value]]", "Value = str\n", {}),
        ("Rows | None", "Rows", "Rows = list[dict[str, str]]\n", {}),
        ("'list[dict[str, str]]' | None", "'list[dict[str, str]]'", "", {}),
        ("tuple[list[dict[str, str]]] | None", "tuple[list[dict[str, str]]]", "", {}),
        ("list[list[dict[str, str]]] | None", "list[list[dict[str, str]]]", "", {}),
        (
            "Annotated[list[dict[str, str]], 'x'] | None",
            "list[dict[str, str]]",
            "from typing import Annotated\n",
            {},
        ),
        ("dict | None", "dict", "", {}),
        ("Root | None", "Root", "Root = dict[str, str]\n", {}),
        ("'dict[str, str]' | None", "'dict[str, str]'", "", {}),
        ("dict[int, Missing] | None", "dict[int, Missing]", "", {}),
        ("dict[str, str] | dict[str, object]", "dict[str, str]", "", {}),
        (
            "dict[str, str] | list[dict[str, str]] | None",
            "list[dict[str, str]]",
            "class str: pass\n",
            {},
        ),
        ("list[dict[str, str]] | None", CSV, "class list: pass\n", {}),
        ("list[dict[str, str]] | None", CSV, "class dict: pass\n", {}),
        ("list[dict[str, object]] | None", MEMSTORE, "class object: pass\n", {}),
        ("list[dict[str, str]] | None", CSV, "from unknown import list\n", {}),
    ],
)
def test_literal_mapping_arm_rejects_unproven_or_wrong_identity(
    tmp_path: Path,
    annotation: str,
    arm: str,
    prefix: str,
    change: dict[str, str],
) -> None:
    source = prefix + f"def read() -> {annotation}: pass\n"
    _fixture(tmp_path, source=source, annotation=annotation)
    baseline = _observe(tmp_path)
    _fixture(tmp_path, source=source, annotation=annotation, arms=(arm,))
    path = tmp_path / "contract.json"
    raw = json.loads(path.read_text())
    raw["rules"][0]["allowed_positions"][0].update(change)
    path.write_text(json.dumps(raw))
    after = _observe(tmp_path)
    assert baseline.observation is not None and after.observation is not None
    assert trace_valid_violations(after.observation) == trace_valid_violations(baseline.observation)
    assert after.observation.records("unknowns") == baseline.observation.records("unknowns")
    assert not [
        item
        for item in after.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]


@pytest.mark.parametrize("resolved", [False, True])
def test_literal_mapping_arm_alias_later_collision_keeps_shared_aggregate(
    tmp_path: Path, resolved: bool
) -> None:
    annotation = "list[dict[str, str]] | Rows | Missing"
    prefix = "Rows = list[dict[str, str]]\n" if resolved else ""
    source = prefix + f"def read() -> {annotation}: pass\n"
    _fixture(tmp_path, source=source, annotation=annotation)
    baseline = _observe(tmp_path)
    _fixture(tmp_path, source=source, annotation=annotation, arms=(CSV,))
    after = _observe(tmp_path)
    assert baseline.observation is not None and after.observation is not None
    assert after.observation.records("unknowns") == baseline.observation.records("unknowns")
    assert _findings(after) == set()
    if resolved:
        aliases = [
            row
            for row in after.observation.records("symbols") or ()
            if row.kind == "type_alias" and row.data.get("name") == "Rows"
        ]
        assert len(aliases) == 1
        assert aliases[0].data.get("source_member_binding_static") is False
    facts = [
        item
        for item in after.observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]
    assert len(facts) == 1


@pytest.mark.parametrize(
    ("annotation", "arm"),
    [
        ("list[dict[str, str]] | list[dict[str, str]] | Missing", CSV),
        ("dict[str, Missing] | dict[str, Missing]", "dict[str, Missing]"),
    ],
)
def test_literal_mapping_arm_duplicate_syntax_is_not_a_unique_contributor(
    tmp_path: Path, annotation: str, arm: str
) -> None:
    source = f"def read() -> {annotation}: pass\n"
    _fixture(tmp_path, source=source, annotation=annotation)
    baseline = _observe(tmp_path)
    _fixture(tmp_path, source=source, annotation=annotation, arms=(arm,))
    after = _observe(tmp_path)
    assert baseline.observation is not None and after.observation is not None
    assert trace_valid_violations(after.observation) == trace_valid_violations(baseline.observation)
    assert after.observation.records("unknowns") == baseline.observation.records("unknowns")


@pytest.mark.parametrize("facade", [False, True])
def test_literal_mapping_arm_ordinary_report_keeps_fail_unknown(
    tmp_path: Path, facade: bool
) -> None:
    from test_atlas_report import _flow_payload
    from test_boundary_type_bound_aliases import _cli
    from test_boundary_types_contained_mapping import _commit_report_fixture

    from archkeel.ir.codec import decode_canonical_model, parse_observation

    _fixture(tmp_path, arms=(ROOT, CSV, MEMSTORE))
    path = tmp_path / "contract.json"
    raw = json.loads(path.read_text())
    if facade:
        (tmp_path / "sample/app/__init__.py").write_text(
            "from .impl import read\n__all__ = ['read']\n"
        )
        raw["components"][0]["public"] = ["sample.app:read"]
        for selector in raw["rules"][0]["allowed_positions"]:
            selector["qualified_name"] = "sample.app.read"
        path.write_text(json.dumps(raw))
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "archkeel.toml").write_text(
        '[scan]\nroots = ["."]\nnamespace = "sample"\ncontract = "contract.json"\n'
    )
    _commit_report_fixture(tmp_path)
    output = tmp_path / "architecture.json"
    report = _cli(tmp_path, "report", output)
    assert report.returncode == 0, (report.stdout, report.stderr)
    model = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    assert {
        (row.data.get("nested_annotation"), row.data.get("container_depth"))
        for row in trace_valid_violations(model)
    } == {("object", 2)}
    assert model.records("unknowns")
    permissions = _flow_payload(output.with_suffix(".report.html"))["boundary_permissions"]
    assert permissions == _flow_payload(output.with_suffix(".detail.html"))["boundary_permissions"]
    assert {row["literal_mapping_arm"] for row in permissions["declared"]} == {ROOT, CSV, MEMSTORE}
    assert {row["data"]["literal_mapping_arm"] for row in permissions["applied"]} == {
        ROOT,
        CSV,
        MEMSTORE,
    }
    assert len(permissions["applied"]) == 3
    assert all(row["declaration_id"] and row["rationale"] for row in permissions["applied"])
    validate = _cli(tmp_path, "validate", output)
    assert validate.returncode == 2, (validate.stdout, validate.stderr)
    assert json.loads(validate.stdout)["declared_rules"] == "UNKNOWN"


def test_literal_mapping_arm_is_a_distinct_widening(tmp_path: Path) -> None:
    from archkeel.ir.widening import contract_widening_changes

    _fixture(tmp_path)
    before = parse_contract(json.loads((tmp_path / "contract.json").read_text()))
    _fixture(tmp_path, arms=(CSV, MEMSTORE))
    after = parse_contract(json.loads((tmp_path / "contract.json").read_text()))
    changes = contract_widening_changes(before, after)
    assert len(changes) == 2
    assert all(change.field == "allowed_positions" for change in changes)
    assert CSV in changes[0].message or CSV in changes[1].message
    assert MEMSTORE in changes[0].message or MEMSTORE in changes[1].message


@pytest.mark.parametrize("head", ["Union", "Optional"])
def test_literal_mapping_arm_requires_proven_union_provider(tmp_path: Path, head: str) -> None:
    annotation = f"{head}[{CSV}, Missing]" if head == "Union" else f"{head}[{CSV}]"
    source = f"from typing import {head}\nunknown({head})\ndef read() -> {annotation}: pass\n"
    _fixture(tmp_path, source=source, annotation=annotation)
    baseline = _observe(tmp_path)
    _fixture(tmp_path, source=source, annotation=annotation, arms=(CSV,))
    after = _observe(tmp_path)
    assert baseline.observation is not None and after.observation is not None
    assert ("dict[str, str]", 1) in _findings(baseline)
    assert trace_valid_violations(after.observation) == trace_valid_violations(baseline.observation)
    assert after.observation.records("unknowns") == baseline.observation.records("unknowns")


@pytest.mark.parametrize("missing", ["route", "contributor"])
def test_literal_mapping_arm_missing_provenance_refuses(missing: str) -> None:
    from dataclasses import replace

    from archkeel.analyzer.python.type_shapes import collect_type_shapes
    from archkeel.check.evaluation import boundary_types as core
    from archkeel.ir.model import ArchitectureContract, BoundaryTypeAllowance

    annotation = f"{CSV} | {CSV} | Missing" if missing == "contributor" else f"{CSV} | Missing"
    verdict = core._boundary_type_verdict(
        annotation,
        "sample",
        ArchitectureContract(schema_version="3.2.0", components=(), rules=()),
        {},
        core.BindingIndex(),
        core.BindingIndex(),
        type_shapes=collect_type_shapes([annotation]),
    )
    assert verdict.undecidable is not None
    assert len(verdict.mapping_occurrences) == (2 if missing == "contributor" else 1)
    if missing == "route":
        occurrences = (verdict.mapping_occurrences[0]._replace(syntax_route=None),)
    else:
        occurrences = verdict.mapping_occurrences[:1]
    incomplete = replace(verdict, mapping_occurrences=occurrences)
    selector = BoundaryTypeAllowance(QUALNAME, "return", "", annotation, literal_mapping_arm=CSV)
    data = {
        "reason": core._BROAD_BOUNDARY_REASON,
        "nested_annotation": "dict[str, str]",
        "container_depth": 1,
    }
    assert not core._literal_mapping_arm_allowance_matches(selector, data, incomplete)


@pytest.mark.parametrize(
    "source,annotation",
    [
        (SOURCE, ANNOTATION),
        (
            "Rows = list[dict[str, str]]\n"
            "def read() -> tuple[Rows, list[dict[str, object]], Missing]: pass\n",
            "tuple[Rows, list[dict[str, object]], Missing]",
        ),
        (
            "from typing import Annotated\n"
            "def read() -> Annotated[list[dict[str, str]], 'tag'] | Missing: pass\n",
            "Annotated[list[dict[str, str]], 'tag'] | Missing",
        ),
        (
            "from dataclasses import dataclass\n@dataclass\nclass Payload:\n"
            "    rows: list[dict[str, object]]\ndef read() -> Payload | Missing: pass\n",
            "Payload | Missing",
        ),
    ],
)
def test_literal_mapping_arm_absence_preserves_complete_31_records(
    tmp_path: Path,
    source: str,
    annotation: str,
) -> None:
    results = []
    for version in ("3.1.0", "3.2.0"):
        _fixture(tmp_path, version=version, source=source, annotation=annotation)
        path = tmp_path / "contract.json"
        raw = json.loads(path.read_text())
        raw["components"][0]["public"].append(
            "sample.app.impl:Payload"
        ) if "class Payload" in source else None
        path.write_text(json.dumps(raw))
        result = _observe(tmp_path)
        assert result.observation is not None
        results.append(result.observation)
    for section in ("violations", "unknowns", "typing_signals"):
        assert results[0].records(section) == results[1].records(section)


@pytest.mark.parametrize(
    "change,accepted",
    [
        ({}, True),
        ({"literal_mapping_arm": ""}, False),
        ({"container_depth": 1}, False),
        ({"mapping_depth": 1}, False),
        ({"field_path": "rows"}, False),
        ({"alias_body": {"origin": "sample.Rows", "shape": CSV}}, False),
        ({"key_alias_body": {"origin": "sample.Key", "shape": "str | None"}}, False),
    ],
)
def test_literal_mapping_arm_schema_matches_parser(
    tmp_path: Path, change: dict, accepted: bool
) -> None:
    from jsonschema import Draft202012Validator
    from test_schema_drift import _schema

    _fixture(tmp_path, arms=(CSV,))
    raw = json.loads((tmp_path / "contract.json").read_text())
    raw["rules"][0]["allowed_positions"][0].update(change)
    assert (
        Draft202012Validator(_schema("architecture-contract-3.2.schema.json")).is_valid(raw)
        is accepted
    )
    if accepted:
        parse_contract(raw)
    else:
        with pytest.raises(ValueError):
            parse_contract(raw)
