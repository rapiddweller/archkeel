# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-107: a module exists because its file does, so an empty file is still evidence of it.

`root_layout`, `complete_assignment` and a component `namespace` judge a module by its own file.
Their violation cites the module fact, whose evidence quoted line 1; an empty `__init__.py` or
a blank first line left nothing to quote, the trace check refused the violation and the whole
run turned UNKNOWN (issue #153). Each case here pins the same violation for the empty file as
for one with text, and a verdict that stays FAIL.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from test_analyzer import _component, _observe
from test_architecture_demo import CONFIG, _prepare_repo
from test_dart_directives import dart_package, report_dart, rule

from archkeel.analyzer import observe
from archkeel.check.report import run_report
from archkeel.check.run import inspect_observation
from archkeel.ir.codec import decode_canonical_model
from archkeel.ir.model import Evidence, Observation, Record, stable_id
from archkeel.ir.trace import trace_valid_violations
from fixtures.architecture_demo import CATALOG

SCHEMA = Path(__file__).parents[1] / "schema"

_PROBE = {"rationale": "Probe.", "provenance": ["docs/architecture/sample.md"]}
_ROOT_LAYOUT = {
    "id": "ROOT",
    "kind": "root_layout",
    "root": "sample",
    "allowed_children": ["sample.keep"],
    "decided_by": "architect",
    **_PROBE,
}
_ASSIGNMENT = {
    "id": "ASSIGN",
    "kind": "complete_assignment",
    "source": "sample",
    "decided_by": "architect",
    **_PROBE,
}
_THE_FILE = (0, 0, 0, "")
# (initializer, the evidence position and excerpt its module fact cites)
_INITIALIZERS = (
    ('"""Extra."""\n', (1, 1, 0, '"""Extra."""')),
    ("", _THE_FILE),
    ("\n", _THE_FILE),
    ("\nVALUE = 1\n", _THE_FILE),
)


def _write(root: Path, contract: dict[str, object], files: dict[str, str]) -> Observation:
    (root / "contract.json").write_text(json.dumps({"schema_version": "2.1.0", **contract}))
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    result = _observe(root)
    assert result.diagnostics == (), result.diagnostics
    assert result.observation is not None
    return result.observation


def _violation(observation: Observation) -> tuple[Record, Evidence]:
    """The one violation, trace-valid, of a complete observation whose verdict is FAIL."""
    _, verdict = inspect_observation(observation)
    assert verdict == "FAIL"
    (violation,) = trace_valid_violations(observation)
    evidence = {item.id: item for item in observation.evidence}
    (fact,) = (
        item
        for section in observation.sections
        for item in section.records
        if item.id in violation.fact_ids
    )
    (source,) = (evidence[key] for key in fact.evidence_ids)
    return violation, source


@pytest.mark.parametrize(("initializer", "cited"), _INITIALIZERS)
def test_an_unexpected_package_is_the_same_violation_whatever_its_initializer_holds(
    tmp_path: Path, initializer: str, cited: tuple[int, int, int, str]
) -> None:
    observation = _write(
        tmp_path,
        {"components": [], "rules": [_ROOT_LAYOUT]},
        {
            "sample/__init__.py": '"""Sample."""\n',
            "sample/keep/__init__.py": '"""Keep."""\n',
            "sample/extra/__init__.py": initializer,
        },
    )
    violation, source = _violation(observation)

    assert (violation.id, violation.rule_ids, violation.fact_ids, violation.title) == (
        stable_id("VIO", "ROOT", "sample.extra"),
        ("ROOT",),
        (stable_id("MOD", "sample.extra"),),
        "sample.extra is not an allowed child of sample",
    )
    assert source.file == "sample/extra/__init__.py"
    assert (source.line, source.end_line, source.column, source.excerpt) == cited


def test_a_module_whose_first_line_is_blank_is_an_unowned_module(tmp_path: Path) -> None:
    """The limit rules.md named: code below a blank first line was UNKNOWN, not FAIL."""
    observation = _write(
        tmp_path,
        {"components": [_component("core")], "rules": [_ASSIGNMENT]},
        {"sample/core.py": "VALUE = 1\n", "sample/extra.py": "\nVALUE = 2\n"},
    )
    violation, source = _violation(observation)

    assert (violation.rule_ids, violation.subjects) == (("ASSIGN",), ("sample.extra",))
    assert (source.file, source.line, source.excerpt) == ("sample/extra.py", 0, "")


def test_an_empty_module_outside_its_namespace_is_misplaced(tmp_path: Path) -> None:
    orders = _component(
        "orders", packages=["sample.orders", "sample.order_rules"], namespace="sample.orders"
    )
    observation = _write(
        tmp_path,
        {"components": [orders], "rules": []},
        {"sample/orders.py": "VALUE = 1\n", "sample/order_rules.py": ""},
    )
    violation, source = _violation(observation)

    assert (violation.kind, violation.subjects) == (
        "module.placement",
        ("sample.order_rules", "sample.orders"),
    )
    assert (source.file, source.line, source.excerpt) == ("sample/order_rules.py", 0, "")


@pytest.mark.parametrize("library", ["class Extra {}\n", ""])
def test_an_empty_dart_library_is_the_same_root_layout_violation(
    tmp_path: Path, library: str
) -> None:
    root = dart_package(
        tmp_path / "pkg",
        {"lib/extra.dart": library},
        rules=[rule("RULE", "root_layout", root="app", allowed_children=["app.core", "app.data"])],
    )
    result, observation, _ = report_dart(root)

    assert (result.exit_code, result.declared_rules) == (0, "FAIL"), result.diagnostics
    assert observation is not None
    (violation,) = trace_valid_violations(observation)
    assert (violation.id, violation.subjects) == (
        stable_id("VIO", "RULE", "app.extra"),
        ("app.extra",),
    )


def _ir_schema_errors(observation: dict[str, object]) -> list[str]:
    """What the published IR schemas reject in one decoded observation, as test_schema_drift."""
    common = json.loads((SCHEMA / "architecture-ir-common.schema.json").read_bytes())
    profile = json.loads((SCHEMA / "architecture-ir-python-decoded.schema.json").read_bytes())
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    validator = Draft202012Validator(profile, registry=registry)
    return [error.message for error in validator.iter_errors(observation)]


def test_the_ir_schemas_accept_a_cited_file(tmp_path: Path) -> None:
    variant = next(item for item in CATALOG if item.id == "class-a-root-layout-empty-package")
    _, architecture = run_report(
        _prepare_repo(tmp_path, dict(variant.files)), config=CONFIG, analyzer=observe
    )
    assert architecture is not None
    observation = decode_canonical_model(json.loads(architecture))
    evidence = observation["evidence"]
    (cited,) = (item for item in evidence if item["file"] == "shop/extra/__init__.py")

    assert (cited["line"], cited["end_line"], cited["column"], cited["excerpt"]) == (0, 0, 0, "")
    assert _ir_schema_errors(observation) == []
