# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Inherited findings keep source identity and name their proven concrete types."""

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _observe
from test_html_report import _native_details
from test_inside_publication import _rule, _write_project

from archkeel.ir.baseline import ViolationFingerprint, violation_fingerprint
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import stable_id
from archkeel.ir.trace import trace_valid_violations
from fixtures.architecture_demo import main as demo_main


def _inherited_result(
    root: Path, annotation: str, *, declared: bool = False, ambiguous: bool = False
):
    _write_project(
        root,
        components=[
            _component("app", packages=["sample.api"], public=["sample.api:Child"]),
            _component(
                "models",
                packages=["sample.models"],
                public=["sample.models:Payload"] if declared else [],
            ),
        ],
        rules=[_rule("TYPES", "boundary_types", source="sample.api")],
        insides={},
        files={
            "sample/models.py": "class Payload: pass\n"
            + ("class Payload: pass\n" if ambiguous else ""),
            "sample/api.py": (
                "from typing import Generic, TypeVar\n"
                "from sample.models import Payload\n"
                "T = TypeVar('T')\n"
                "class Base(Generic[T]):\n"
                f"    def get(self) -> {annotation}: ...\n"
                "class Child(Base[Payload]):\n"
                "    pass\n"
            ),
        },
    )
    result = _observe(root)
    assert result.observation is not None, result.diagnostics
    return result.observation


@pytest.mark.parametrize("annotation", ["T", "list[T]"])
def test_inherited_finding_names_concrete_origin_without_changing_source_or_identity(
    tmp_path: Path, annotation: str
) -> None:
    observation = _inherited_result(tmp_path, annotation)
    [finding] = trace_valid_violations(observation)
    symbols = observation.records("symbols") or ()
    child = next(item for item in symbols if item.data.get("qualified_name") == "sample.api.Child")
    method = next(
        item for item in symbols if item.data.get("qualified_name") == "sample.api.Base.get"
    )

    assert finding.data.get("annotation") == annotation
    assert method.data.get("returns") == annotation
    assert finding.id == stable_id("VIO", "TYPES", child.id, "return", method.id)
    assert violation_fingerprint(finding) == ViolationFingerprint(
        ("TYPES",), ("sample.api", "sample.api.Child.get")
    )
    assert finding.data.get("resolved_types") == ("sample.models:Payload",)
    assert "sample.models:Payload" in finding.title
    assert f"returns {annotation}" in finding.title


@pytest.mark.parametrize("annotation", ["T", "list[T]"])
def test_declaring_the_concrete_type_clears_the_inherited_violation(
    tmp_path: Path, annotation: str
) -> None:
    observation = _inherited_result(tmp_path, annotation, declared=True)

    assert trace_valid_violations(observation) == ()


@pytest.mark.parametrize("annotation", ["T", "list[T]"])
def test_ambiguous_substitution_stays_unknown_without_a_concrete_origin(
    tmp_path: Path, annotation: str
) -> None:
    observation = _inherited_result(tmp_path, annotation, ambiguous=True)

    assert trace_valid_violations(observation) == ()
    unknowns = [
        item for item in observation.records("unknowns") or () if item.rule_ids == ("TYPES",)
    ]
    assert any(item.data.get("reason") == "inherited_surface" for item in unknowns)
    assert all(
        item.data.get("resolved_types") is None and "sample.models:Payload" not in item.title
        for item in unknowns
    )


@pytest.mark.parametrize(
    ("variant_id", "annotation"),
    [
        ("class-a-inherited-generic-undeclared-return", "T"),
        ("class-a-inherited-generic-undeclared-batch", "list[T]"),
    ],
)
def test_cli_and_html_report_keep_the_inherited_concrete_origin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], variant_id: str, annotation: str
) -> None:
    output = tmp_path / f"{variant_id}.json"

    assert demo_main(["--replay", variant_id, "--output", str(output)]) == 2
    validation, report = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert validation["exit_code"] == 2
    assert report["exit_code"] == 0
    observation = parse_observation(decode_canonical_model(json.loads(output.read_text())))
    [finding] = trace_valid_violations(observation)
    assert finding.data.get("annotation") == annotation
    assert finding.data.get("resolved_types") == ("shop.app.payloads:Payload",)
    assert "shop.app.payloads:Noise" not in finding.title
    details = _native_details(output, observation)
    assert any(
        item.id == finding.id and item.title == finding.title and item.status == "FAIL"
        for detail in details
        for item in detail.findings
    )
