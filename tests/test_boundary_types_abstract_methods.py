# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Stdlib abstract methods preserve visible signatures without proving custom decorators."""

import json
from pathlib import Path

import pytest
from test_analyzer import _component
from test_inside_publication import _rule, _write_project
from test_recursive_inside_independent_contracts import _commit_tree, _scan_config

from archkeel.analyzer import observe
from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.ir.codec import (
    decode_canonical_model,
    parse_observation,
    result_payload,
)
from archkeel.ir.trace import trace_valid_violations


def _validate_abstract_boundary(root: Path, source: str):
    _write_project(
        root,
        components=[
            _component("api", packages=["sample"], public=["sample.api:Base", "sample.api:Child"])
        ],
        rules=[_rule("TYPES", "boundary_types", source="sample.api")],
        insides={},
        files={"sample/api.py": source},
    )
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "docs/architecture/sample.md").write_text(
        "<!-- archkeel-component-graph -->\n```mermaid\ngraph TD\n```\n"
    )
    _commit_tree(root)
    result, _ = run_validate(root, _scan_config(), observe)
    report, artifact = run_report(root, config=_scan_config(), analyzer=observe)
    assert artifact is not None, report.diagnostics
    observation = parse_observation(decode_canonical_model(json.loads(artifact)))
    payload = result_payload(report)
    unknowns = [
        item
        for item in observation.records("unknowns") or ()
        if item.kind == "boundary_type_position" and item.rule_ids == ("TYPES",)
    ]
    assert report.measurements is not None
    assert report.measurements.scalars.unknown_positions == len(unknowns)
    assert payload["measurements"]["scalars"]["unknown_positions"] == len(unknowns)
    [assessment] = report.rule_assessments or ()
    assert assessment.undecided == len(unknowns)
    assert payload["rule_assessments"][0]["undecided"] == len(unknowns)
    assert payload["declared_rules"] == report.declared_rules == assessment.status
    if trace_valid_violations(observation):
        assert report.declared_rules == "FAIL"
    if result.exit_code == 0:
        assert result.declared_rules == report.declared_rules
    return result, observation, unknowns


@pytest.mark.parametrize(
    ("imports", "base", "decorator"),
    [
        ("from abc import ABC, abstractmethod\n", "ABC", "abstractmethod"),
        ("from abc import ABC as Abstract, abstractmethod as abstract\n", "Abstract", "abstract"),
    ],
)
@pytest.mark.parametrize("override", [False, True])
def test_visible_abstract_signature_and_typed_override_pass_full_validate(
    tmp_path: Path, imports: str, base: str, decorator: str, override: bool
) -> None:
    result, observation, unknowns = _validate_abstract_boundary(
        tmp_path,
        imports
        + f"class Base({base}):\n"
        + f"    @{decorator}\n"
        + "    def convert(self, value: str) -> str:\n"
        + "        raise NotImplementedError\n"
        + "class Child(Base):\n"
        + (
            "    def convert(self, value: str) -> str:\n        return value.lower()\n"
            if override
            else "    pass\n"
        ),
    )

    assert result.exit_code == 0, result.diagnostics
    assert result.declared_rules == "PASS"
    assert unknowns == []
    assert trace_valid_violations(observation) == ()


@pytest.mark.parametrize("descriptor", ["staticmethod", "classmethod"])
def test_abstractmethod_preserves_one_builtin_descriptor(tmp_path: Path, descriptor: str) -> None:
    receiver = "" if descriptor == "staticmethod" else "cls, "
    result, _, unknowns = _validate_abstract_boundary(
        tmp_path,
        "from abc import ABC, abstractmethod\n"
        "class Base(ABC):\n"
        f"    @{descriptor}\n"
        "    @abstractmethod\n"
        f"    def convert({receiver}value: str) -> str: ...\n"
        "class Child(Base):\n"
        "    pass\n",
    )

    assert result.exit_code == 0, result.diagnostics
    assert result.declared_rules == "PASS"
    assert unknowns == []


@pytest.mark.parametrize("annotation", ["Hidden", "dict"])
def test_inherited_abstract_return_still_fails_for_private_or_broad_types(
    tmp_path: Path, annotation: str
) -> None:
    result, observation, unknowns = _validate_abstract_boundary(
        tmp_path,
        "from abc import ABC, abstractmethod\n"
        "class Hidden: pass\n"
        "class Base(ABC):\n"
        "    @abstractmethod\n"
        f"    def convert(self, value: str) -> {annotation}: ...\n"
        "class Child(Base):\n"
        "    pass\n",
    )

    assert result.exit_code == 2
    assert unknowns == []
    assert any(
        item.data.get("qualified_name") == "sample.api.Child.convert"
        and item.data.get("position") == "return"
        for item in trace_valid_violations(observation)
    )


@pytest.mark.parametrize(
    "source",
    [
        "def abstractmethod(method): return method\nclass Base:\n    @abstractmethod\n"
        "    def convert(self, value: str) -> str: ...\n",
        "from abc import ABC, abstractmethod\nabstractmethod = custom\nclass Base(ABC):\n"
        "    @abstractmethod\n    def convert(self, value: str) -> str: ...\n",
        "from abc import ABC, abstractmethod\nclass Base(ABC):\n"
        "    abstractmethod = custom\n    @abstractmethod\n"
        "    def convert(self, value: str) -> str: ...\n",
        "import abc\nabc.abstractmethod = custom\nclass Base(abc.ABC):\n"
        "    @abc.abstractmethod\n    def convert(self, value: str) -> str: ...\n",
        "class Base:\n    @abstractmethod\n    def convert(self, value: str) -> str: ...\n"
        "from abc import abstractmethod\n",
        "from abc import ABC, abstractmethod\nclass Base(ABC):\n"
        "    @abstractmethod()\n    def convert(self, value: str) -> str: ...\n",
        "from abc import ABC, abstractmethod\nclass Base(ABC):\n"
        "    @custom\n    @abstractmethod\n    def convert(self, value: str) -> str: ...\n",
        "from abc import ABC, abstractmethod\nclass Base(ABC):\n"
        "    if flag:\n        convert = custom\n"
        "    @abstractmethod\n    def convert(self, value: str) -> str: ...\n",
        "from abc import ABC, abstractmethod\nclass Base(ABC):\n"
        "    def __init_subclass__(cls): mutate(cls)\n"
        "    @abstractmethod\n    def convert(self, value: str) -> str: ...\n",
        "from abc import abstractmethod\nclass Base(Unknown):\n"
        "    @abstractmethod\n    def convert(self, value: str) -> str: ...\n",
        "import abc as abstract\nclass Base(abstract.ABC):\n"
        "    @abstract.abstractmethod\n    def convert(self, value: str) -> str: ...\n",
    ],
    ids=[
        "local-decorator",
        "rebound-import",
        "class-shadow",
        "module-attribute-write",
        "late-import",
        "called-decorator",
        "custom-stack",
        "conditional-class-body",
        "class-mutation",
        "unresolved-base",
        "unproven-module-member-route",
    ],
)
def test_unproven_abstract_surface_stays_unknown(tmp_path: Path, source: str) -> None:
    result, observation, unknowns = _validate_abstract_boundary(
        tmp_path, source + "class Child(Base):\n    pass\n"
    )

    assert result.exit_code == 0, result.diagnostics
    assert result.declared_rules == "UNKNOWN"
    assert trace_valid_violations(observation) == ()
    assert any(
        item.data.get("qualified_name") == "sample.api.Child.__inherited_methods__"
        and item.data.get("reason") == "inherited_surface"
        for item in unknowns
    )
