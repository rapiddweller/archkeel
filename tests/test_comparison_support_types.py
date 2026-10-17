# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One support type at the real claim/Delta ports; open wire data stays open."""

import copy
import json
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import CONFIG, _prepare_repo
from test_delta import _delta
from test_delta import _model as _observation
from test_dependency_api_target import _source_members
from test_duplication import _TOUR
from test_uml_evaluation import _model

from archkeel.check.ports import ScanConfig
from archkeel.ir import bindings, codec_delta, decisions, duplication, model, references, structure
from archkeel.ir import type_fanin as fanin
from archkeel.ir.codec import canonical_json_bytes, delta_payload, parse_delta
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
DOC = "docs/architecture/comparison-support-types.md"
CLAIMS = [
    (bindings, "BindingReads", "unread_bindings", "functions", "binding"),
    (references, "SymbolReferences", "unreferenced_symbols", "symbols", "symbols"),
    (fanin, "TypeFanin", "type_fanin", "positions", "crossing"),
    (structure, "InsideSizes", "oversized_insides", "components", "component"),
    (duplication, "OwnedLogic", "repeated_logic", "owners", "repetition"),
]


def _payload():
    return _delta(_observation(git_head="1" * 40), _observation(git_head="2" * 40))


def test_existing_model_owns_one_exact_nominal_support_domain():
    assert isinstance(model.ComparisonStatus, type)
    assert issubclass(model.ComparisonStatus, StrEnum)
    assert model.ComparisonStatus.__module__ == "archkeel.ir.model"
    assert [(value.name, str(value)) for value in model.ComparisonStatus] == [
        ("SUPPORTED", "SUPPORTED"),
        ("UNKNOWN", "UNKNOWN"),
    ]
    for module, name, *_ in CLAIMS:
        assert module.ComparisonStatus is model.ComparisonStatus
        assert get_type_hints(getattr(module, name))["status"] is model.ComparisonStatus
    for cls in (model.DimensionDelta, model.RatchetObservations):
        assert get_type_hints(cls)["status"] is model.ComparisonStatus


@pytest.mark.parametrize(("module", "name", "producer", "count", "noun"), CLAIMS)
@pytest.mark.parametrize("wire", ["SUPPORTED", "UNKNOWN"])
def test_all_five_valid_legacy_claim_constructors_store_the_canonical_type(
    module, name, producer, count, noun, wire
):
    value = getattr(module, name)(wire)
    assert value.status is model.ComparisonStatus[wire]


@pytest.mark.parametrize(("module", "name", "producer", "count", "noun"), CLAIMS)
def test_all_five_unknown_invariants_keep_the_original_error_and_empty_supported_is_valid(
    module, name, producer, count, noun
):
    cls = getattr(module, name)
    assert getattr(cls("SUPPORTED", **{count: 0}), count) == 0
    with pytest.raises(ValueError, match=f"^an unsupported claim names no {noun}$"):
        cls("UNKNOWN", **{count: 1})


@pytest.mark.parametrize(("module", "name", "producer", "count", "noun"), CLAIMS)
def test_actual_claim_producers_return_nominal_support_in_both_signal_paths(
    tmp_path, module, name, producer, count, noun
):
    observation = _model(_prepare_repo(tmp_path, dict(_TOUR.files)), CONFIG)
    derive = getattr(module, producer)
    complete = derive(observation)
    assert isinstance(complete.status, StrEnum)
    assert complete.status is model.ComparisonStatus.SUPPORTED
    missing = replace(observation, sections=())
    assert derive(missing).status is model.ComparisonStatus.UNKNOWN


@pytest.mark.parametrize("wire", ["SUPPORTED", "UNKNOWN"])
def test_delta_dto_legacy_statuses_normalize_without_changing_measurement_invariants(wire):
    cls = model.ComparisonStatus
    dimension = model.DimensionDelta("vendor.future", wire, None, None)
    assert dimension.name == "vendor.future"
    assert dimension.status is cls[wire]
    measured = parse_delta(_payload()).ratchets
    value = (
        replace(measured, status=wire)
        if wire == "SUPPORTED"
        else model.RatchetObservations(wire, reason="evidence absent")
    )
    assert value.status is cls[wire]
    for baseline, head in [(measured.baseline, None), (None, measured.head)]:
        with pytest.raises(
            ValueError, match="^measurements exist exactly when regression checks are SUPPORTED$"
        ):
            model.RatchetObservations(wire, baseline, head)


def test_shared_count_decision_distinguishes_missing_evidence_from_measured_zero():
    assert decisions._named(model.ComparisonStatus.UNKNOWN, ()) is None
    assert decisions._named(model.ComparisonStatus.SUPPORTED, ()) == 0
    assert decisions._named(model.ComparisonStatus.SUPPORTED, (object(),)) == 1
    assert get_type_hints(decisions._named)["status"] is model.ComparisonStatus


