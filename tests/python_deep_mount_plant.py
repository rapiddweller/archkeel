# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A three-level mount tree for the interface lifecycle (AD-514, amended; #880).

`pkg.main` imports `Thing` from `pkg.app.core.a.mod`. The root component `app` mounts `app.json`;
its component `core` mounts `core.json`; the component `a` of `core.json` publishes `Thing`.
The import crosses three boundaries (`core.json`, `app.json`, the root). Each variant changes who
publishes `Thing`; `four` is the `interface.*` finding of release 4.0.1 (`validate --json` of an
installed 4.0.1 on the same tree), by contract file and pointer.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GRAPH = (
    "# Target\n\n<!-- archkeel-component-graph -->\n```mermaid\ngraph TD\n    main --> app\n```\n"
)
PROJECT = '[project]\nname = "pkg"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
SCAN = '[scan]\nroots = ["pkg"]\nnamespace = "pkg"\ncontract = "architecture-contract.json"\n'
THING = "pkg.app.core.a.mod:Thing"


def rules(source: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "INTERFACE-BOUNDARY",
            "kind": "interface_boundary",
            "decided_by": "agent",
            "rationale": "Callers use the declared API.",
            "provenance": ["docs/target.md"],
            "include_type_checking": True,
        },
        {
            "id": "NO-CYCLES",
            "kind": "no_component_cycles",
            "decided_by": "agent",
            "rationale": "Dependencies run one way.",
            "provenance": ["docs/target.md"],
        },
        {
            "id": "REQUIRES-COMPLETE",
            "kind": "complete_requires",
            "decided_by": "agent",
            "rationale": "Each import is declared.",
            "provenance": ["docs/target.md"],
        },
        {
            "id": "ASSIGNMENT-COMPLETE",
            "kind": "complete_assignment",
            "source": source,
            "decided_by": "agent",
            "rationale": "Each module has an owner.",
            "provenance": ["docs/target.md"],
        },
    ]


def component(label: str, packages: list[str], public: list[str] | None, **more: Any) -> dict:
    found = {
        "id": label,
        "label": label,
        "role": "component",
        "packages": packages,
        "responsibilities": [f"{label}."],
        "forbidden_responsibilities": [],
        "provenance": ["docs/target.md"],
        "decided_by": "agent",
        "requires": [],
    }
    if public is not None:
        found["public"] = public
    return {**found, **more}


def contracts() -> dict[str, dict[str, Any]]:
    def base(source: str) -> dict[str, Any]:
        return {"schema_version": "2.2.0", "rules": rules(source)}

    return {
        "architecture-contract.json": {
            **base("pkg"),
            "components": [
                component(
                    "main",
                    [],
                    None,
                    exact_modules=["pkg", "pkg.main"],
                    requires=[
                        {
                            "component": "app",
                            "through": [THING],
                            "rationale": "The main package builds a Thing.",
                            "decided_by": "agent",
                        }
                    ],
                ),
                component("app", ["pkg.app"], [THING], inside="app.json"),
            ],
        },
        "app.json": {
            **base("pkg.app"),
            "components": [
                component("core", ["pkg.app.core"], [THING], inside="core.json"),
                component("edge", ["pkg.app.edge"], [], exact_modules=["pkg.app"]),
            ],
        },
        "core.json": {
            **base("pkg.app.core"),
            "components": [
                component("a", ["pkg.app.core.a"], [THING]),
                component("b", ["pkg.app.core.b"], [], exact_modules=["pkg.app.core"]),
            ],
        },
    }


@dataclass(frozen=True)
class Variant:
    name: str
    change: Callable[[dict[str, dict[str, Any]]], None]
    # The finding of 4.0.1 as (code, file, pointer), or None when it gives none.
    four: tuple[str, str, str] | None


def _public(file: str, label: str, entries: list[str]) -> Callable[[dict], None]:
    def change(found: dict[str, dict[str, Any]]) -> None:
        next(c for c in found[file]["components"] if c["label"] == label)["public"] = entries

    return change


def variants() -> list[Variant]:
    return [
        Variant("every boundary publishes the entry", lambda _: None, None),
        Variant(
            "the root component does not publish it",
            _public("architecture-contract.json", "app", []),
            ("interface.unused", "app.json", "/components/0/public/0"),
        ),
        Variant(
            "the middle component does not publish it",
            _public("app.json", "core", []),
            ("interface.unused", "core.json", "/components/0/public/0"),
        ),
    ]


def build(root: Path, variant: Variant) -> Path:
    found = contracts()
    variant.change(found)
    files = {
        "pkg/__init__.py": "",
        "pkg/app/__init__.py": "",
        "pkg/app/core/__init__.py": "",
        "pkg/app/core/a/__init__.py": "",
        "pkg/app/core/a/mod.py": "class Thing: ...\n",
        "pkg/app/core/b/__init__.py": "",
        "pkg/app/edge/__init__.py": "",
        "pkg/main/__init__.py": "from pkg.app.core.a.mod import Thing\n\nvalue = Thing()\n",
        "docs/target.md": GRAPH,
        "pyproject.toml": PROJECT,
        "archkeel.toml": SCAN,
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    for name, contract in found.items():
        (root / name).write_text(json.dumps(contract, indent=1))
    return root
