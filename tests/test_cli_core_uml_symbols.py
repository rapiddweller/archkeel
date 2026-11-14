# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-502: the core compares the symbol part of a UML target on TypeScript plants.

Each plant is a TypeScript tree with a UML target. `PLANTS` gives the row of release 4.0.1 on the
same tree and the row of the core. The core row is equal to the release row or stricter: a core
PASS where 4.0.1 gives FAIL or UNKNOWN is a bug.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_cli_core_only_scan import command
from test_cli_core_uml_compare import ONE, PROVENANCE, module, project

ROW = "UML-TARGET-a2e40c5592b1b06a"
PUBLIC = {"kind": "public", "basis": "declared"}
PRIVATE = {"kind": "private", "basis": "declared"}


def sym(identity: str, kind: str, name: str, parent: str = "one", **extra: Any) -> dict:
    """A planned symbol entity of the module `one`; `name` is below the module name."""
    entity = {
        "id": identity,
        "kind": kind,
        "qualified_name": f"{ONE}.{name}",
        "parent_id": parent,
        "language": "typescript",
        "presence": "planned",
        "provenance": PROVENANCE,
        "responsibilities": ["Hold it."],
        "visibility": PUBLIC,
        **extra,
    }
    return {key: value for key, value in entity.items() if value is not None}


def referenced(identity: str, kind: str, name: str, **extra: Any) -> dict:
    """An entity that the target only names: it is not planned and states no detail."""
    return {
        "id": identity,
        "kind": kind,
        "qualified_name": f"{ONE}.{name}",
        "language": "typescript",
        "presence": "referenced",
        "provenance": PROVENANCE,
        **extra,
    }


def edge(kind: str, source: str, target: str) -> dict:
    return {
        "id": f"{source}-{kind}-{target}",
        "kind": kind,
        "source_id": source,
        "target_id": target,
        "provenance": PROVENANCE,
    }


def param(name: str, annotation: str = "number") -> dict:
    return {"name": name, "annotation": annotation, "kind": "positional", "default_known": True}


def signature(returns: str, *parameters: dict) -> dict:
    return {"parameters": list(parameters), "returns": returns}


SOURCE = """import { t } from '../b/t';
export const used = t;
export interface Port { run(value: number): string; }
export class Unit {}
export class Client implements Port {
  private token: string = '';
  run(value: number): string { return helper(value); }
}
export enum State { READY = 'ready', STOPPED = 'stopped' }
export function helper(value: number): string { return String(value); }
export function build(): Unit {
  const item = new Unit();
  return item;
}
export type Text = string;
export const VERSION = 1;
"""
FILES = {"src/a/one.ts": SOURCE, "src/b/t.ts": "export const t = 1;\n"}
ENTITIES = [
    module("one", ONE),
    sym("port", "interface", "Port"),
    sym("port-run", "method", "Port.run", "port", signature=signature("string", param("value"))),
    sym("unit", "class", "Unit"),
    sym("client", "class", "Client"),
    sym("token", "attribute", "Client.token", "client", visibility=PRIVATE, annotation="string"),
    sym("run", "method", "Client.run", "client", signature=signature("string", param("value"))),
    sym("state", "enum", "State"),
    sym("ready", "enum_literal", "State.READY", "state"),
    sym("stopped", "enum_literal", "State.STOPPED", "state"),
    sym("helper", "function", "helper", signature=signature("string", param("value"))),
    sym("build", "function", "build", signature=signature("Unit")),
    sym("item", "binding", "build.item", "build", visibility=None),
    sym("text", "type_alias", "Text"),
    sym("version", "constant", "VERSION"),
]
RELATIONSHIPS = [
    edge("calls", "run", "helper"),
    edge("creates", "build", "unit"),
    edge("instance_of", "item", "unit"),
    edge("references", "build", "unit"),
]


def change(identity: str, **fields: Any) -> list[dict]:
    """The base entities with `fields` set on one of them; a `None` value removes the field."""
    changed = []
    for entity in ENTITIES:
        if entity["id"] == identity:
            entity = {**entity, **fields}
        changed.append({k: v for k, v in entity.items() if v is not None})
    return changed


def without(*identities: str) -> dict:
    """The base target without some entities and the relationships that name them."""
    gone = set(identities)
    return target(
        [e for e in ENTITIES if e["id"] not in gone],
        relationships=[
            r for r in RELATIONSHIPS if gone.isdisjoint({r["source_id"], r["target_id"]})
        ],
    )


def target(entities: list[dict] | None = None, **fields: Any) -> dict:
    return {
        "schema_version": "1.1.0",
        "entities": ENTITIES if entities is None else entities,
        "relationships": RELATIONSHIPS,
        "scopes": [],
        **fields,
    }


def closed(owner: str, entity_kinds: list[str], relationship_kinds: list[str]) -> dict:
    return {
        "scope_id": owner,
        "mode": "closed",
        "rationale": "Keep it closed.",
        "provenance": PROVENANCE,
        "entity_kinds": entity_kinds,
        "relationship_kinds": relationship_kinds,
    }