@pytest.mark.parametrize("version", ["1.2.0", "1.3.0", "1.4.0", "2.0.0"])
def test_all_supported_delta_versions_keep_exact_bytes_and_open_future_wire_fields(version):
    raw = _payload()
    raw["schema_version"] = version
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
    value = parse_delta(raw)
    assert all(isinstance(item.status, model.ComparisonStatus) for item in value.dimensions)
    assert isinstance(value.ratchets.status, model.ComparisonStatus)
    assert canonical_json_bytes(delta_payload(value)) == canonical_json_bytes(raw)


@pytest.mark.parametrize("wire", [None, True, 2, {}, [], "FAIL", "future"])
def test_invalid_delta_status_values_keep_both_existing_error_labels(wire):
    raw = _payload()
    raw["dimensions"]["coverage"]["status"] = wire
    with pytest.raises(ValueError, match=r"^dimensions\.coverage\.status invalid$"):
        parse_delta(raw)
    raw = _payload()
    raw["ratchets"] = {"status": wire}
    with pytest.raises(ValueError, match=r"^delta\.ratchets status invalid$"):
        parse_delta(raw)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"status": "SUPPORTED"}, "supported regression check fields mismatch"),
        ({"status": "UNKNOWN"}, "unknown regression check fields mismatch"),
        ({"status": "UNKNOWN", "reason": None}, "ratchets.reason must be a string"),
    ],
)
def test_status_specific_invalid_field_shapes_keep_error_order(raw, message):
    with pytest.raises(ValueError, match=message):
        codec_delta._parse_ratchets(raw, nullable_calls=True)


def _contract(*, producers=False):
    intent = copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text()))
    intent.pop("$schema", None)
    intent["declarations"]["uml"]["entities"] = [
        row
        for row in intent["declarations"]["uml"]["entities"]
        if (
            row["id"].startswith("IR-COMPARISON-")
            and (producers or not row["id"].startswith("IR-COMPARISON-producer-"))
        )
        or row["id"] in {"IR-DEPENDENCY-model", "IR-DELTA-VERSION-codec"}
    ]
    intent["declarations"]["uml"]["relationships"] = []
    intent["declarations"]["uml"]["scopes"] = []
    modules = ["model", "codec_delta", "decisions"]
    if not producers:
        modules += [module.__name__.rsplit(".", 1)[-1] for module, *_ in CLAIMS]
    # Guard actual DTO/decoder/decision projections only. Producer API fixtures below
    # additionally retain their whole algorithms, whose other raw vocabularies remain pending.
    intent["rules"] = [
        {
            "id": "COMPARISON-" + name,
            "kind": "forbidden_construct",
            "source": "archkeel.ir." + name,
            "constructs": ["string_literal_compare"],
            "rationale": "These actual migrated support boundaries use the canonical type.",
            "provenance": [DOC],
            "decided_by": "architect",
        }
        for name in modules
    ]
    return intent


def _repository(tmp_path, *, producers=False):
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "contract.json": json.dumps(_contract(producers=producers)),
        DOC: "Independent shared comparison support intent.\n",
    }
    prefix = "from __future__ import annotations\nfrom dataclasses import dataclass\n"
    files["archkeel/ir/model.py"] = (
        prefix
        + "from enum import StrEnum\nfrom typing import TypeAlias\n"
        + _source_members(
            "src/archkeel/ir/model.py",
            {"RawJson", "ComparisonStatus", "DimensionDelta", "RatchetObservations"},
        )
    )
    files["archkeel/ir/codec_delta.py"] = (
        "from __future__ import annotations\nfrom .model import ComparisonStatus, RawJson\n"
        + _source_members("src/archkeel/ir/codec_delta.py", {"_parse_comparison_status"})
    )
    files["archkeel/ir/decisions.py"] = (
        "from __future__ import annotations\nfrom .model import ComparisonStatus\n"
        + _source_members("src/archkeel/ir/decisions.py", {"_named"})
    )
    for module, name, producer, *_ in CLAIMS:
        path = "src/" + module.__name__.replace(".", "/") + ".py"
        members = {name, producer} if producers else {name}
        files[path.removeprefix("src/")] = (
            prefix
            + "from .model import ComparisonStatus, Observation\n"
            + _source_members(path, members)
        )
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _valid(value):
    comparison = architecture_report(value).comparison
    assert comparison is not None and comparison.status == "PASS", [
        (row.subject_id, row.aspect, row.status, row.reason)
        for row in comparison.assessments
        if row.status != "PASS"
    ]
    assert not trace_valid_violations(value)


@pytest.mark.parametrize("producers", [False, True])
def test_native_actual_boundaries_and_all_five_producer_ports_match_fixed_intent(
    tmp_path, producers
):
    root, config = _repository(tmp_path, producers=producers)
    _valid(_model(root, config))


