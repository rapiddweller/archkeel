# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Known action ports are nominal; public Delta extension text remains open."""

import json
from enum import StrEnum
from pathlib import Path
from typing import Literal, get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_delta import _delta
from test_delta import _model as _observation
from test_dependency_api_target import _source_members

from archkeel.check import delta, expectation
from archkeel.check.ports import ScanConfig
from archkeel.ir import model
from archkeel.ir.codec import canonical_json_bytes, delta_payload, parse_delta
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
DOC = "docs/architecture/known-delta-action-types.md"
KINDS = [
    ("ADDED", "added"),
    ("REMOVED", "removed"),
    ("RELOCATED", "relocated"),
    ("CHANGED", "changed"),
]


def _kind():
    assert hasattr(model, "KnownSemanticChangeKind"), "the actual known-action owner is missing"
    return model.KnownSemanticChangeKind


def test_existing_semantic_owner_has_exact_known_domain_and_open_wire_field():
    kind = _kind()
    assert issubclass(kind, StrEnum) and kind.__module__ == "archkeel.ir.model"
    assert [(item.name, str(item)) for item in kind] == KINDS
    assert get_type_hints(model.SemanticChange)["change"] is str
    assert get_type_hints(model.UnresolvedCallChange)["change"] == Literal[kind.ADDED, kind.REMOVED]
    assert get_type_hints(expectation.ExpectedSemanticChange)["change"] is kind
    assert get_type_hints(delta._change)["kind"] is kind
    assert get_type_hints(expectation._require_change_kind)["return"] is kind
    assert get_type_hints(expectation._validate_change_counts)["change"] is kind


@pytest.mark.parametrize(("name", "wire"), KINDS)
def test_valid_legacy_selected_constructor_and_actual_ingress_store_one_type(name, wire):
    kind = _kind()
    selected = expectation.ExpectedSemanticChange("violations", wire, "f", 1, 1)
    assert selected.change is kind[name]
    assert expectation._require_change_kind(wire, "change") is kind[name]


@pytest.mark.parametrize(("name", "wire"), KINDS)
def test_actual_producer_serializes_canonical_wire_text_and_retains_changed_fingerprints(
    name, wire
):
    kind = _kind()
    projection = model.Projection(
        "p", "FACT", "architecture", "sample", "sample", (), model.RecordData(()), ()
    )
    row = delta._DeltaRecord("logical", "semantic", "location", projection)
    result = delta._change("vendor.future", kind[name], "f", (row,), (row,))
    assert type(result.change) is str and result.change == wire
    assert result.before_fingerprints == (("semantic",) if name == "CHANGED" else None)
    assert result.after_fingerprints == result.before_fingerprints


@pytest.mark.parametrize("version", ["1.2.0", "1.3.0", "1.4.0", "2.0.0"])
def test_future_public_action_roundtrips_but_known_governance_rejects_it(version):
    raw = _delta(_observation(git_head="1" * 40), _observation(git_head="2" * 40))
    raw["schema_version"] = version
    raw["semantic_changes"].append(
        dict(
            dimension="violations",
            change="vendor.future",
            fingerprint="f",
            before_count=0,
            after_count=0,
            before=None,
            after=None,
        )
    )
    decoded = parse_delta(raw)
    assert canonical_json_bytes(delta_payload(decoded)) == canonical_json_bytes(raw)
    with pytest.raises(
        expectation.ExpectationError,
        match=r"^semantic_changes\[0\]\.change has unsupported value 'vendor.future'$",
    ):
        expectation._index_semantic_changes(decoded.semantic_changes)


@pytest.mark.parametrize(("name", "wire"), KINDS)
@pytest.mark.parametrize(("before", "after"), [(0, 0), (0, 2), (2, 0), (2, 3)])
def test_nominal_count_policy_keeps_the_complete_zero_positive_truth_table(
    name, wire, before, after
):
    kind = _kind()
    valid = (
        (before == 0 and after > 0)
        if name == "ADDED"
        else (before > 0 and after == 0)
        if name == "REMOVED"
        else before > 0 and after > 0
    )
    if valid:
        expectation._validate_change_counts(kind[name], before, after, "selected")
    else:
        with pytest.raises(
            expectation.ExpectationError, match=f"^selected has counts inconsistent with {wire}$"
        ):
            expectation._validate_change_counts(kind[name], before, after, "selected")


