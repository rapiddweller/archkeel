# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Private boundary reasons are nominal; historical wire reasons stay open."""

import copy
import json
from dataclasses import FrozenInstanceError, replace
from enum import StrEnum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_delta import _model as wire_model
from test_delta import _record

from archkeel.check.evaluation import boundary_types as boundary
from archkeel.check.evaluation import rules
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.run import inspect_observation
from archkeel.cli.observe import observe
from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model, parse_observation
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
REASONS = (
    "missing_annotation",
    "inherited_surface",
    "forward_reference",
    "dotted_name",
    "generic",
    "union",
    "ambiguous_binding",
    "ambiguous_facade",
    "unresolved_name",
    "external_type",
    "nested_type",
    "other",
)


def _reason_type():
    reason = getattr(boundary, "_UndecidableReason", None)
    assert reason is not None, "the existing boundary owner must own its reason type"
    assert issubclass(reason, StrEnum)
    return reason


def test_private_position_field_and_classifier_expose_the_owned_reason():
    reason = _reason_type()
    assert get_type_hints(boundary._Position)["undecidable"] == reason | None
    assert get_type_hints(boundary._unresolvable_shape)["return"] is reason


@pytest.mark.parametrize("spelling", REASONS)
def test_valid_legacy_reason_normalizes_once_and_replace_stays_nominal(spelling):
    reason = _reason_type()
    position = boundary._Position(undecidable=spelling)
    assert position.undecidable is reason(spelling)
    assert replace(position, violation="independent diagnostic").undecidable is reason(spelling)
    assert replace(position, undecidable="other").undecidable is reason.OTHER
    assert replace(position, undecidable=None).undecidable is None


@pytest.mark.parametrize("spelling", ["future_reason", "", "GENERIC"])
def test_private_position_rejects_unknown_reason_instead_of_another_known_reason(spelling):
    with pytest.raises(ValueError):
        boundary._Position(undecidable=spelling)


@pytest.mark.parametrize(
    "annotation,spelling",
    [("pkg.Type", "dotted_name"), ("List[int]", "generic"), ("A | B", "union"), ("?", "other")],
)
def test_fallback_classifier_returns_actual_owned_members(annotation, spelling):
    assert boundary._unresolvable_shape(annotation) is _reason_type()(spelling)


def test_none_frozen_slots_and_open_diagnostic_text_keep_existing_meaning():
    position = boundary._Position(violation="written diagnostic", unknown_context="future:detail")
    assert position.undecidable is None
    assert position.violation == "written diagnostic"
    assert position.unknown_context == "future:detail"
    assert not hasattr(position, "__dict__")
    with pytest.raises(FrozenInstanceError):
        position.undecidable = None


def test_legacy_facade_keys_are_plain_strings_in_the_existing_order():
    assert boundary._UNDECIDABLE_KINDS == REASONS
    assert all(type(key) is str for key in boundary._UNDECIDABLE_KINDS)
    assert rules._UNDECIDABLE_KINDS is boundary._UNDECIDABLE_KINDS
    assert rules._Position is boundary._Position


def test_unknown_future_wire_reason_keeps_exact_text_and_conservative_verdict():
    detail = dict(
        module="sample.api",
        qualified_name="sample.api.load",
        position="return",
        annotation="Opaque",
        reason="future:reason",
        occurrence=0,
    )
    position = _record(
        "POSITION", kind="boundary_type_position", evidence_class="UNKNOWN", data=detail
    )
    limit = _record(
        "LIMIT",
        kind="boundary_type_limit",
        evidence_class="UNKNOWN",
        data=dict(
            positions=1,
            decided=0,
            undecided=1,
            undecidable_positions=[detail],
            **{"future:reason": 1},
        ),
    )
    position["rule_ids"] = limit["rule_ids"] = ["BOUNDARY"]
    declaration = _record("BOUNDARY", kind="boundary_types", evidence_class="DECLARED_RULE")
    declaration["provenance"] = ["contract.json"]
    observation = parse_observation(
        wire_model(git_head="a" * 40, declarations=[declaration], unknowns=[position, limit])
    )
    assert inspect_observation(observation)[1] == "UNKNOWN"
    encoded = canonical_report_bytes(observation)
    replay = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert canonical_report_bytes(replay) == encoded
    actual = {record.id: record for record in replay.records("unknowns")}
    assert actual["POSITION"].data.get("reason") == "future:reason"
    assert actual["LIMIT"].data.get("future:reason") == 1