@pytest.mark.parametrize(
    ("path", "name"),
    [("model", "DimensionDelta"), ("model", "RatchetObservations")]
    + [(module.__name__.rsplit(".", 1)[-1], name) for module, name, *_ in CLAIMS],
)
def test_native_actual_status_field_widening_fails_independent_intent(tmp_path, path, name):
    root, config = _repository(tmp_path)
    _valid(_model(root, config))
    source = root / "archkeel/ir" / f"{path}.py"
    original = source.read_text()
    start, rest = original.split(f"class {name}:", 1)
    assert "status: ComparisonStatus" in rest
    intent = (root / "contract.json").read_bytes()
    source.write_text(
        start + f"class {name}:" + rest.replace("status: ComparisonStatus", "status: str", 1)
    )
    changed = _model(root, config)
    assert trace_valid_violations(changed)
    assert any(row.status == "FAIL" for row in architecture_report(changed).comparison.assessments)
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize(
    ("path", "old", "new"),
    [
        ("model", "class ComparisonStatus(StrEnum):", "class ComparisonStatus(str):"),
        ("codec_delta", ") -> ComparisonStatus:", ") -> str:"),
        ("decisions", "status: ComparisonStatus", "status: str"),
        ("decisions", ") -> int | None:", ") -> str:"),
    ],
)
def test_native_enum_parameter_and_return_widening_fail_fixed_target(tmp_path, path, old, new):
    root, config = _repository(tmp_path)
    _valid(_model(root, config))
    source = root / "archkeel/ir" / f"{path}.py"
    original = source.read_text()
    assert old in original
    intent = (root / "contract.json").read_bytes()
    source.write_text(original.replace(old, new, 1))
    assert trace_valid_violations(_model(root, config))
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize(("module", "name", "producer", "count", "noun"), CLAIMS)
def test_native_each_actual_producer_return_widening_fails_fixed_target(
    tmp_path, module, name, producer, count, noun
):
    root, config = _repository(tmp_path, producers=True)
    _valid(_model(root, config))
    source = root / Path(*module.__name__.split(".")).with_suffix(".py")
    original = source.read_text()
    assert f") -> {name}:" in original
    intent = (root / "contract.json").read_bytes()
    source.write_text(original.replace(f") -> {name}:", ") -> object:", 1))
    assert trace_valid_violations(_model(root, config))
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize(
    "path",
    ["model", "codec_delta", "decisions"]
    + [module.__name__.rsplit(".", 1)[-1] for module, *_ in CLAIMS],
)
@pytest.mark.parametrize(
    "probe",
    [
        'def _probe(value):\n    return value == "UNKNOWN"\n',
        'def _probe(value):\n    return value in {"SUPPORTED", "UNKNOWN"}\n',
        'def _probe(value):\n    match value:\n        case "UNKNOWN":\n            return True\n'
        "        case _:\n            return False\n",
        'from typing import Final\nSTATUS: Final[str] = "UNKNOWN"\n'
        "def _probe(value):\n    return value == STATUS\n",
    ],
)
def test_native_migrated_actual_boundary_projections_reject_raw_dispatch(tmp_path, path, probe):
    root, config = _repository(tmp_path)
    _valid(_model(root, config))
    source = root / "archkeel/ir" / f"{path}.py"
    intent = (root / "contract.json").read_bytes()
    source.write_text(source.read_text() + "\n" + probe)
    assert any(row.rule_ids for row in trace_valid_violations(_model(root, config)))
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize(
    ("path", "old", "new"),
    [
        ("model", "self.status is ComparisonStatus.SUPPORTED", 'self.status == "SUPPORTED"'),
        ("decisions", "status is ComparisonStatus.SUPPORTED", 'status == "SUPPORTED"'),
        (
            "codec_delta",
            "return ComparisonStatus(value)",
            'if value == "UNKNOWN":\n            return ComparisonStatus.UNKNOWN\n'
            "        return ComparisonStatus(value)",
        ),
    ]
    + [
        (
            module.__name__.rsplit(".", 1)[-1],
            "self.status is ComparisonStatus.UNKNOWN",
            'self.status == "UNKNOWN"',
        )
        for module, *_ in CLAIMS
    ],
)
def test_native_actual_invariant_and_decoder_raw_reversion_fails_fixed_guard(
    tmp_path, path, old, new
):
    root, config = _repository(tmp_path)
    _valid(_model(root, config))
    source = root / "archkeel/ir" / f"{path}.py"
    original = source.read_text()
    assert old in original
    intent = (root / "contract.json").read_bytes()
    source.write_text(original.replace(old, new, 1))
    assert any(row.rule_ids for row in trace_valid_violations(_model(root, config)))
    assert (root / "contract.json").read_bytes() == intent
