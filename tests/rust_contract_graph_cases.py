# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-359: hand-written UML Target cases for the parity test of the Rust contract parser.

A single-key mutation cannot build a graph fault such as a repeated planned entity, so each case
here changes a small Target in one way that a check of `declared_graph` decides.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

Edit = Callable[[dict[str, Any]], None]


def _entity(identity: str, kind: str, name: str, **extra: Any) -> dict[str, Any]:
    entity = {
        "id": identity,
        "kind": kind,
        "qualified_name": name,
        "language": "python",
        "presence": "planned",
        "responsibilities": [f"Own {name}."],
        "provenance": ["d.md"],
    }
    entity.update(extra)
    return entity


def base() -> dict[str, Any]:
    """A small valid contract with a UML Target: a class, an interface, a method and a scope."""
    component = {
        "id": "C-A",
        "label": "a",
        "role": "component",
        "packages": ["p.a"],
        "responsibilities": ["Own a."],
        "forbidden_responsibilities": [],
        "provenance": ["d.md"],
        "requires": [{"component": "a", "rationale": "Self."}],
    }
    entities = [
        _entity("E-K", "class", "p.a.K"),
        _entity("E-I", "interface", "p.a.I"),
        _entity(
            "E-M",
            "method",
            "p.a.K.run",
            parent_id="E-K",
            signature={"parameters": [{"name": "x"}], "returns": "int"},
        ),
        _entity("E-E", "enum", "p.a.E"),
        _entity("E-L", "enum_literal", "p.a.E.ONE", parent_id="E-E"),
    ]
    relationships = [
        {
            "id": "R-1",
            "kind": "realizes",
            "source_id": "E-K",
            "target_id": "E-I",
            "provenance": ["d.md"],
        },
    ]
    scopes = [
        {
            "scope_id": "E-K",
            "mode": "closed",
            "rationale": "All methods.",
            "provenance": ["d.md"],
            "entity_kinds": ["method"],
        },
    ]
    uml = {
        "schema_version": "1.1.0",
        "entities": entities,
        "relationships": relationships,
        "scopes": scopes,
    }
    return {
        "schema_version": "2.4.0",
        "components": [component],
        "rules": [],
        "declarations": {"uml": uml},
    }


def _uml(document: dict[str, Any]) -> dict[str, Any]:
    uml: dict[str, Any] = document["declarations"]["uml"]
    return uml


def _add(entity: dict[str, Any]) -> Edit:
    return lambda document: _uml(document)["entities"].append(entity)


def _set(index: int, **values: Any) -> Edit:
    return lambda document: _uml(document)["entities"][index].update(values)


def _edge(**values: Any) -> Edit:
    edge = {
        "id": "R-X",
        "kind": "references",
        "source_id": "E-K",
        "target_id": "E-I",
        "provenance": ["d.md"],
        **values,
    }
    return lambda document: _uml(document)["relationships"].append(edge)


def _scope(**values: Any) -> Edit:
    scope = {
        "scope_id": "E-I",
        "mode": "open",
        "rationale": "R.",
        "provenance": ["d.md"],
        "entity_kinds": ["method"],
        **values,
    }
    return lambda document: _uml(document)["scopes"].append(scope)


def _reference(**values: Any) -> dict[str, Any]:
    entity = {
        "id": "E-R",
        "kind": "interface",
        "qualified_name": "p.a.I",
        "language": "python",
        "presence": "referenced",
        "provenance": ["e.md"],
    }
    entity.update(values)
    return entity


def _declare(**values: Any) -> Edit:
    return lambda document: document["declarations"].update(values)


def _component(**values: Any) -> Edit:
    return lambda document: document["components"][0].update(values)


