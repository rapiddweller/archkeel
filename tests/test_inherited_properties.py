# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Inherited properties retain both accessor signatures without proving custom descriptors."""

import json
from pathlib import Path

import pytest
from test_analyzer import _component
from test_inside_publication import _rule, _write_project
from test_recursive_inside_independent_contracts import _commit_tree, _scan_config

from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.trace import trace_valid_violations


def _validate(root: Path, source: str, extra: dict[str, str] | None = None):
    _write_project(
        root,
        components=[_component("api", packages=["sample"], public=["sample.api:Child"])],
        rules=[_rule("TYPES", "boundary_types", source="sample.api")],
        insides={},
        files={"sample/api.py": source, **(extra or {})},
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
    assert observation.coverage.status == "PASS"
    assert report.measurements is not None
    return result, report, observation


def _property(getter: str = "int", setter: str = "int") -> str:
    return (
        "class Hidden: pass\nclass Base:\n"
        f"    @property\n    def value(self) -> {getter}: ...\n"
        f"    @value.setter\n    def value(self, new_value: {setter}) -> None: ...\n"
        "class Child(Base):\n    pass\n"
    )


def test_inherited_property_inspects_both_accessors(tmp_path: Path) -> None:
    result, report, observation = _validate(tmp_path, _property())
    assert result.exit_code == 0
    assert report.declared_rules == "PASS"
    assert report.measurements.scalars.unknown_positions == 0
    assert trace_valid_violations(observation) == ()


@pytest.mark.parametrize("annotation", ["object", "Hidden"])
@pytest.mark.parametrize("accessor,position", [("getter", "return"), ("setter", "new_value")])
def test_inherited_accessor_keeps_broad_and_private_types_visible(
    tmp_path: Path, annotation: str, accessor: str, position: str
) -> None:
    source = _property(**{accessor: annotation})
    result, report, observation = _validate(tmp_path, source)
    assert result.exit_code == 2
    assert report.declared_rules == "FAIL"
    assert report.measurements.scalars.unknown_positions == 0
    violations = trace_valid_violations(observation)
    assert any(
        item.data.get("qualified_name") == "sample.api.Child.value"
        and item.data.get("position") == position
        and item.data.get("annotation") == annotation
        for item in violations
    )


@pytest.mark.parametrize(
    "source",
    [
        "property = custom\n" + _property(),
        _property().replace("class Base:\n", "class Base:\n    property = custom\n"),
        _property().replace("@property", "@custom"),
        _property().replace("@value.setter", "@custom\n    @value.setter"),
        _property().replace("@value.setter", "@value.setter()"),
        _property().replace("@value.setter", "@other.setter"),
        _property().replace("    @value.setter", "    value = custom\n    @value.setter"),
        _property().replace("class Child(Base):", "Base.value = custom\nclass Child(Base):"),
        _property().replace("class Base:", "class Base(Missing):"),
        _property().replace("    @value.setter", "    @value.setter\n    @staticmethod"),
    ],
)
def test_unproven_descriptor_binding_stays_unknown(tmp_path: Path, source: str) -> None:
    _, report, observation = _validate(tmp_path, source)
    assert report.declared_rules == "UNKNOWN"
    assert report.measurements.scalars.unknown_positions > 0
    assert trace_valid_violations(observation) == ()


@pytest.mark.parametrize(
    "replacement,expected",
    [
        ("    @Base.value.getter\n    def value(self) -> int: ...\n", "FAIL"),
        ("    @property\n    def value(self) -> int: ...\n", "PASS"),
        ("    @Base.value.setter\n    def value(self, new_value: int) -> None: ...\n", "PASS"),
    ],
)
def test_copied_and_fresh_property_overrides_have_different_setters(
    tmp_path: Path, replacement: str, expected: str
) -> None:
    source = _property(setter="Hidden").replace(
        "class Child(Base):\n    pass\n", "class Child(Base):\n" + replacement
    )
    result, report, observation = _validate(tmp_path, source)
    assert report.declared_rules == expected
    assert report.measurements.scalars.unknown_positions == 0
    assert result.exit_code == (2 if expected == "FAIL" else 0)
    assert bool(trace_valid_violations(observation)) == (expected == "FAIL")


@pytest.mark.parametrize("accessor", ["getter", "setter"])
def test_later_accessor_replaces_only_its_previous_signature(tmp_path: Path, accessor: str) -> None:
    source = _property(**{accessor: "object"})
    replacement = (
        "    @value.getter\n    def value(self) -> int: ...\n"
        if accessor == "getter"
        else "    @value.setter\n    def value(self, new_value: int) -> None: ...\n"
    )
    source = source.replace("class Child(Base):", replacement + "class Child(Base):")
    result, report, observation = _validate(tmp_path, source)
    assert result.exit_code == 0
    assert report.declared_rules == "PASS"
    assert report.measurements.scalars.unknown_positions == 0
    assert trace_valid_violations(observation) == ()


@pytest.mark.parametrize("annotation,expected", [("int", "PASS"), ("Hidden", "FAIL")])
def test_imported_property_keeps_its_defining_annotation_scope(
    tmp_path: Path, annotation: str, expected: str
) -> None:
    base = _property(setter=annotation).split("class Child(Base):")[0]
    source = "from .base import Base\nclass Hidden: pass\nclass Child(Base): pass\n"
    result, report, observation = _validate(tmp_path, source, {"sample/base.py": base})
    assert report.declared_rules == expected
    assert report.measurements.scalars.unknown_positions == 0
    assert result.exit_code == (2 if expected == "FAIL" else 0)
    assert bool(trace_valid_violations(observation)) == (expected == "FAIL")


@pytest.mark.parametrize("annotation,expected", [("int", "PASS"), ("object", "FAIL")])
def test_direct_property_uses_the_same_effective_accessor_policy(
    tmp_path: Path, annotation: str, expected: str
) -> None:
    source = (
        _property(setter=annotation)
        .split("class Child(Base):")[0]
        .replace("class Base:", "class Child:")
    )
    _, report, _ = _validate(tmp_path, source)
    assert report.declared_rules == expected
    assert report.measurements.scalars.unknown_positions == 0


@pytest.mark.parametrize("annotation,expected", [("int", "PASS"), ("object", "FAIL")])
def test_lone_direct_property_keeps_existing_signature_policy(
    tmp_path: Path, annotation: str, expected: str
) -> None:
    source = (
        "from dataclasses import dataclass\n@dataclass\nclass Child:\n"
        f"    @property\n    def value(self) -> {annotation}: ...\n"
    )
    _, report, _ = _validate(tmp_path, source)
    assert report.declared_rules == expected
    assert report.measurements.scalars.unknown_positions == 0


@pytest.mark.parametrize("accessor,expected", [("Base.value.getter", "FAIL"), ("property", "PASS")])
@pytest.mark.parametrize("imported", ["from .base import Base", "from .base import Base as Alias"])
def test_imported_property_copy_preserves_the_original_private_setter(
    tmp_path: Path, accessor: str, expected: str, imported: str
) -> None:
    base = _property(setter="Hidden").split("class Child(Base):")[0]
    source = f"{imported}\nclass Child(Base):\n    @{accessor}\n    def value(self) -> int: ...\n"
    if imported.endswith("as Alias"):
        source = source.replace("class Child(Base)", "class Child(Alias)").replace(
            "@Base.value", "@Alias.value"
        )
    _, report, observation = _validate(tmp_path, source, {"sample/base.py": base})
    assert report.declared_rules == expected
    assert report.measurements.scalars.unknown_positions == 0
    violations = trace_valid_violations(observation)
    if expected == "FAIL":
        assert any(item.data.get("position") == "new_value" for item in violations)


@pytest.mark.parametrize(
    "change",
    [
        "Base.value.fget.__annotations__.clear()\n",
        "Base.value.fset.__annotations__.clear()\n",
        "expose(Base.value)\n",
        "Base.value = other\n",
    ],
)
def test_property_escape_and_accessor_mutation_stay_unknown(tmp_path: Path, change: str) -> None:
    source = _property().replace("class Child(Base):", change + "class Child(Base):")
    _, report, _ = _validate(tmp_path, source)
    assert report.declared_rules == "UNKNOWN"
    assert report.measurements.scalars.unknown_positions > 0


def test_private_direct_property_does_not_create_a_public_surface(tmp_path: Path) -> None:
    source = (
        "from dataclasses import dataclass\n@dataclass\nclass Child:\n"
        "    def get(self) -> int: ...\n"
        "    @property\n    def _value(self) -> int: ...\n"
        "    @_value.setter\n    def _value(self, new_value: int) -> None: ...\n"
    )
    _, report, _ = _validate(tmp_path, source)
    assert report.declared_rules == "PASS"
    assert report.measurements.scalars.unknown_positions == 0


_PROPERTY_SPELLINGS = [
    ("", "property", "property"),
    ("from builtins import property\n", "property", "property"),
    ("from builtins import property as prop\n", "prop", "prop"),
    ("import builtins\n", "builtins.property", "builtins"),
]


@pytest.mark.parametrize("prefix,decorator,binding", _PROPERTY_SPELLINGS)
@pytest.mark.parametrize(
    "annotation,expected", [("int", "PASS"), ("object", "FAIL"), ("Hidden", "FAIL")]
)
def test_builtin_property_spellings_keep_inherited_accessor_findings(
    tmp_path, prefix, decorator, binding, annotation, expected
):
    source = prefix + _property(setter=annotation).replace("@property", f"@{decorator}")
    result, report, observation = _validate(tmp_path, source)
    assert report.declared_rules == expected
    assert result.exit_code == (0 if expected == "PASS" else 2)
    assert report.measurements.scalars.unknown_positions == 0
    assert bool(trace_valid_violations(observation)) == (expected == "FAIL")


@pytest.mark.parametrize("prefix,decorator,binding", _PROPERTY_SPELLINGS)
@pytest.mark.parametrize("change", ["module-shadow", "class-shadow", "owner-mutation"])
def test_builtin_property_spellings_preserve_binding_and_mutation_uncertainty(
    tmp_path, prefix, decorator, binding, change
):
    source = _property().replace("@property", f"@{decorator}")
    if change == "module-shadow":
        source = f"{binding} = custom\n" + source
    elif change == "class-shadow":
        source = source.replace("class Base:\n", f"class Base:\n    {binding} = custom\n")
    else:
        source = source.replace("class Child(Base):", "Base.value = custom\nclass Child(Base):")
    _, report, observation = _validate(tmp_path, prefix + source)
    assert report.declared_rules == "UNKNOWN"
    assert report.measurements.scalars.unknown_positions > 0
    assert trace_valid_violations(observation) == ()


def test_qualified_builtin_property_mutation_stays_unknown(tmp_path):
    source = "import builtins\nbuiltins.property = custom\n" + _property().replace(
        "@property", "@builtins.property"
    )
    _, report, observation = _validate(tmp_path, source)
    assert report.declared_rules == "UNKNOWN"
    assert report.measurements.scalars.unknown_positions > 0
    assert trace_valid_violations(observation) == ()
