# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Shared contract fixtures and checks of the retained annotation reader."""

import ast
import json
from pathlib import Path

from archkeel.ir.model import (
    ForbiddenConstructKind,
    ForbiddenConstructRule,
    Observation,
    text_value,
)

ROOT = Path(__file__).parents[1]
BOUNDARY_TYPES = ROOT / "src/archkeel/check/evaluation/boundary_types.py"


def _component(
    label: str,
    *,
    public: list[str] | None = None,
    planned: list[str] | None = None,
    packages: list[str] | None = None,
    namespace: str | None = None,
) -> dict[str, object]:
    component: dict[str, object] = {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": packages or [f"sample.{label}"],
        "responsibilities": [],
        "forbidden_responsibilities": [],
        "provenance": ["docs/architecture/sample.md"],
    }
    if public is not None:
        component["public"] = public
    if planned is not None:
        component["planned"] = planned
    if namespace is not None:
        component["namespace"] = namespace
    return component


def _inside_component(label: str, requires: list[str]) -> dict[str, object]:
    return {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": [f"sample.core.{label}"],
        "responsibilities": [],
        "forbidden_responsibilities": [],
        "provenance": ["docs/architecture/sample.md"],
        "requires": [{"component": name, "rationale": "Probe."} for name in requires],
    }


def _with_inside(tmp_path: Path, inside: str, *, inner_rules: list[object] | None = None) -> None:
    outer = {
        "schema_version": "2.1.0",
        "components": [_component("core") | {"inside": inside}],
        "rules": [],
    }
    (tmp_path / "contract.json").write_text(json.dumps(outer))
    (tmp_path / "inner.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _inside_component("a", ["b"]),
                    _inside_component("b", []),
                ],
                "rules": inner_rules or [],
            }
        )
    )


def _multi_package_worker() -> dict[str, object]:
    return {
        "id": "COMP-WORKER",
        "label": "worker",
        "role": "component",
        "packages": ["sample.orchestrator", "sample.worker"],
        "responsibilities": [],
        "forbidden_responsibilities": [],
        "provenance": ["docs/architecture/sample.md"],
    }


def _any_rule(source: str = "sample") -> ForbiddenConstructRule:
    return ForbiddenConstructRule(
        "R",
        "forbidden_construct",
        source,
        (ForbiddenConstructKind.ANY_ANNOTATION,),
        "because",
        (),
        "architect",
    )


def _boundary_types_contract(*components: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "2.1.0",
        "components": list(components),
        "rules": [
            {
                "id": "APP-TYPES-NOT-DICT",
                "kind": "boundary_types",
                "source": "sample.app",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    }


def _facade_types(observation: Observation) -> dict[str, tuple[str, ...]]:
    """Every function symbol that records the types its declared facade signature exposes."""
    return {
        name: types
        for record in observation.records("symbols") or ()
        if (name := text_value(record.data.get("qualified_name")))
        and isinstance(types := record.data.get("facade_types"), tuple)
    }


def _boundary_types_source_ast() -> ast.Module:
    return ast.parse(BOUNDARY_TYPES.read_bytes())


def _top_level_callers(tree: ast.Module, called_name: str) -> set[str]:
    """Find the module-level functions that call the named function."""
    return {
        node.name
        for node in ast.iter_child_nodes(tree)
        if isinstance(node, ast.FunctionDef)
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == called_name
    }


def test_only_one_function_resolves_an_annotations_named_type() -> None:
    callers = _top_level_callers(_boundary_types_source_ast(), "resolve_named_type")
    assert callers == {
        "_named_type_verdict",
        "_direct_generic_candidate_types",
        "_declared_field_reach",
    }, (
        f"resolve_named_type is called directly from {sorted(callers)}: annotation walkers "
        "must share `_named_type_verdict`; `_direct_generic_candidate_types` is the separate "
        "bare-name identity lookup for a proven generic base and concrete arguments."
    )


def test_resolved_position_types_does_not_itself_walk_collection_parameters() -> None:
    tree = _boundary_types_source_ast()
    [target] = [
        node
        for node in ast.iter_child_nodes(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_resolved_position_types"
    ]
    walks_collections = any(
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "_collection_parameters"
        for call in ast.walk(target)
    )
    assert not walks_collections, (
        "_resolved_position_types calls _collection_parameters itself: it derives which "
        "positions to resolve on its own, instead of reading the one analysis "
        "_boundary_type_verdict already computed for the same annotation."
    )