EDITS: dict[str, Edit] = {
    "valid": lambda document: None,
    "repeated planned entity": _add(_entity("E-K2", "class", "p.a.K")),
    "attribute without classifier": _add(_entity("E-A", "attribute", "p.a.x")),
    "attribute of a class": _add(_entity("E-A", "attribute", "p.a.K.x", parent_id="E-K")),
    "method without parent": _set(2, parent_id=None),
    "method of an enum literal": _set(2, parent_id="E-L"),
    "enum literal with modifier": _set(4, modifiers=["static"]),
    "enum literal of a class": _set(4, parent_id="E-K"),
    "file path on a class": _set(0, file_path="p/a.py"),
    "module with a normal path": _add(_entity("E-F", "module", "p.a.f", file_path="p/a/f.py")),
    "module with a dot path": _add(_entity("E-F", "module", "p.a.f", file_path="./p/f.py")),
    "module with a parent path": _add(_entity("E-F", "module", "p.a.f", file_path="../f.py")),
    "signature on a class": _set(0, signature={"parameters": []}),
    "repeated python parameter": _set(2, signature={"parameters": [{"name": "x"}, {"name": "x"}]}),
    "repeated dart parameter": _set(
        2, language="dart", signature={"parameters": [{"name": "x"}, {"name": "x"}]}
    ),
    "initializer on a class": _set(0, initializer="1"),
    "binding with initializer": _add(_entity("E-B", "binding", "p.a.b", initializer="1")),
    "unknown parent": _set(0, parent_id="E-NONE"),
    "parent cycle": lambda document: (
        _set(0, parent_id="E-I")(document),
        _set(1, parent_id="E-K")(document),
    ),
    "component entity": _add(_entity("E-C", "component", "p.a")),
    "component entity with parent": _add(_entity("E-C", "component", "p.a", parent_id="E-K")),
    "defined entity": _set(0, presence="defined"),
    "planned without responsibility": _set(0, responsibilities=[]),
    "entity with record ids": _set(0, record_ids=["X"]),
    "entity with evidence": _set(0, evidence_ids=["X"]),
    "entity without provenance": _set(0, provenance=[]),
    "entity with blank provenance": _set(0, provenance=[" "]),
    "entity with definition context": _set(
        0, definition_contexts=[{"kind": "if", "branch": "body", "evidence_ids": []}]
    ),
    "inherits between interfaces": _edge(kind="inherits", source_id="E-I", target_id="E-K"),
    "inherits from a method": _edge(kind="inherits", source_id="E-M"),
    "mixes in from an interface": _edge(kind="mixes_in", source_id="E-I", target_id="E-K"),
    "mixes in a class": _edge(kind="mixes_in"),
    "unknown source": _edge(source_id="E-NONE"),
    "unknown target": _edge(target_id="E-NONE"),
    "relationship candidates": _edge(candidate_ids=["E-K"]),
    "resolved relationship": _edge(resolution="resolved"),
    "requires relationship": _edge(kind="requires", reason="r"),
    "relationship record ids": _edge(record_ids=["X"]),
    "relationship without target": _edge(target_id=None, expression="x"),
    "through on references": _edge(through=["p.a"]),
    "decided by on references": _edge(decided_by="agent"),
    "relationship count": _edge(candidate_count=0),
    "relationship without provenance": _edge(provenance=[]),
    "scope with requires": _scope(relationship_kinds=["requires"]),
    "scope on an unknown entity": _scope(scope_id="E-NONE"),
    "scope without kinds": _scope(entity_kinds=[]),
    "repeated scope kind": _scope(scope_id="E-K"),
    "second scope kind": _scope(scope_id="E-K", entity_kinds=["attribute"]),
    "linked reference": _add(_reference()),
    "reference with responsibility": _add(_reference(responsibilities=["x"])),
    "reference with parent": _add(_reference(parent_id="E-K")),
    "reference owns a scope": lambda document: (
        _add(_reference())(document),
        _scope(scope_id="E-R")(document),
    ),
    "ambiguous reference": lambda document: (
        _add(_entity("E-I2", "interface", "p.a.I", parent_id="E-K"))(document),
        _add(_reference())(document),
    ),
    "reference of a symbol in inherits": lambda document: (
        _add(_entity("E-S", "symbol", "p.a.S"))(document),
        _add(_reference(id="E-RS", kind="symbol", qualified_name="p.a.S"))(document),
        _edge(kind="inherits", target_id="E-RS")(document),
    ),
    "referenced symbol in inherits": lambda document: (
        _add(_reference(id="E-RS", kind="symbol", qualified_name="p.a.T"))(document),
        _edge(kind="inherits", target_id="E-RS")(document),
    ),
    "enum literal in schema 1.0.0": lambda document: _uml(document).update(schema_version="1.0.0"),
    "schema 1.3.0": lambda document: _uml(document).update(schema_version="1.3.0"),
    "public API without provenance": _declare(public_api=["p.a"]),
    "public API with provenance": _declare(
        public_api=["p.a", "p.a:K"], public_api_provenance=["d.md"]
    ),
    "public and planned entry": _component(public=["p.a:K"], planned=["p.a:K"]),
    "modules with UML": _declare(modules=[{"path": "p/a.py", "responsibility": "R."}]),
    "layer with UML": lambda document: (
        document.update(schema_version="2.4.0"),
        _component(layer="core")(document),
    ),
    "planned component with UML": _component(lifecycle="planned", packages=[]),
    "entity id of a rule": lambda document: document["rules"].append(
        {
            "id": "E-K",
            "kind": "complete_requires",
            "rationale": "r",
            "provenance": ["p"],
            "decided_by": "agent",
        }
    ),
    "layout rule with UML": lambda document: document["rules"].append(
        {
            "id": "L-1",
            "kind": "root_layout",
            "root": "p",
            "allowed_children": ["p.a"],
            "rationale": "r",
            "provenance": ["p"],
            "decided_by": "agent",
        }
    ),
    "external scope with UML": lambda document: document["rules"].append(
        {
            "id": "X-1",
            "kind": "external_dependency_scope",
            "dependency": "rich",
            "allowed_sources": ["p.a"],
            "rationale": "r",
            "provenance": ["p"],
            "decided_by": "agent",
        }
    ),
}


def graph_cases(encode: Callable[[object], bytes]) -> list[tuple[str, bytes]]:
    """Each edit applied to a fresh copy of the base contract."""
    cases = []
    for name, edit in EDITS.items():
        document = copy.deepcopy(base())
        edit(document)
        cases.append((f"graph: {name}", encode(document)))
    return cases
