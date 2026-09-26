# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent #168 regressions for scope, evidence classification and flow verdicts."""

import json
from pathlib import Path

from test_analyzer import _component, _observe
from test_boundary_types_nested_dtos import _write_app
from test_inside_rule_coverage import _write_inside_case

from archkeel.check.run import inspect_observation
from archkeel.ir.model import Observation
from archkeel.ir.trace import trace_valid_violations, validate_evidence_classes
from archkeel.render.flow import build_flow


def _foreign_type_case(root: Path, *, api: str, origin: str, nested: bool) -> Observation:
    (root / "sample/core").mkdir(parents=True, exist_ok=True)
    (root / "sample/foreign").mkdir(parents=True, exist_ok=True)
    (root / "sample/core/api.py").write_text(api)
    (root / "sample/foreign/impl.py").write_text(origin)
    public = ["sample.core.api:run"]
    parent = _component("core", public=public)
    rule = {
        "id": "TYPES",
        "kind": "boundary_types",
        "source": "sample.core.api",
        "rationale": "Keep the declared facade typed.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    if nested:
        (root / "inner.json").write_text(
            json.dumps(
                {
                    "schema_version": "2.1.0",
                    "components": [_component("api", packages=["sample.core.api"], public=public)],
                    "rules": [rule],
                }
            )
        )
        parent = parent | {"inside": "inner.json"}
    (root / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [parent, _component("foreign", public=[])],
                "rules": [] if nested else [rule],
            }
        )
    )
    result = _observe(root)
    assert result.observation is not None, result.diagnostics
    validate_evidence_classes(result.observation)
    return result.observation


def test_inside_reexport_keeps_missing_annotation_from_global_origin(tmp_path: Path) -> None:
    api = 'from sample.foreign.impl import run\n__all__ = ["run"]\n'
    origin = "def run(payload) -> str:\n    return str(payload)\n"
    for nested in (False, True):
        observation = _foreign_type_case(tmp_path, api=api, origin=origin, nested=nested)
        rule_id = "core:TYPES" if nested else "TYPES"
        assert not trace_valid_violations(observation)
        assert any(
            item.kind == "boundary_type_position"
            and item.rule_ids == (rule_id,)
            and item.data.get("qualified_name") == "sample.core.api.run"
            for item in observation.records("unknowns") or ()
        )
        assert inspect_observation(observation)[1] == "UNKNOWN"


def test_inside_type_lookup_retains_foreign_owners_private_surface(tmp_path: Path) -> None:
    api = (
        "from sample.foreign.impl import Payload\n"
        '__all__ = ["run"]\n'
        "def run() -> Payload:\n    return Payload()\n"
    )
    origin = "class Payload:\n    value: str\n"
    for nested in (False, True):
        observation = _foreign_type_case(tmp_path, api=api, origin=origin, nested=nested)
        findings = trace_valid_violations(observation)
        assert len(findings) == 1
        assert "Payload which foreign does not declare" in findings[0].title
        assert findings[0].rule_ids == (("core:TYPES" if nested else "TYPES"),)
        assert inspect_observation(observation)[1] == "FAIL"


def test_inside_allowance_remains_a_fact_not_unknown(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        implementation=(
            "class Payload:\n    value: dict[str, str]\n"
            "def run() -> Payload:\n    return Payload()\n"
        ),
        declared=("sample.app.impl:Payload", "sample.app.impl:run"),
        allowed_positions=(
            {
                "qualified_name": "sample.app.impl.run",
                "position": "return",
                "field_path": "value",
                "annotation": "dict[str, str]",
            },
        ),
    )
    for nested in (False, True):
        if nested:
            (tmp_path / "inner.json").write_text((tmp_path / "contract.json").read_text())
            (tmp_path / "contract.json").write_text(
                json.dumps(
                    {
                        "schema_version": "2.1.0",
                        "components": [_component("app") | {"inside": "inner.json"}],
                        "rules": [],
                    }
                )
            )
        result = _observe(tmp_path)
        assert result.observation is not None, result.diagnostics
        observation = result.observation
        assert not trace_valid_violations(observation)
        allowance_sections = [
            section.name
            for section in observation.sections
            for item in section.records
            if item.kind == "boundary_type_allowance"
        ]
        assert allowance_sections == ["typing_signals"]
        measured, verdict = inspect_observation(observation)
        assert measured.scalars.unknown_positions == 0
        assert verdict == "PASS"


def test_inner_module_cycle_overrides_positive_requires_receipts(tmp_path: Path) -> None:
    metadata = {
        "rationale": "Check the declared inner dependencies.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    _write_inside_case(
        tmp_path,
        b_requires=["a"],
        rules=[
            metadata | {"id": "REQ", "kind": "complete_requires"},
            metadata | {"id": "CYCLE", "kind": "no_component_cycles", "level": "module"},
        ],
    )
    (tmp_path / "sample/core/a.py").write_text("import sample.core.b\n")
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    observation = result.observation
    findings = trace_valid_violations(observation)
    assert [(item.kind, item.rule_ids) for item in findings] == [("module_cycle", ("core:CYCLE",))]
    inside = next(
        item.inside for item in build_flow(observation).components if item.label == "core"
    )
    assert inside is not None
    assert {(edge.source, edge.target) for edge in inside.edges} == {("a", "b"), ("b", "a")}
    assert all(
        edge.state == "violation" and edge.rule_ids == ("core:CYCLE",) for edge in inside.edges
    )
