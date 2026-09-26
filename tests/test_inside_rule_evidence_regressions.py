# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent #168 regressions for scope, evidence classification and flow verdicts."""

import json
from pathlib import Path

from test_analyzer import _component, _observe
from test_boundary_types_nested_dtos import _write_app
from test_inside_rule_coverage import _commit_test_root, _scan_config, _write_inside_case

from archkeel.check.run import inspect_observation
from archkeel.check.validation import COMPONENT_GRAPH_MARKER
from archkeel.cli import main
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


def test_inside_boundary_rule_does_not_judge_foreign_public_functions(tmp_path: Path) -> None:
    (tmp_path / "sample/core").mkdir(parents=True)
    (tmp_path / "sample/foreign").mkdir(parents=True)
    (tmp_path / "sample/core/api.py").write_text(
        '__all__ = ["run"]\ndef run(value: str) -> str:\n    return value\n'
    )
    (tmp_path / "sample/foreign/impl.py").write_text("def foreign(value):\n    return value\n")
    (tmp_path / "inner.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _component(
                        "api",
                        packages=["sample.core"],
                        public=["sample.core.api:run"],
                    )
                ],
                "rules": [
                    {
                        "id": "TYPES",
                        "kind": "boundary_types",
                        "source": "sample",
                        "rationale": "Keep the inside facade typed.",
                        "provenance": ["docs/architecture/sample.md"],
                        "decided_by": "architect",
                    }
                ],
            }
        )
    )
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _component("core", public=["sample.core.api:run"]) | {"inside": "inner.json"},
                    _component("foreign", public=["sample.foreign.impl:foreign"]),
                ],
                "rules": [],
            }
        )
    )

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    assert not any(
        item.rule_ids == ("core:TYPES",) and item.data.get("module") == "sample.foreign.impl"
        for item in result.observation.records("unknowns") or ()
    )


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


def test_inside_forbidden_construct_matches_function_and_method_owners(tmp_path: Path) -> None:
    _write_inside_case(
        tmp_path,
        rules=[
            {
                "id": "NO-EVAL",
                "kind": "forbidden_construct",
                "source": "sample.core.a",
                "constructs": ["eval"],
                "rationale": "Keep dynamic evaluation out of the inside.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )
    (tmp_path / "sample/core/a.py").write_text(
        "def function():\n    return eval('1')\n\n"
        "class Service:\n    def method(self):\n        return eval('2')\n"
    )

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    findings = [
        item
        for item in trace_valid_violations(result.observation)
        if item.rule_ids == ("core:NO-EVAL",)
    ]
    assert len(findings) == 2
    assert {subject for item in findings for subject in item.subjects} == {
        "sample.core.a.function",
        "sample.core.a.Service.method",
    }


def test_validate_keeps_known_violations_with_missing_inside_diagnostics(
    tmp_path: Path, capsys
) -> None:
    _write_inside_case(tmp_path, rules=[])
    contract_path = tmp_path / "contract.json"
    contract = json.loads(contract_path.read_text())
    contract["components"][0]["inside"] = "missing.json"
    contract["components"].append(_component("foreign"))
    contract["rules"] = [
        {
            "id": "NO-FOREIGN",
            "kind": "forbidden_dependency",
            "source": "sample.core",
            "target": "sample.foreign",
            "include_type_checking": True,
            "rationale": "Keep core independent of foreign.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
    ]
    contract_path.write_text(json.dumps(contract))
    (tmp_path / "sample/core/a.py").write_text("import sample.foreign.api\n")
    foreign = tmp_path / "sample/foreign"
    foreign.mkdir()
    (foreign / "__init__.py").write_text("")
    (foreign / "api.py").write_text("VALUE = 1\n")
    docs = tmp_path / "docs/architecture"
    docs.mkdir(parents=True)
    (docs / "sample.md").write_text(
        f"# Sample architecture\n\n{COMPONENT_GRAPH_MARKER}\n"
        "```mermaid\ngraph TD\n  stale --> edge\n```\n"
    )
    (tmp_path / "baseline.json").write_text(
        json.dumps({"schema_version": "1.3.0", "budgets": {}, "violations": []})
    )
    _scan_config(tmp_path)
    _commit_test_root(tmp_path)

    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(tmp_path).parts
    }
    exit_code = main(
        [
            "validate",
            "--root",
            str(tmp_path),
            "--baseline",
            "baseline.json",
            "--write-baseline",
            "--accept-new",
            "--write-graph",
            "--json",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(tmp_path).parts
    }

    assert exit_code == 2
    assert after == before
    assert result["declared_rules"] == "UNKNOWN"
    diagnostics = result["diagnostics"]
    assert diagnostics
    assert any(item.get("code") == "contract.invalid" for item in diagnostics)
    assert any(
        item.get("code") == "rule.violated" and item["subject"] == "NO-FOREIGN"
        for item in diagnostics
    ), diagnostics
