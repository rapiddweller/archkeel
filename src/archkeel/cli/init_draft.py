# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Draft `archkeel.toml` and a first contract from the folder layout of a project (AD-626, AD-638).

The draft reads the layout only (`init_layouts`): no source, no import, no fact. It names each
component the layout shows and leaves every decision to the user: each responsibility and each
rationale is the word `TODO`, which the core reports as open. The draft decides nothing. A file
that exists is never replaced.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .init_layouts import DOCUMENT, Layout, NothingToDraft, Part, detect

__all__ = ["CONFIG", "CONTRACT", "DOCUMENT", "PROVENANCE", "Draft", "NothingToDraft", "draft"]
CONFIG: Final = "archkeel.toml"
CONTRACT: Final = "architecture-contract.json"
# A contract must cite a file that exists, and a cited document must hold the marked component
# graph (release 4.0.1 wrote it too). The draft draws the components and no edge: the core then
# reports `graph.drift` with the edges that it found, and that list is the first decision to make.
PROVENANCE: Final = "docs/architecture/architecture.md"
_SCHEMA: Final = "3.14.0"


@dataclass(frozen=True)
class Draft:
    """The three files of a draft, as text, and what they name."""

    config: str
    contract: str
    document: str
    language: str
    namespace: str
    components: tuple[str, ...]
    note: str = ""


def _document(components: tuple[str, ...]) -> str:
    nodes = "".join(f"    {label}\n" for label in components)
    return (
        "# Architecture\n\nTODO: write the decisions of this architecture here.\n\n"
        f"<!-- archkeel-component-graph -->\n```mermaid\ngraph TD\n{nodes}```\n"
    )


def _component(part: Part) -> dict[str, object]:
    return {
        "id": "COMP-" + re.sub(r"[^A-Z0-9]+", "-", part.label.upper()).strip("-"),
        "label": part.label,
        "role": "component",
        "packages": list(part.packages),
        "exact_modules": list(part.modules),
        # `decided_by: architect` with the word TODO: the core reports `responsibility.missing`.
        "responsibilities": ["TODO"],
        "forbidden_responsibilities": [],
        "provenance": [PROVENANCE],
        "decided_by": "architect",
        "public": [],
    }


def _rule(identifier: str, kind: str, **fields: str) -> dict[str, object]:
    return {
        "id": identifier,
        "kind": kind,
        **fields,
        "rationale": "TODO: say why this rule holds.",
        "provenance": [PROVENANCE],
        "decided_by": "architect",
    }


def _toml(layout: Layout) -> str:
    roots = ", ".join(f'"{root}"' for root in layout.roots)
    return (
        f'[scan]\nlanguage = "{layout.language}"\nnamespace = "{layout.namespace}"\n'
        f'roots = [{roots}]\ncontract = "{CONTRACT}"\n{layout.extra}'
    )


def draft(root: Path) -> Draft:
    """Draft the files for the layout of `root`, or raise `NothingToDraft`."""
    layout = detect(root)
    rules = [
        _rule("ASSIGNMENT-COMPLETE", "complete_assignment", source=layout.namespace),
        _rule("COMPONENT-NO-CYCLES", "no_component_cycles"),
    ]
    parts = [part for part in layout.parts if part.packages or part.modules]
    labels = tuple(part.label for part in parts)
    contract = {
        "schema_version": _SCHEMA,
        "components": [_component(part) for part in parts],
        "rules": rules,
    }
    return Draft(
        _toml(layout),
        json.dumps(contract, indent=2) + "\n",
        _document(labels),
        layout.language,
        layout.namespace,
        labels,
        layout.note,
    )


def write_missing(root: Path, result: Draft) -> list[str]:
    """Write each file of the draft that does not exist, and return their names.

    The contract and its document are written together, and only when the contract is missing:
    an existing contract is the user's. A file is created exclusively, so a file that appears
    meanwhile is never replaced. A failure removes what this call wrote, then raises `OSError`.
    """
    wanted = {CONFIG: result.config}
    if not (root / CONTRACT).exists():
        wanted |= {CONTRACT: result.contract, PROVENANCE: result.document}
    written: list[Path] = []
    try:
        for name, text in wanted.items():
            target = root / name
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8") as handle:
                written.append(target)
                handle.write(text)
    except OSError:
        for target in written:
            target.unlink(missing_ok=True)
        raise
    return [path.relative_to(root).as_posix() for path in written]