def _repository(tmp_path):
    target = copy.deepcopy(
        json.loads((ROOT / "docs/architecture/contracts/check.json").read_text())
    )
    target.pop("$schema", None)
    target["rules"] = []
    target["declarations"]["modules"] = []
    target["declarations"]["uml"]["relationships"] = []
    target["declarations"]["uml"]["scopes"] = []
    target["declarations"]["uml"]["entities"] = [
        row
        for row in target["declarations"]["uml"]["entities"]
        if row["id"].startswith("BOUNDARY-")
    ]
    files = {
        "archkeel/__init__.py": "",
        "archkeel/check/__init__.py": "",
        "archkeel/check/evaluation/__init__.py": "",
        "archkeel/check/evaluation/boundary_types.py": (
            ROOT / "src/archkeel/check/evaluation/boundary_types.py"
        ).read_text(),
        "contract.json": json.dumps(target),
        "docs/architecture/boundary-reason-types.md": "Owned boundary reason intent.\n",
        "docs/architecture/language-adapter-target.md": "Existing Core owners.\n",
    }
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _model(root, config):
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert result.exit_code == 0 and encoded is not None, result.diagnostics
    return parse_observation(decode_canonical_model(json.loads(encoded)))


def _comparison(model):
    report = architecture_report(model)
    assert report.comparison is not None
    return report.comparison


def test_native_real_private_ports_match_the_independent_target(tmp_path):
    root, config = _repository(tmp_path)
    comparison = _comparison(_model(root, config))
    assert comparison.status == "PASS", [
        (row.subject_id, row.aspect, row.status, row.evidence_ids)
        for row in comparison.assessments
        if row.status != "PASS"
    ]


@pytest.mark.parametrize(
    "old,new",
    [
        ("undecidable: _UndecidableReason | None", "undecidable: str | None"),
        (
            "def _unresolvable_shape(annotation: str) -> _UndecidableReason:",
            "def _unresolvable_shape(annotation: str) -> str:",
        ),
    ],
)
def test_native_real_port_widening_fails_the_unchanged_target(tmp_path, old, new):
    root, config = _repository(tmp_path)
    source = root / "archkeel/check/evaluation/boundary_types.py"
    before = source.read_text()
    assert old in before, "the actual owned field/return port must exist"
    target = (root / "contract.json").read_bytes()
    source.write_text(before.replace(old, new, 1))
    observed = _model(root, config)
    comparison = _comparison(observed)
    assert any(
        row.status == "FAIL" and row.aspect in {"annotation", "signature"}
        for row in comparison.assessments
    ), comparison
    assert trace_valid_violations(observed)
    assert (root / "contract.json").read_bytes() == target

def _placement_model(tmp_path, *, unrelated):
    root, config = _repository(tmp_path)
    target_path = root / "contract.json"
    target = json.loads(target_path.read_text())
    root_policy = json.loads((ROOT / "architecture-contract.json").read_text())
    target["rules"] = [
        row for row in root_policy["rules"] if row["id"] == "TYPES-ENUM-IN-MODEL"
    ]
    assert len(target["rules"]) == 1
    target_path.write_text(json.dumps(target))
    if unrelated:
        (root / "archkeel/check/evaluation/unrelated.py").write_text(
            "from enum import StrEnum\nclass Unrelated(StrEnum):\n    VALUE = 'value'\n"
        )
    return _model(root, config)


def test_native_placement_policy_accepts_the_actual_private_reason_owner(tmp_path):
    model = _placement_model(tmp_path, unrelated=False)
    assert not trace_valid_violations(model)


def test_native_placement_policy_still_rejects_an_unrelated_check_owner(tmp_path):
    model = _placement_model(tmp_path, unrelated=True)
    found = [
        row
        for row in trace_valid_violations(model)
        if row.data.get("qualified_name") == "archkeel.check.evaluation.unrelated.Unrelated"
    ]
    assert len(found) == 1
    assert found[0].rule_ids == ("TYPES-ENUM-IN-MODEL",)
    cited = {e.id: e for e in model.evidence}
    assert any(
        cited[e].file == "archkeel/check/evaluation/unrelated.py" for e in found[0].evidence_ids
    )