@pytest.mark.parametrize("wire", [None, True, 2, {}, [], "", " ", "ADDED", "future"])
def test_both_known_ingresses_keep_original_invalid_labels_and_validation_order(wire):
    raw = dict(
        dimension="violations", change=wire, fingerprint="f", before_count=False, after_count=0
    )
    with pytest.raises(expectation.ExpectationError) as selected:
        expectation._parse_selected_change(raw, index=3)
    nonempty = isinstance(wire, str) and bool(wire.strip())
    assert str(selected.value) == (
        f"selected_changes[3] has unsupported change {wire!r}"
        if nonempty
        else "selected_changes[3].change must be a non-empty string"
    )
    with pytest.raises(expectation.ExpectationError) as indexed:
        expectation._require_change_kind(wire, "actual.change")
    assert str(indexed.value) == (
        f"actual.change has unsupported value {wire!r}"
        if nonempty
        else "actual.change must be a non-empty string"
    )


def test_index_retains_nominal_keys_and_plain_duplicate_error():
    kind = _kind()
    change = model.SemanticChange("violations", "added", "f", 0, 1, None, None)
    indexed, removed, added = expectation._index_semantic_changes((change,))
    identity = next(iter(indexed))
    assert identity[1] is kind.ADDED
    assert not removed and not added
    with pytest.raises(expectation.ExpectationError) as error:
        expectation._index_semantic_changes((change, change))
    assert str(error.value) == "delta repeats semantic fingerprint: ('violations', 'added', 'f')"


def _contract():
    ir = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    check = json.loads((ROOT / "docs/architecture/contracts/check.json").read_text())
    entities = [
        row
        for contract in (ir, check)
        for row in contract["declarations"]["uml"]["entities"]
        if row["id"].startswith("KNOWN-ACTION-") or row["id"] == "IR-DEPENDENCY-model"
    ]
    for row in entities:
        if row["kind"] == "module":
            row.pop("parent_id", None)
    ir.pop("$schema", None)
    ir["components"] = [
        dict(
            id="CORE",
            label="core",
            role="component",
            packages=["archkeel"],
            responsibilities=["Own the actual typed action ports."],
            forbidden_responsibilities=[],
            provenance=[DOC],
            public=["archkeel"],
        )
    ]
    ir["declarations"] = {
        "uml": {"schema_version": "1.0.0", "entities": entities, "relationships": [], "scopes": []}
    }
    ir["rules"] = [
        dict(
            id="ACTION-" + module,
            kind="forbidden_construct",
            source="archkeel." + module,
            constructs=["string_literal_compare"],
            rationale="Actual migrated source projections use nominal actions.",
            provenance=[DOC],
            decided_by="architect",
        )
        for module in ["ir.model", "check.delta", "check.expectation"]
    ]
    return ir


def _repository(tmp_path):
    prefix = "from __future__ import annotations\nfrom dataclasses import dataclass\n"
    root = _prepare_repo(
        tmp_path,
        {
            "archkeel/__init__.py": "",
            "archkeel/ir/__init__.py": "",
            "archkeel/check/__init__.py": "",
            "archkeel/ir/model.py": prefix
            + "from enum import StrEnum\n"
            + _source_members(
                "src/archkeel/ir/model.py", {"KnownSemanticChangeKind", "SemanticChange"}
            ),
            "archkeel/check/delta.py": prefix
            + "from archkeel.ir.model import KnownSemanticChangeKind as _KnownSemanticChangeKind\n"
            "from archkeel.ir.model import SemanticChange\n"
            + _source_members("src/archkeel/check/delta.py", {"_DeltaRecord", "_change"}),
            "archkeel/check/expectation.py": prefix + "import builtins as _builtins\n"
            "from archkeel.ir.model import KnownSemanticChangeKind as _KnownSemanticChangeKind\n"
            + _source_members(
                "src/archkeel/check/expectation.py",
                {
                    "ExpectationError",
                    "ExpectedSemanticChange",
                    "_require_change_kind",
                    "_validate_change_counts",
                },
            ),
            "contract.json": json.dumps(_contract()),
            DOC: "Independent actual action boundary intent.\n",
        },
    )
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _valid(value):
    comparison = architecture_report(value).comparison
    assert comparison is not None and comparison.status == "PASS", [
        (row.subject_id, row.aspect, row.status, row.reason)
        for row in comparison.assessments
        if row.status != "PASS"
    ]
    assert not trace_valid_violations(value)
