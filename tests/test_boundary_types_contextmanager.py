# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A native transformed return cannot lend its proof to another type position."""

import json
from dataclasses import replace

import pytest
from collector_pin import assembled
from test_analyzer import _any_rule, _component
from test_python_contextmanager_signatures import _PROGRESS, _native_case, _signature
from test_python_provider_sources import _native_facts

from archkeel.check.evaluation.boundary_types import (
    _boundary_types_violations,
    boundary_type_limits,
    facade_signature_types,
    public_api_exposed_types,
)
from archkeel.check.evaluation.evaluate import evaluate_source
from archkeel.ir.codec import (
    canonical_report_bytes,
    contract_bytes,
    decode_canonical_model,
    parse_contract,
    parse_observation,
)
from archkeel.ir.facts_codec import raw_evidence, raw_record
from archkeel.ir.protocol import (
    CollectionRequest,
    ProtocolVersion,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)
from archkeel.ir.type_shapes import LiteralKind, TypeLiteral


def _contract(*public):
    return parse_contract(
        {
            "schema_version": "3.6.0",
            "components": [
                _component(
                    "sample", packages=["sample"], public=list(public or ["sample.api:progress"])
                )
            ],
            "rules": [
                {
                    "id": "TYPES",
                    "kind": "boundary_types",
                    "source": "sample",
                    "rationale": "Retain the effective exported signature.",
                    "provenance": ["architecture.md"],
                    "decided_by": "architect",
                }
            ],
        }
    )


def _scan(facts, contract=None):
    return evaluate_source(facts, contract or _contract(), roots=("sample",), namespace="sample")


def _unknowns(scan):
    return [row for row in scan.unknowns if "TYPES" in row["rule_ids"]]


def _rows(facts, section):
    return [
        raw_record(row)
        for block in facts.sections
        if block.name == section
        for row in block.records
    ]


def _limits(facts, contract, symbols=None, type_shapes=None, **kwargs):
    return boundary_type_limits(
        _rows(facts, "symbols") if symbols is None else symbols,
        _rows(facts, "imports"),
        contract,
        {file.module: file.all_exports for file in facts.files},
        {item.id: raw_evidence(item) for item in facts.evidence},
        {},
        {file.module for file in facts.files},
        stable_bindings_by_module={file.module: file.stable_bindings for file in facts.files},
        type_shapes=dict(facts.type_shapes) if type_shapes is None else type_shapes,
        provider_bindings=facts.provider_bindings,
        **kwargs,
    )


def test_native_effective_signature_retains_source_and_saved_provenance(tmp_path):
    facts, _ = _native_case(tmp_path)
    symbol, proof = _signature(facts)
    assert proof is not None
    scan = _scan(facts)
    assert scan.violations == [] and _unknowns(scan) == []
    [function] = [row for row in scan.symbols if row["kind"] == "function"]
    assert function["data"]["returns"] == "Iterator[None]"
    assert function["data"]["signature_decorators_proven"] is False
    assert function["data"]["facade_types"] == [proof.effective_return.wrapper]
    assert function["data"]["parameters"] == raw_record(symbol)["data"]["parameters"]
    (tmp_path / "architecture.md").write_text("Publish the proved callable signature.\n")
    contract_path = tmp_path / "contract.json"
    contract_path.write_bytes(contract_bytes(_contract()))
    observation, _ = assembled(
        facts,
        contract_root=tmp_path,
        contract_path=contract_path,
        roots=("sample",),
        namespace="sample",
    )
    saved = parse_observation(
        decode_canonical_model(json.loads(canonical_report_bytes(observation)))
    )
    [stored] = [row for row in saved.records("symbols") if row.kind == "function"]
    assert stored.data.get("returns") == "Iterator[None]"
    assert stored.data.get("contextmanager_signature") == symbol.data.get(
        "contextmanager_signature"
    )


