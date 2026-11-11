# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-364: a contract that uses every declaration, and hand-written faults for the parity test.

No repository contract has a `compat` entry, a coupling budget and every boundary position at
once, so `full()` holds them all, and the mutation sources include it. Each edit of `EDITS`
breaks one check of the parser; the name says which.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable
from typing import Any

from rust_contract_graph_cases import base

P = ["d.md"]
Edit = Callable[[dict[str, Any]], None]


def _rule(identity: str, kind: str, **fields: Any) -> dict[str, Any]:
    return {
        "id": identity,
        "kind": kind,
        "rationale": "r",
        "provenance": P,
        "decided_by": "agent",
        **fields,
    }


def _positions() -> list[dict[str, Any]]:
    head = {"qualified_name": "p.a.f", "position": "return"}
    return [
        {**head, "annotation": "list[str]"},
        {**head, "annotation": "dict[str, int]", "container_depth": 2, "mapping_depth": 1},
        {**head, "annotation": "Alias", "alias_body": {"origin": "o", "shape": "s"}},
        {**head, "annotation": "Key", "key_alias_body": {"origin": "o", "shape": "s"}},
        {**head, "annotation": "Arm", "literal_mapping_arm": "kind"},
        {**head, "annotation": "dict", "native_mapping": True},
        {**head, "annotation": "Mapping", "field_path": "items"},
    ]


def full() -> dict[str, Any]:
    """A valid 3.14.0 contract with each declaration, each Python-only kind and a UML Target."""
    document = base()
    document["schema_version"] = "3.14.0"
    document["components"][0]["public"] = ["p.a"]
    document["components"].append(
        {
            "id": "C-B",
            "label": "b",
            "role": "component",
            "packages": ["p.b"],
            "responsibilities": ["Own b."],
            "forbidden_responsibilities": [],
            "provenance": P,
            "public": ["p.b.api", "p.b.api:Thing"],
            "capability_id": "CAP-1",
        }
    )
    document["rules"] = [
        _rule("R-IB", "interface_boundary", include_type_checking=True),
        _rule("R-CO", "call_owner", source="p.a", target="p.b.f", allowed_sources=["p.a.x"]),
        _rule(
            "R-SO",
            "source_ownership",
            source="p.a",
            mode="confined",
            roles=["read", "fallback"],
            symbols=["p.a.X"],
            parameters=["p.a.g.y"],
            owner="p.a.own",
            value_owner="p.a.vo",
        ),
        _rule("R-BT", "boundary_types", source="p.a", allowed_positions=_positions()),
        _rule(
            "R-PD",
            "protocol_declarations",
            source="p.a",
            protocol="p.a.Proto",
            selectors=[{"role": "member", "visibility": "public", "name": "run"}],
        ),
        _rule(
            "R-FC",
            "forbidden_construct",
            source="p.a",
            constructs=["type_ignore", "getattr"],
            allowed_type_ignores=[
                {"qualified_name": "p.a.f", "line": 3, "statement": "s", "tag": "misc"}
            ],
            selector={"receiver": "p.a.obj", "member": "attr", "role": "read"},
        ),
    ]
    document["declarations"].update(
        {
            "capabilities": [
                {"id": "CAP-1", "name": "N", "label": "L", "review_order": 1, "provenance": P}
            ],
            "review_scopes": [
                {
                    "id": "RS-1",
                    "label": "L",
                    "parent_id": "CAP-1",
                    "subjects": ["a"],
                    "provenance": P,
                }
            ],
            "public_api": ["p.b.api:Thing"],
            "public_api_provenance": P,
            "public_commands": [
                {"id": "CMD-1", "command": "archkeel x", "description": "D", "provenance": P}
            ],
            "context_roots": ["src"],
            "context_roots_provenance": P,
            "paths": [
                {"id": "PATH-1", "label": "L", "kind": "read", "steps": ["a", "b"], "provenance": P}
            ],
            "spot_owners": [
                {
                    "id": "OWN-1",
                    "label": "L",
                    "owner": "p.a",
                    "responsibility": "R",
                    "provenance": P,
                }
            ],
            "compat": [{"module": "p.old", "target": "p.a", "lifetime": "migration"}],
            "measurement_budgets": [{"name": "cycle_edges", "provenance": P}],
            "facade_budgets": [{"component": "b", "max_names": 3, "provenance": P}],
            "coupling_budgets": [{"source": "a", "target": "b", "max_names": 2, "provenance": P}],
            "modules": [{"path": "p/a.py", "responsibility": "R."}],
        }
    )
    return document


