# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Draft `archkeel.toml` and a first contract for a Python project (AD-626).

The draft reads the folder layout only: no source, no import, no fact. It names each top-level
subpackage as one component and leaves every decision to the user: each responsibility and each
rationale is the word `TODO`, which the core reports as open. The draft decides nothing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

CONFIG: Final = "archkeel.toml"
CONTRACT: Final = "architecture-contract.json"
# A contract must cite a file that exists, and a cited document must hold the marked component
# graph (release 4.0.1 wrote it too). The draft draws the components and no edge: the core then
# reports `graph.drift` with the edges that it found, and that list is the first decision to make.
PROVENANCE: Final = "docs/architecture/architecture.md"
DOCUMENT: Final = "https://github.com/rapiddweller/archkeel/blob/main/docs/onboarding.md"
_SCHEMA: Final = "3.14.0"


class NothingToDraft(ValueError):
    """The layout names no single Python package: the user writes the configuration by hand."""


@dataclass(frozen=True)
class Draft:
    """The three files of a draft, as text, and the scan root and components they name."""

    config: str
    contract: str
    document: str
    root: str
    namespace: str
    components: tuple[str, ...]
    note: str = ""


def _packages(folder: Path) -> list[Path]:
    return sorted(
        path for path in folder.iterdir() if path.is_dir() and (path / "__init__.py").is_file()
    )


def _identifier(label: str) -> str:
    return "COMP-" + re.sub(r"[^A-Z0-9]+", "-", label.upper()).strip("-")


def _document(components: tuple[str, ...]) -> str:
    nodes = "".join(f"    {label}\n" for label in components)
    return (
        "# Architecture\n\nTODO: write the decisions of this architecture here.\n\n"
        f"<!-- archkeel-component-graph -->\n```mermaid\ngraph TD\n{nodes}```\n"
    )


def draft(root: Path) -> Draft:
    """Draft the files for the one top-level Python package below `root` (or `root/src`)."""
    base = root / "src" if (root / "src").is_dir() else root
    found = _packages(base)
    if len(found) != 1:
        names = ", ".join(path.relative_to(root).as_posix() for path in found) or "none"
        where = base.relative_to(root).as_posix()
        raise NothingToDraft(
            f"expected one top-level Python package in {where} (a folder with __init__.py); "
            f"found: {names}. Write {CONFIG} by hand: {DOCUMENT}"
        )
    package = found[0]
    namespace, scan_root = package.name, package.relative_to(root).as_posix()
    subpackages = _packages(package)
    inside = {path.name for path in subpackages}
    modules = [namespace] + [
        f"{namespace}.{path.stem}"
        for path in sorted(package.glob("*.py"))
        if path.stem != "__init__" and path.stem not in inside
    ]
    parts: list[dict[str, object]] = [
        _component(path.name, [f"{namespace}.{path.name}"], []) for path in subpackages
    ]
    # The modules beside the subpackages need an owner, or no rule can pass.
    parts.append(_component("root", [], modules))
    rules = [
        _rule("ASSIGNMENT-COMPLETE", "complete_assignment", source=namespace),
        _rule("COMPONENT-NO-CYCLES", "no_component_cycles"),
    ]
    labels = tuple(str(part["label"]) for part in parts)
    contract = {"schema_version": _SCHEMA, "components": parts, "rules": rules}
    config = (
        f'[scan]\nlanguage = "python"\nnamespace = "{namespace}"\n'
        f'roots = ["{scan_root}"]\ncontract = "{CONTRACT}"\n'
    )
    return Draft(
        config,
        json.dumps(contract, indent=2) + "\n",
        _document(labels),
        scan_root,
        namespace,
        labels,
        _note(root),
    )


def _note(root: Path) -> str:
    """A hint for the one input that the draft cannot give: the Python range of the project."""
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and "requires-python" in pyproject.read_text(encoding="utf-8"):
        return ""
    return (
        "pyproject.toml has no [project].requires-python: the core cannot prove the scan scope "
        "(UNKNOWN: scope_proof) until it does."
    )


def _component(label: str, packages: list[str], modules: list[str]) -> dict[str, object]:
    return {
        "id": _identifier(label),
        "label": label,
        "role": "component",
        "packages": packages,
        "exact_modules": modules,
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


def write_draft(root: Path) -> Draft:
    """Write the draft below `root`. A file that exists is never replaced."""
    existing = [name for name in (CONFIG, CONTRACT, PROVENANCE) if (root / name).exists()]
    if existing:
        raise FileExistsError(
            f"{', '.join(existing)} in {root} exist already; init replaces no file"
        )
    result = draft(root)
    (root / CONFIG).write_text(result.config, encoding="utf-8")
    (root / CONTRACT).write_text(result.contract, encoding="utf-8")
    (root / PROVENANCE).parent.mkdir(parents=True, exist_ok=True)
    (root / PROVENANCE).write_text(result.document, encoding="utf-8")
    return result