@pytest.mark.parametrize(
    ("payload", "violation", "unknown"),
    [
        ("None", False, False),
        ("str", False, False),
        ("object", True, False),
        ("dict", True, False),
        ("Any", False, True),
        ("dict[str, Any]", True, True),
        ("Missing", False, True),
        ("ContextManager[None]", False, True),
    ],
)
def test_native_contextmanager_checks_the_carried_payload(tmp_path, payload, violation, unknown):
    source = "from typing import Any, ContextManager\n" + _PROGRESS.replace(
        "Iterator[None]", f"Iterator[{payload}]"
    )
    facts, _ = _native_case(tmp_path, source)
    assert _signature(facts)[1] is not None
    scan = _scan(facts)
    assert bool(scan.violations) is violation
    assert bool(_unknowns(scan)) is unknown


def test_native_any_payload_keeps_its_existing_construct_violation(tmp_path):
    facts, _ = _native_case(
        tmp_path, "from typing import Any\n" + _PROGRESS.replace("Iterator[None]", "Iterator[Any]")
    )
    contract = _contract()
    scan = _scan(facts, replace(contract, rules=(*contract.rules, _any_rule())))
    assert any(row["kind"] == "forbidden_construct" for row in scan.violations)
    assert any(row["kind"] == "boundary_type_position" for row in _unknowns(scan))


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [("dict", "FAIL"), ("", "UNKNOWN"), ("ContextManager[None]", "UNKNOWN")],
)
def test_native_contextmanager_keeps_original_parameter_checks(tmp_path, annotation, expected):
    source = "from typing import ContextManager\n" + _PROGRESS.replace(
        "message: str", f"message: {annotation}" if annotation else "message"
    )
    facts, _ = _native_case(tmp_path, source)
    assert _signature(facts)[1] is not None
    scan = _scan(facts)
    assert bool(scan.violations) is (expected == "FAIL")
    positions = [row for row in _unknowns(scan) if row["kind"] == "boundary_type_position"]
    assert [row["data"]["position"] for row in positions] == (
        ["message"] if expected == "UNKNOWN" else []
    )


def test_native_transform_retains_parameter_kinds_and_defaults(tmp_path):
    facts, _ = _native_case(
        tmp_path,
        _PROGRESS.replace("message: str", "message: str = 'work', /, *, verbose: bool = False"),
    )
    symbol, proof = _signature(facts)
    assert proof is not None
    scan = _scan(facts)
    assert scan.violations == [] and _unknowns(scan) == []
    [function] = [row for row in scan.symbols if row["kind"] == "function"]
    assert function["data"]["parameters"] == raw_record(symbol)["data"]["parameters"]
    assert [row["kind"] for row in function["data"]["parameters"]] == [
        "positional_only",
        "keyword_only",
    ]
    assert [row["default"] for row in function["data"]["parameters"]] == ["'work'", "False"]
    assert all(row["default_known"] for row in function["data"]["parameters"])


@pytest.mark.parametrize("scoped", [False, True], ids=["root", "mounted"])
@pytest.mark.parametrize("reexport", [False, True], ids=["direct", "reexport"])
def test_native_return_proof_is_shared_by_rule_and_facade_paths(tmp_path, scoped, reexport):
    facts, providers = _native_case(tmp_path)
    public = "sample.api:progress"
    if reexport:
        (tmp_path / "sample/__init__.py").write_text(
            "from .api import progress\n__all__ = ['progress']\n"
        )
        facts = _native_facts(
            CollectionRequest(
                SnapshotInput(str(tmp_path), "a" * 40, False),
                SourceScope(("sample",), "sample"),
                PythonSettings(provider_sources=providers),
                ProtocolVersion.V4,
            )
        )
        public = "sample:progress"
    contract = _contract(public)
    scan = _scan(facts, contract)
    assert scan.violations == [] and _unknowns(scan) == []
    kwargs = {"source_modules": frozenset({"sample", "sample.api"})} if scoped else {}
    symbols, imports = _rows(facts, "symbols"), _rows(facts, "imports")
    assert _boundary_types_violations(
        symbols, imports, contract, {}, {}, type_shapes=scan.type_shapes, **kwargs
    ) == ([], [])
    assert _limits(facts, contract, **kwargs) == []
    facade = facade_signature_types(
        symbols,
        imports,
        contract,
        {},
        type_shapes=scan.type_shapes,
        **({**kwargs, "scope_id": "sample:api"} if scoped else {}),
    )
    [function] = [row for row in facade if row["kind"] == "function"]
    exposed = (
        function["data"]["facade_types_by_mount"]["sample:api"][public.partition(":")[0]]
        if scoped
        else function["data"]["facade_types"]
    )
    assert exposed == ["contextlib._GeneratorContextManager"]


