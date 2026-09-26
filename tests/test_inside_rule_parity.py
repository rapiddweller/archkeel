# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Moving a rule into an inside contract must not erase its proven findings."""

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _inside_component, _observe

from archkeel.ir.trace import trace_valid_violations


@pytest.mark.parametrize(
    "rule",
    [
        {"kind": "complete_requires"},
        {
            "kind": "forbidden_dependency",
            "source": "sample.core.a",
            "target": "sample.core.b",
            "include_type_checking": True,
        },
        {"kind": "forbidden_construct", "source": "sample.core", "constructs": ["eval"]},
        {
            "kind": "external_dependency_scope",
            "dependency": "json",
            "allowed_sources": ["sample.core.b"],
        },
        {"kind": "complete_external_scope", "source": "sample.core"},
        {"kind": "complete_assignment", "source": "sample.core"},
        {
            "kind": "root_layout",
            "root": "sample.core",
            "allowed_children": ["sample.core.a", "sample.core.b"],
        },
        {"kind": "no_component_cycles"},
        {"kind": "no_component_cycles", "level": "module"},
        {"kind": "interface_boundary"},
        {"kind": "sibling_isolation", "members": ["sample.core.a", "sample.core.b"]},
        {
            "kind": "symbol_placement",
            "source": "sample.core",
            "class_kinds": ["class"],
            "exact_sources": ["sample.core.b"],
        },
        {"kind": "boundary_types", "source": "sample.core.a"},
    ],
    ids=lambda rule: str(rule["kind"]) + str(rule.get("level", "")),
)
def test_inside_rule_preserves_top_level_findings(tmp_path: Path, rule: dict[str, object]) -> None:
    package = tmp_path / "sample/core"
    package.mkdir(parents=True)
    (tmp_path / "sample/__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    (package / "a.py").write_text(
        "from sample.core.b import _hidden\n"
        "import json\nimport external_probe_library\n"
        "VALUE = eval('1')\n"
        "class Misplaced:\n    pass\n"
        "def run() -> dict:\n    return {}\n"
    )
    (package / "b.py").write_text(
        "from sample.core.a import run\n_hidden = 1\ndef public() -> str:\n    return 'ok'\n"
    )
    (package / "extra.py").write_text("VALUE = 1\n")
    decision = {
        "id": "PROBE",
        "rationale": "Exercise the same rule at both contract levels.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
        **rule,
    }
    inner = {
        "schema_version": "2.1.0",
        "components": [
            _inside_component("a", []) | {"public": ["sample.core.a:run"]},
            _inside_component("b", []) | {"public": ["sample.core.b:public"]},
        ],
        "rules": [decision],
    }
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(inner))
    top = _observe(tmp_path)
    assert top.observation is not None, top.diagnostics
    top_findings = trace_valid_violations(top.observation)
    assert top_findings, "The control must prove this rule detects the fixture violation"

    (tmp_path / "inner.json").write_text(json.dumps(inner))
    contract_path.write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_component("core") | {"inside": "inner.json"}],
                "rules": [],
            }
        )
    )
    nested = _observe(tmp_path)
    assert nested.observation is not None, nested.diagnostics
    nested_findings = trace_valid_violations(nested.observation)
    assert sorted((item.kind, item.subjects) for item in nested_findings) == sorted(
        (item.kind, item.subjects) for item in top_findings
    )
    assert all(item.rule_ids == ("core:PROBE",) for item in nested_findings)
