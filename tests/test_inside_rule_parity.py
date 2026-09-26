# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Moving a rule into an inside contract must not erase its proven findings."""

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _inside_component, _observe

from archkeel.check.ports import ScanConfig
from archkeel.check.validation import inside_diagnostics
from archkeel.ir.codec import parse_contract
from archkeel.ir.trace import trace_valid_violations

_INTERFACE_RULE = {
    "id": "INTERFACE",
    "kind": "interface_boundary",
    "rationale": "Keep each level's declared public names in use.",
    "provenance": ["docs/architecture/sample.md"],
    "decided_by": "architect",
}


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


def test_nested_public_is_local_and_parent_public_remains_outward(tmp_path: Path) -> None:
    package = tmp_path / "sample/core"
    (package / "a").mkdir(parents=True)
    (package / "b").mkdir()
    (tmp_path / "sample/cli").mkdir(parents=True)
    docs = tmp_path / "docs/architecture"
    docs.mkdir(parents=True)
    (docs / "sample.md").write_text("Decision.\n")
    (tmp_path / "sample/__init__.py").touch()
    (package / "__init__.py").touch()
    (package / "a/__init__.py").touch()
    (package / "b/__init__.py").touch()
    (tmp_path / "sample/cli/__init__.py").touch()
    (package / "api.py").write_text("def entry() -> str:\n    return 'ok'\n")
    (package / "a/client.py").write_text(
        "from sample.core.b.api import helper\n\ndef run() -> str:\n    return helper()\n"
    )
    (package / "b/api.py").write_text("def helper() -> str:\n    return 'ok'\n")
    (tmp_path / "sample/cli/client.py").write_text(
        "from sample.core.api import entry\n\nVALUE = entry()\n"
    )

    parent = _component(
        "core",
        packages=["sample.core"],
        public=["sample.core.api:entry"],
    ) | {"inside": "inner.json"}
    cli = _component("cli", packages=["sample.cli"], public=[])
    inner = {
        "schema_version": "2.1.0",
        "components": [
            _inside_component("a", []) | {"public": []},
            _inside_component("b", []) | {"public": ["sample.core.b.api:helper"]},
        ],
        "rules": [_INTERFACE_RULE],
    }
    contract = {
        "schema_version": "2.1.0",
        "components": [parent, cli],
        "rules": [_INTERFACE_RULE],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "inner.json").write_text(json.dumps(inner))
    config = ScanConfig(("sample",), "sample", "contract.json", "0" * 64)

    observed = _observe(tmp_path)
    assert observed.observation is not None, observed.diagnostics
    assert trace_valid_violations(observed.observation) == ()
    parsed = parse_contract(contract)
    assert inside_diagnostics(tmp_path, parsed, config) == ()

    inner["components"][1]["public"] = ["sample.core.b.api.missing:helper"]
    (tmp_path / "inner.json").write_text(json.dumps(inner))
    observed = _observe(tmp_path)
    assert observed.observation is not None, observed.diagnostics
    missing = inside_diagnostics(tmp_path, parsed, config, observation=observed.observation)
    assert any(item.code == "interface.missing" for item in missing)

    inner["rules"] = []
    (tmp_path / "inner.json").write_text(json.dumps(inner))
    observed = _observe(tmp_path)
    assert observed.observation is not None, observed.diagnostics
    no_interface_rule = inside_diagnostics(
        tmp_path, parsed, config, observation=observed.observation
    )
    assert not any(item.code == "interface.missing" for item in no_interface_rule)

    inner["components"][1]["public"] = []
    inner["rules"] = [_INTERFACE_RULE]
    (tmp_path / "inner.json").write_text(json.dumps(inner))
    observed = _observe(tmp_path)
    assert observed.observation is not None, observed.diagnostics
    assert any(
        item.rule_ids == ("core:INTERFACE",)
        for item in trace_valid_violations(observed.observation)
    )

    inner["components"][1]["public"] = ["sample.core.b.api:helper"]
    parent["public"] = []
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "inner.json").write_text(json.dumps(inner))
    observed = _observe(tmp_path)
    assert observed.observation is not None, observed.diagnostics
    assert any(
        item.rule_ids == ("INTERFACE",) for item in trace_valid_violations(observed.observation)
    )