@pytest.mark.parametrize("scoped", [False, True], ids=["root", "mounted"])
def test_native_proven_return_does_not_seed_an_identical_ordinary_annotation(tmp_path, scoped):
    source = (
        "import contextlib\n"
        + _PROGRESS
        + (
            "\ndef plain(message: contextlib._GeneratorContextManager[None]) "
            "-> contextlib._GeneratorContextManager[None]: return message\n"
        )
    )
    facts, _ = _native_case(tmp_path, source)
    symbols, imports = _rows(facts, "symbols"), _rows(facts, "imports")
    for names in (("progress", "plain"), ("plain",), ("progress", "plain")):
        contract = _contract(*(f"sample.api:{name}" for name in names))
        scan = _scan(facts, contract)
        assert scan.violations == []
        positions = [row for row in _unknowns(scan) if row["kind"] == "boundary_type_position"]
        assert {(row["data"]["qualified_name"], row["data"]["position"]) for row in positions} == {
            ("sample.api.plain", "message"),
            ("sample.api.plain", "return"),
        }
        facade = facade_signature_types(
            symbols,
            imports,
            contract,
            {},
            type_shapes=dict(facts.type_shapes),
            **(
                {"source_modules": frozenset({"sample.api"}), "scope_id": "sample:api"}
                if scoped
                else {}
            ),
        )
        plain = next(row for row in facade if row["data"].get("name") == "plain")
        assert "facade_types" not in plain["data"]
        assert "facade_types_by_mount" not in plain["data"]


@pytest.mark.parametrize(
    "change", ["missing", "corrupt", "source_binding_unique", "namespace_bound"]
)
def test_native_return_proof_requires_metadata_and_both_source_bindings(tmp_path, change):
    facts, _ = _native_case(tmp_path)
    symbols = _rows(facts, "symbols")
    function = next(row for row in symbols if row["kind"] == "function")
    if change == "missing":
        function["data"].pop("contextmanager_signature")
    elif change == "corrupt":
        function["data"]["contextmanager_signature"] = {"kind": "sync-generator-contextmanager-v1"}
    else:
        function["data"][change] = False
    unknowns = _limits(facts, _contract(), symbols=symbols)
    assert {
        row["data"]["position"] for row in unknowns if row["kind"] == "boundary_type_position"
    } == {"message", "return"}


@pytest.mark.parametrize("corrupt", [False, True], ids=["missing", "wrong-head-kind"])
def test_missing_or_corrupt_effective_shape_cannot_prove_the_return(tmp_path, corrupt):
    facts, _ = _native_case(tmp_path)
    _, proof = _signature(facts)
    assert proof is not None
    shape = f"{proof.effective_return.wrapper}[{proof.effective_return.payload}]"
    shapes = dict(facts.type_shapes)
    if corrupt:
        shapes[shape] = replace(
            shapes[shape], head=TypeLiteral(proof.effective_return.wrapper, LiteralKind.NONE)
        )
    else:
        del shapes[shape]
    unknowns = _limits(facts, _contract(), type_shapes=shapes)
    assert [
        row["data"]["position"] for row in unknowns if row["kind"] == "boundary_type_position"
    ] == ["return"]


def test_explicit_public_api_reach_uses_transformed_payload(tmp_path):
    source = "class Payload:\n    value: str\n" + _PROGRESS.replace(
        "Iterator[None]", "Iterator[Payload]"
    )
    facts, _ = _native_case(tmp_path, source)
    scan = _scan(facts)
    unknowns = []
    exposed = public_api_exposed_types(
        ["sample.api:progress"],
        scan.symbols,
        scan.imports,
        scan.modules,
        _contract(),
        type_shapes=scan.type_shapes,
        unknowns=unknowns,
    )
    assert exposed == {"sample.api:progress": ["sample.api:Payload"]}
    assert unknowns == []