def edit(old: str, new: str) -> dict[str, str]:
    assert old in SOURCE
    return {**FILES, "src/a/one.ts": SOURCE.replace(old, new)}


BROKEN = {"src/b/bad.ts": "export const = ;\n"}


def more(*entities: dict, **fields: Any) -> dict:
    return target([*ENTITIES, *entities], **fields)


# name: (files, UML target, row of 4.0.1, row of the core)
PLANTS: dict[str, tuple[dict[str, str], dict, str, str]] = {
    "sym-pass": (FILES, target(), "PASS", "PASS"),
    "kind-differs": (FILES, target(change("helper", kind="class", signature=None)), "FAIL", "FAIL"),
    "parent-differs": (FILES, target(change("run", parent_id="unit")), "FAIL", "FAIL"),
    "return-differs": (
        FILES,
        target(change("helper", signature=signature("number", param("value")))),
        "FAIL",
        "FAIL",
    ),
    "parameter-name-differs": (
        FILES,
        target(change("helper", signature=signature("string", param("val")))),
        "FAIL",
        "FAIL",
    ),
    "parameter-count-differs": (
        FILES,
        target(change("helper", signature=signature("string", param("value"), param("more")))),
        "FAIL",
        "FAIL",
    ),
    "visibility-differs": (FILES, target(change("token", visibility=PUBLIC)), "FAIL", "FAIL"),
    "annotation-differs": (FILES, target(change("token", annotation="number")), "FAIL", "FAIL"),
    "initializer-differs": (
        FILES,
        target(change("item", initializer="new Other()")),
        "FAIL",
        "FAIL",
    ),
    "initializer-equal": (
        FILES,
        target(change("item", initializer="new Unit()")),
        "PASS",
        "PASS",
    ),
    "absent-symbol": (
        FILES,
        more(sym("ghost", "function", "ghost", signature=signature("void"))),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "ambiguous-name": (
        edit(
            "export type Text",
            "export function helper(value: number): string { return ''; }\nexport type Text",
        ),
        target(),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "namespace-interface": (
        edit(
            "export type Text", "export interface Both {}\nexport const Both = 1;\nexport type Text"
        ),
        more(sym("both", "interface", "Both")),
        "PASS",
        "PASS",
    ),
    "namespace-constant": (
        edit(
            "export type Text", "export interface Both {}\nexport const Both = 1;\nexport type Text"
        ),
        more(sym("both", "constant", "Both")),
        "PASS",
        "PASS",
    ),
    "namespace-class": (
        edit(
            "export type Text", "export interface Both {}\nexport const Both = 1;\nexport type Text"
        ),
        more(sym("both", "class", "Both")),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "missing-call": (
        FILES,
        target(relationships=[*RELATIONSHIPS, edge("calls", "helper", "build")]),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "closed-calls-listed": (
        FILES,
        target(
            relationships=[*RELATIONSHIPS, edge("calls", "build", "unit")],
            scopes=[closed("one", [], ["calls"])],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "unresolved-call-site": (
        edit("return helper(value); }", "return helper(value) + (value as any).go(); }"),
        target(
            relationships=[*RELATIONSHIPS, edge("calls", "build", "unit")],
            scopes=[closed("one", [], ["calls"])],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "missing-base": (
        FILES,
        target(relationships=[*RELATIONSHIPS, edge("inherits", "client", "unit")]),
        "FAIL",
        "FAIL",
    ),
    "missing-base-incomplete": (
        {**FILES, **BROKEN},
        target(relationships=[*RELATIONSHIPS, edge("inherits", "client", "unit")]),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "present-base": (
        edit("export class Client implements", "export class Client extends Unit implements"),
        target(relationships=[*RELATIONSHIPS, edge("inherits", "client", "unit")]),
        "PASS",
        "PASS",
    ),
    "closed-function": (
        FILES,
        without("build", "item") | {"scopes": [closed("one", ["function"], [])]},
        "FAIL",
        "FAIL",
    ),
    "closed-calls": (
        FILES,
        target(relationships=[], scopes=[closed("one", [], ["calls"])]),
        "FAIL",
        "FAIL",
    ),
    "closed-method-extra": (
        FILES,
        without("run") | {"scopes": [closed("client", ["method"], [])]},
        "FAIL",
        "FAIL",
    ),
    "closed-method-listed": (
        FILES,
        target(scopes=[closed("client", ["method"], [])]),
        "PASS",
        "UNKNOWN",
    ),
    "referenced-found": (
        FILES,
        more(
            referenced("ref", "function", "helper"),
            relationships=[*RELATIONSHIPS, edge("calls", "run", "ref")],
        ),
        "PASS",
        "PASS",
    ),
    "referenced-kind-differs": (
        FILES,
        more(
            referenced("ref", "class", "helper"),
            relationships=[*RELATIONSHIPS, edge("calls", "run", "ref")],
        ),
        "PASS",
        "PASS",
    ),
    "referenced-absent": (
        FILES,
        more(
            referenced("ref", "function", "nothing"),
            relationships=[*RELATIONSHIPS, edge("calls", "run", "ref")],
        ),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "missing-base-unresolved": (
        edit(
            "export class Client implements",
            "export class Client extends (globalThis as any).Base implements",
        ),
        target(relationships=[*RELATIONSHIPS, edge("inherits", "client", "unit")]),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "missing-base-external": (
        edit(
            "export class Client implements",
            "import { Ext } from 'external-lib';\nexport class Client extends Ext implements",
        ),
        target(relationships=[*RELATIONSHIPS, edge("inherits", "client", "unit")]),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "global-name-is-no-definition": (
        FILES,
        more({**sym("string", "class", "x", parent=None), "qualified_name": "String"}),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "symbol-named-as-module": (
        FILES,
        more({**sym("named", "class", "x", parent=None), "qualified_name": ONE}),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "missing-base-inner-unresolved": (
        edit(
            "run(value: number): string { return helper(value); }",
            "run(value: number): string { class Inner extends (globalThis as any).B {} "
            "return helper(value); }",
        ),
        target(relationships=[*RELATIONSHIPS, edge("inherits", "client", "unit")]),
        "UNKNOWN",
        "UNKNOWN",
    ),
    "closed-kind-differs": (
        FILES,
        target(
            change("helper", kind="class", signature=None), scopes=[closed("one", ["function"], [])]
        ),
        "FAIL",
        "FAIL",
    ),
    "closed-calls-kind-differs": (
        FILES,
        target(
            relationships=[
                edge("references", "run", "helper"),
                edge("calls", "build", "unit"),
            ],
            scopes=[closed("one", [], ["calls"])],
        ),
        "FAIL",
        "FAIL",
    ),
    "pass-incomplete": ({**FILES, **BROKEN}, target(), "UNKNOWN", "UNKNOWN"),
}


# The named cause of each row that is not PASS: a part of the reason of an UNKNOWN row, or of the
# cause of a FAIL detail. A row with another cause is another defect.
CAUSES: dict[str, str | tuple[str, ...]] = {
    "kind-differs": "recorded entity kind differs",
    "parent-differs": "lexical parent differs",
    "return-differs": "return annotation differs",
    "parameter-name-differs": "parameter name or order differs",
    "parameter-count-differs": "parameter count differs",
    "visibility-differs": "visibility or its basis differs",
    "annotation-differs": "annotation differs",
    "initializer-differs": "initializer syntax differs",
    "absent-symbol": "absent symbol",
    "ambiguous-name": "several definitions share a declared name",
    "namespace-class": "several definitions share a declared name",
    "missing-call": "unresolved calls site",
    "closed-calls": "closed scope holds an unlisted relationship",
    "closed-calls-listed": "closed scope completeness",
    "unresolved-call-site": "closed scope completeness",
    "missing-base": "declared base is absent",
    "missing-base-incomplete": "inherits inventory is not complete",
    "missing-base-unresolved": "unresolved inherits site",
    "missing-base-external": "unresolved inherits site",
    "closed-function": "closed scope holds an unlisted definition",
    "closed-method-extra": "closed scope holds an unlisted definition",
    "closed-method-listed": "closed scope completeness",
    "referenced-absent": "relationship endpoints cannot be identified uniquely",
    "global-name-is-no-definition": "absent symbol",
    "symbol-named-as-module": "absent symbol",
    "missing-base-inner-unresolved": "inherits inventory is not complete",
    "closed-kind-differs": (
        "recorded entity kind differs",
        "closed scope holds an unlisted definition",
    ),
    "closed-calls-kind-differs": "closed scope holds an unlisted relationship",
    "pass-incomplete": "the scope of the run is not complete",
}


# The core PASS needs resolved definitions and a complete scope. Where 4.0.1 passes on partial
# coverage, the core stays UNKNOWN (AD-502 lists the forms). Any other difference is a bug.
STRICTER = {("PASS", "UNKNOWN")}


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_core_row_is_never_weaker_than_the_release_row(name: str) -> None:
    _, _, release, core = PLANTS[name]
    assert release == core or (release, core) in STRICTER


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_symbol_row_is_the_pinned_row(release_core: Path, tmp_path: Path, name: str) -> None:
    files, uml, _, expected = PLANTS[name]
    done = command(release_core, project(tmp_path, files, uml, None), "--json")
    result = json.loads(done.stdout)
    assert "refusal" not in result, result
    assert result["frame"]["rules"][ROW] == ["uml_target", expected], result["frame"]["explained"]
    causes = CAUSES.get(name, "")
    causes = (causes,) if isinstance(causes, str) else causes
    if expected == "FAIL":
        found = {item["cause"] for item in result["frame"]["details"][ROW]}
        assert found == set(causes), found
        assert done.returncode == 1
    if expected == "PASS":
        assert result["status"] == "PASS" and done.returncode == 0, result["frame"]
        assert name not in CAUSES
    if expected == "UNKNOWN":
        assert causes[0] in result["frame"]["explained"][ROW], result["frame"]["explained"][ROW]
        assert result["frame"]["unknown_kinds"][ROW] == "no_receipt"
        assert done.returncode == 2