def _declarations(document: dict[str, Any]) -> dict[str, Any]:
    declarations: dict[str, Any] = document["declarations"]
    return declarations


def _set(key: str, index: int, **values: Any) -> Edit:
    return lambda document: _declarations(document)[key][index].update(values)


def _append(key: str, entry: dict[str, Any]) -> Edit:
    return lambda document: _declarations(document)[key].append(entry)


def _rule_of(identity: str, document: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = next(rule for rule in document["rules"] if rule["id"] == identity)
    return found


def _rule_set(identity: str, **values: Any) -> Edit:
    return lambda document: _rule_of(identity, document).update(values)


def _position(index: int, **values: Any) -> Edit:
    return lambda document: _rule_of("R-BT", document)["allowed_positions"][index].update(values)


def _drop_position_key(index: int, key: str) -> Edit:
    return lambda document: _rule_of("R-BT", document)["allowed_positions"][index].pop(key)


def _component(index: int, **values: Any) -> Edit:
    return lambda document: document["components"][index].update(values)


def _uml_entity_id(identity: str) -> Edit:
    def edit(document: dict[str, Any]) -> None:
        _declarations(document)["uml"]["entities"][0]["id"] = identity
        _declarations(document)["uml"]["scopes"][0]["scope_id"] = identity
        _declarations(document)["uml"]["relationships"][0]["source_id"] = identity
        _declarations(document)["uml"]["entities"][2]["parent_id"] = identity

    return edit


def _stable_id(prefix: str, *parts: object) -> str:
    """`stable_id` of `ir/facts.py`."""
    payload = "\x1f".join(str(part) for part in parts).encode()
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:16]}"


def _api_id(selector: str) -> str:
    return f"API-{hashlib.sha256(selector.encode()).hexdigest()[:16]}"


def _selector(**values: Any) -> Edit:
    return _rule_set("R-FC", selector=values)


