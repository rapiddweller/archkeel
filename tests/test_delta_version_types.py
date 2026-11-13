# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Actual Delta version ports preserve legacy bytes and open extension strings."""

import copy
import json
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_delta import _delta
from test_delta import _model as _observation
from test_dependency_api_target import _source_members

from archkeel.check.ports import ScanConfig
from archkeel.ir import model
from archkeel.ir.codec import canonical_json_bytes, delta_payload, parse_delta
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
DOC = "docs/architecture/delta-version-types.md"
VERSIONS = [("V1_2", "1.2.0"), ("V1_3", "1.3.0"), ("V1_4", "1.4.0"), ("V2_0", "2.0.0")]


def _payload():
    return _delta(_observation(git_head="1" * 40), _observation(git_head="2" * 40))


def test_existing_model_owns_exact_delta_version_domain_and_actual_ports():
    assert hasattr(model, "DeltaVersion")
    assert issubclass(model.DeltaVersion, StrEnum)
    assert model.DeltaVersion.__module__ == "archkeel.ir.model"
    assert [(item.name, str(item)) for item in model.DeltaVersion] == VERSIONS
    assert type(model.DELTA_SCHEMA_VERSION) is str and model.DELTA_SCHEMA_VERSION == "2.0.0"
    assert get_type_hints(model.ArchitectureDelta)["schema_version"] is model.DeltaVersion
    assert get_type_hints(model.supports_nullable_delta_counts) == {
        "version": model.DeltaVersion,
        "return": bool,
    }


@pytest.mark.parametrize(("name", "wire"), VERSIONS)
def test_each_supported_delta_wire_version_normalizes_and_roundtrips_exactly(name, wire):
    assert hasattr(model, "DeltaVersion")
    raw = _payload()
    raw["schema_version"] = wire
    value = parse_delta(raw)
    assert value.schema_version is model.DeltaVersion[name]
    assert canonical_json_bytes(delta_payload(value)) == canonical_json_bytes(raw)


@pytest.mark.parametrize(("name", "wire"), VERSIONS)
def test_valid_legacy_dataclass_version_replacement_uses_the_canonical_type(name, wire):
    assert hasattr(model, "DeltaVersion")
    value = replace(parse_delta(_payload()), schema_version=wire)
    assert value.schema_version is model.DeltaVersion[name]


@pytest.mark.parametrize(
    ("name", "expected"), [("V1_2", False), ("V1_3", False), ("V1_4", True), ("V2_0", True)]
)
def test_single_owned_nullable_count_policy_has_exact_historical_truth_table(name, expected):
    assert hasattr(model, "DeltaVersion")
    assert model.supports_nullable_delta_counts(model.DeltaVersion[name]) is expected


@pytest.mark.parametrize("wire", ["1.1.0", "1.5.0", "2.1.0", "future"])
def test_unsupported_wire_versions_keep_the_original_error(wire):
    raw = _payload()
    raw["schema_version"] = wire
    with pytest.raises(ValueError, match="^unsupported delta schema version$"):
        parse_delta(raw)


@pytest.mark.parametrize("wire", [None, True, 2, {}, []])
def test_nonstring_version_values_keep_the_original_wire_error(wire):
    raw = _payload()
    raw["schema_version"] = wire
    with pytest.raises(ValueError, match="delta.schema_version"):
        parse_delta(raw)


def test_direct_invalid_version_constructor_cannot_export_an_unsupported_format():
    with pytest.raises(ValueError):
        replace(parse_delta(_payload()), schema_version="future")


def test_public_future_dimension_and_semantic_change_values_remain_open_wire_data():
    raw = _payload()
    raw["dimensions"]["vendor.future"] = copy.deepcopy(raw["dimensions"]["coverage"])
    raw["semantic_changes"].append(
        {
            "dimension": "vendor.future",
            "change": "vendor-experiment",
            "fingerprint": "f" * 64,
            "before_count": 0,
            "after_count": 0,
            "before": None,
            "after": None,
        }
    )
    raw["unknowns"].append(
        {
            "id": "vendor-unknown",
            "dimension": "vendor.future",
            "reason": "vendor opaque reason",
            "evidence_class": "UNKNOWN",
        }
    )
    assert canonical_json_bytes(delta_payload(parse_delta(raw))) == canonical_json_bytes(raw)


def _contract():
    intent = copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text()))
    intent.pop("$schema", None)
    intent["declarations"]["uml"]["entities"] = [
        row
        for row in intent["declarations"]["uml"]["entities"]
        if row["id"].startswith("IR-DELTA-VERSION-") or row["id"] == "IR-DEPENDENCY-model"
    ]
    intent["declarations"]["uml"]["relationships"] = []
    intent["declarations"]["uml"]["scopes"] = []
    # Both files below are honest source projections of the migrated version ports only.
    intent["rules"] = [
        {
            "id": "DELTA-VERSION-" + name,
            "kind": "forbidden_construct",
            "source": source,
            "constructs": ["string_literal_compare"],
            "rationale": "Version decisions use owned tags.",
            "provenance": [DOC],
            "decided_by": "architect",
        }
        for name, source in [("OWNER", "archkeel.ir.model"), ("CODEC", "archkeel.ir.codec_delta")]
    ]
    return intent


def _repository(tmp_path):
    actual = (ROOT / "src/archkeel/ir/model.py").read_text()
    version_label = next(
        line for line in actual.splitlines() if line.startswith("DELTA_SCHEMA_VERSION =")
    )
    owner = (
        "from __future__ import annotations\nimport builtins\n"
        "from collections.abc import Mapping, Sequence\n"
        "from dataclasses import dataclass\nfrom enum import StrEnum\n"
        "from typing import Final, TypeAlias\n"
        + version_label
        + "\n"
        + _source_members(
            "src/archkeel/ir/model.py",
            {"RawJson", "DeltaVersion", "ArchitectureDelta", "supports_nullable_delta_counts"},
        )
    )
    codec = (
        "from __future__ import annotations\n"
        "from .model import DeltaVersion, RawJson\nfrom .codec_wire import _string\n"
        + _source_members("src/archkeel/ir/codec_delta.py", {"_parse_delta_version"})
    )
    root = _prepare_repo(
        tmp_path,
        {
            "archkeel/__init__.py": "",
            "archkeel/ir/__init__.py": "",
            "archkeel/ir/model.py": owner,
            "archkeel/ir/codec_delta.py": codec,
            "contract.json": json.dumps(_contract()),
            DOC: "Independent Delta version intent.\n",
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
