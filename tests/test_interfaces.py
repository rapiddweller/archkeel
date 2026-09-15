# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Unit tests for the AD-9 component communication derivation."""

from typing import Any

from test_delta import _model

from archkeel.ir.codec import parse_observation
from archkeel.ir.interfaces import InterfaceEdge, InterfaceName, interface_edges
from archkeel.ir.model import Observation


def _declaration(label: str, packages: list[str]) -> dict[str, Any]:
    return {
        "id": f"COMP-{label}",
        "evidence_class": "DECLARED_RULE",
        "area": "components",
        "kind": "component_responsibility",
        "title": label,
        "subjects": packages,
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {},
    }


def _import_record(
    identifier: str,
    *,
    source_module: str,
    target_module: str,
    symbol: str | None,
    origin_definition: str | None,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "evidence_class": "FACT",
        "area": "dependencies",
        "kind": "import",
        "title": "import",
        "subjects": [source_module, target_module],
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {
            "source_module": source_module,
            "target_module": target_module,
            "symbol": symbol,
            "origin_definition": origin_definition,
            "under_type_checking": False,
        },
    }


def _symbol_record(
    identifier: str,
    *,
    kind: str,
    qualified_name: str,
    module: str,
    name: str,
    class_kind: str | None = None,
    parameters: list[dict[str, str | None]] | None = None,
    returns: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "qualified_name": qualified_name,
        "module": module,
        "name": name,
        "parent": None,
        "visibility": "public_name",
    }
    if kind == "class":
        data["class_kind"] = class_kind or "class"
    else:
        data["parameters"] = parameters or []
        data["returns"] = returns
    return {
        "id": identifier,
        "evidence_class": "FACT",
        "area": "repository_topology",
        "kind": kind,
        "title": name,
        "subjects": [qualified_name, module],
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": data,
    }


def _observation(
    *,
    declarations: tuple[dict[str, Any], ...] = (),
    imports: tuple[dict[str, Any], ...] = (),
    symbols: tuple[dict[str, Any], ...] = (),
) -> Observation:
    raw = _model(git_head="a" * 40, imports=list(imports))
    raw["declarations"] = list(declarations)
    raw["symbols"] = list(symbols)
    return parse_observation(raw)


def test_ownership_overlap_produces_no_edge() -> None:
    observation = _observation(
        declarations=(
            _declaration("a", ["pkg.a"]),
            _declaration("shared1", ["pkg.shared"]),
            _declaration("shared2", ["pkg.shared"]),
        ),
        imports=(
            _import_record(
                "IMP-1",
                source_module="pkg.a.mod",
                target_module="pkg.shared.thing",
                symbol="Widget",
                origin_definition="pkg.shared.thing.Widget",
            ),
        ),
    )
    assert interface_edges(observation) == ()


def test_origin_definition_follows_reexport_chain_and_reports_constants() -> None:
    observation = _observation(
        declarations=(_declaration("a", ["pkg.a"]), _declaration("b", ["pkg.b"])),
        imports=(
            _import_record(
                "IMP-1",
                source_module="pkg.a.mod",
                target_module="pkg.b",
                symbol="Widget",
                origin_definition="pkg.b.impl.Widget",
            ),
            _import_record(
                "IMP-2",
                source_module="pkg.a.mod",
                target_module="pkg.b",
                symbol=None,
                origin_definition=None,
            ),
        ),
        symbols=(
            _symbol_record(
                "SYM-1",
                kind="class",
                qualified_name="pkg.b.impl.Widget",
                module="pkg.b.impl",
                name="Widget",
                class_kind="dataclass",
            ),
        ),
    )
    edges = interface_edges(observation)
    assert edges == (
        InterfaceEdge(
            "a",
            "b",
            (
                InterfaceName("pkg.b", "constant", (), ""),
                InterfaceName("pkg.b:Widget", "dataclass", (), ""),
            ),
        ),
    )


def test_typed_and_untyped_function_signatures() -> None:
    observation = _observation(
        declarations=(_declaration("a", ["pkg.a"]), _declaration("b", ["pkg.b"])),
        imports=(
            _import_record(
                "IMP-1",
                source_module="pkg.a.mod",
                target_module="pkg.b",
                symbol="typed",
                origin_definition="pkg.b.typed",
            ),
            _import_record(
                "IMP-2",
                source_module="pkg.a.mod",
                target_module="pkg.b",
                symbol="untyped",
                origin_definition="pkg.b.untyped",
            ),
        ),
        symbols=(
            _symbol_record(
                "SYM-1",
                kind="function",
                qualified_name="pkg.b.typed",
                module="pkg.b",
                name="typed",
                parameters=[{"name": "value", "annotation": "int"}],
                returns="str",
            ),
            _symbol_record(
                "SYM-2",
                kind="function",
                qualified_name="pkg.b.untyped",
                module="pkg.b",
                name="untyped",
                parameters=[{"name": "value", "annotation": None}],
                returns=None,
            ),
        ),
    )
    edges = interface_edges(observation)
    assert edges == (
        InterfaceEdge(
            "a",
            "b",
            (
                InterfaceName("pkg.b:typed", "function", ("value: int",), "str"),
                InterfaceName("pkg.b:untyped", "function", ("value: UNKNOWN",), "UNKNOWN"),
            ),
        ),
    )