EDITS: dict[str, Edit] = {
    "valid": lambda document: None,
    "coupling without a TYPE_CHECKING boundary": _rule_set("R-IB", include_type_checking=False),
    "coupling of one component": _set("coupling_budgets", 0, target="a"),
    "repeated facade budget": _append(
        "facade_budgets", {"component": "b", "max_names": 1, "provenance": P}
    ),
    "repeated coupling budget": _append(
        "coupling_budgets", {"source": "a", "target": "b", "max_names": 1, "provenance": P}
    ),
    "facade budget without a facade": lambda document: (
        _component(1, public=None)(document),
        _declarations(document).pop("coupling_budgets"),
    ),
    "coupling target without a facade": _component(1, public=None),
    "coupling target without a facade and no facade budget": lambda document: (
        _component(1, public=None)(document),
        _declarations(document).pop("facade_budgets"),
        _declarations(document).update(public_api=[], public_api_provenance=[]),
    ),
    "coupling source without a facade": _component(0, public=None),
    "coupling source unknown": _set("coupling_budgets", 0, source="z"),
    "repeated compat module": _append(
        "compat", {"module": "p.old", "target": "p.b", "lifetime": "permanent"}
    ),
    "compat to itself": _set("compat", 0, target="p.old"),
    "compat module not dotted": _set("compat", 0, module="p old"),
    "compat lifetime permanent": _set("compat", 0, lifetime="permanent"),
    "compat lifetime unknown": _set("compat", 0, lifetime="forever"),
    "repeated measurement budget": _append(
        "measurement_budgets", {"name": "cycle_edges", "provenance": P}
    ),
    "repeated module path": _append("modules", {"path": "p/a.py", "responsibility": "S."}),
    "module responsibility on two lines": _set("modules", 0, responsibility="R.\nS."),
    "capability id of a component": _set("capabilities", 0, id="C-A"),
    "review scope id of a component": _set("review_scopes", 0, id="C-A"),
    "command id of a component": _set("public_commands", 0, id="C-A"),
    "path id of a component": _set("paths", 0, id="C-A"),
    "SPOT owner id of a component": _set("spot_owners", 0, id="C-A"),
    "UML relationship id of a rule": lambda document: _declarations(document)["uml"][
        "relationships"
    ][0].update(id="R-IB"),
    "UML entity id of a requires edge": _uml_entity_id(
        _stable_id("TARGET-REQUIRES", "C-A", "C-A", (), "Self.", None, 0)
    ),
    "UML entity id of the module inventory": _uml_entity_id(
        _stable_id("MODULE-TARGET-INVENTORY", "architecture-contract.json")
    ),
    "UML entity id of a public API entry": _uml_entity_id(_api_id("p.b.api:Thing")),
    "retired with value transfer": _rule_set(
        "R-SO",
        mode="retired",
        roles=["value_transfer"],
        parameters=[],
        owner=None,
        value_owner=None,
    ),
    "retired with an owner": _rule_set(
        "R-SO", mode="retired", roles=["read"], parameters=[], value_owner=None
    ),
    "parameter without a function": _rule_set("R-SO", parameters=["y"]),
    "confined without a value owner": _rule_set("R-SO", value_owner=None),
    "repeated boundary position": lambda document: _rule_of("R-BT", document)[
        "allowed_positions"
    ].append(_positions()[0]),
    "mapping depth with a field path": _position(1, field_path="items"),
    "container depth not mapping depth plus one": _position(1, container_depth=3),
    "mapping depth without container depth": _drop_position_key(1, "container_depth"),
    "alias body with a field path": _position(2, field_path="items"),
    "key alias body with a container depth": _position(3, container_depth=1),
    "literal arm with a mapping depth": _position(4, mapping_depth=1),
    "literal arm with a container depth": _position(4, container_depth=1),
    "native mapping false": _position(5, native_mapping=False),
    "native mapping of a list": _position(5, annotation="list"),
    "native mapping with a container depth": _position(5, container_depth=1),
    "bare dict": _drop_position_key(5, "native_mapping"),
    "bare Mapping at the root": _drop_position_key(6, "field_path"),
    "repeated protocol selector": lambda document: _rule_of("R-PD", document)["selectors"].append(
        {"role": "member", "visibility": "all", "name": "run"}
    ),
    "protocol selector of another role": lambda document: _rule_of("R-PD", document)[
        "selectors"
    ].append({"role": "parameter", "visibility": "public", "name": "run"}),
    "repeated type ignore": lambda document: _rule_of("R-FC", document)[
        "allowed_type_ignores"
    ].append({"qualified_name": "p.a.f", "line": 3, "statement": "s", "tag": "misc"}),
    "read selector with a literal": _selector(
        receiver="p.a.obj", member="m", role="read", literal="x"
    ),
    "constructor selector with a member": _selector(
        receiver="p.a.Obj", member="m", role="constructor"
    ),
    "constructor selector": _selector(receiver="p.a.Obj", role="constructor"),
    "equality selector without a literal": _selector(
        receiver="p.a.obj", member="m", role="equality"
    ),
    "equality selector with a literal": _selector(
        receiver="p.a.obj", member="m", role="equality", literal=""
    ),
    "selector receiver not an identifier": _selector(receiver="p.a.1obj", member="m", role="read"),
    "planned owner with a public API": _component(
        1, lifecycle="planned", packages=[], public=["p.b.api"]
    ),
    "planned owner with an empty public API": lambda document: (
        _component(1, lifecycle="planned", packages=[], public=[])(document),
        _declarations(document).pop("facade_budgets"),
        _declarations(document).pop("coupling_budgets"),
    ),
    "planned owner with packages": _component(1, lifecycle="planned"),
    "planned owner with packages and no public API": lambda document: (
        _component(1, lifecycle="planned", public=None)(document),
        _declarations(document).pop("facade_budgets"),
        _declarations(document).pop("coupling_budgets"),
        _declarations(document).update(public_api=[], public_api_provenance=[]),
    ),
    "namespace not dotted": _component(1, packages=["p b"], namespace="p b"),
    "namespace outside the packages": _component(1, namespace="p.c"),
    "namespace of another component": _component(1, namespace="p.a"),
    "mixes in from an interface to a mixin": lambda document: (
        _declarations(document)["uml"]["entities"].append(
            {
                "id": "E-MX",
                "kind": "mixin",
                "qualified_name": "p.a.MX",
                "language": "python",
                "presence": "planned",
                "responsibilities": ["Mix."],
                "provenance": P,
            }
        ),
        _declarations(document)["uml"]["relationships"].append(
            {
                "id": "R-MX",
                "kind": "mixes_in",
                "source_id": "E-I",
                "target_id": "E-MX",
                "provenance": P,
            }
        ),
    ),
}


def declaration_cases(encode: Callable[[object], bytes]) -> list[tuple[str, bytes]]:
    """Each edit applied to a fresh copy of the full contract."""
    cases = []
    for name, edit in EDITS.items():
        document = copy.deepcopy(full())
        edit(document)
        cases.append((f"declarations: {name}", encode(document)))
    return cases
