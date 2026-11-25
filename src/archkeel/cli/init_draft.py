# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Draft `archkeel.toml` and a first contract, or a system of them (AD-626, AD-638, AD-660).

The draft reads the folder layout and the manifests only (`init_areas`): no source, no import, no
fact. It names each component the layout shows and leaves every decision to the user: each
responsibility and each rationale is the word `TODO`, which the core reports as open. The draft
decides nothing. A file that exists is never replaced.

One language area gives `archkeel.toml`, a contract and its page at the root. Several areas give a
system: `docs/architecture/architecture-system.json` with one part for each area, and for each part
a configuration, a contract and a page in `docs/architecture/<part>/`.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .init_areas import (
    _IGNORED,
    DOCUMENT,
    Area,
    Layout,
    NothingToDraft,
    Part,
    _dart_layout,
    _folders,
    _python_layouts,
    _python_one_script,
    _rust_layout,
    _slug,
)
from .init_binding import _binding, _uses
from .init_preset import Shape
from .init_typescript import _typescript_layout, _typescript_project

__all__ = [
    "CONFIG",
    "CONTRACT",
    "DOCUMENT",
    "SYSTEM",
    "Draft",
    "NothingToDraft",
    "draft",
    "write_missing",
]


# Which language areas a repository has; `init_areas` drafts the layout of one folder.
def _workspaces(folder: Path) -> bool:
    try:
        data = json.loads((folder / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and bool(data.get("workspaces"))


def _layout_of(repo: Path, folder: Path) -> Layout | None:
    """The layout of a Cargo, package.json or pubspec manifest in `folder`, or `None`."""
    if (folder / "Cargo.toml").is_file() and (layout := _rust_layout(repo, folder)):
        return layout
    if (folder / "package.json").is_file():
        # One scan of all workspace members needs one tsconfig that covers them. Without a root
        # tsconfig.json each member with its own is a project of its own, found below.
        if _workspaces(folder) and (folder / "tsconfig.json").is_file():
            return _typescript_layout(repo, folder)
        if (folder / "tsconfig.json").is_file():
            return _typescript_project(repo, folder)
    if (folder / "pubspec.yaml").is_file():
        return _dart_layout(repo, folder)
    return None


def _discover(repo: Path) -> tuple[list[Area], str]:
    """The areas of `repo`, and the first reason that a folder gave none (for a refusal)."""
    areas: list[Area] = []
    claimed: list[Path] = []
    why = ""
    for folder in _folders(repo):
        if any(folder.is_relative_to(done) for done in claimed):
            continue
        relative = folder.relative_to(repo).as_posix() or "."
        try:
            layout = _layout_of(repo, folder)
            if layout is not None:
                areas.append(Area(relative, layout))
                # The members of a workspace are inside it; a project owns its folder.
                members = [repo / root for root in layout.roots] if _workspaces(folder) else []
                claimed += members or ([folder] if folder != repo else [])
        except NothingToDraft as error:
            why = why or str(error)
        # A Python project can share its folder with a Cargo or Node manifest.
        if folder == repo or any((folder / n).is_file() for n in ("pyproject.toml", "setup.py")):
            try:
                areas += [Area(layout.roots[0], layout) for layout in _python_layouts(repo, folder)]
            except NothingToDraft as error:
                why = why or str(error)
    return areas, why


def _detect(repo: Path, *, observed: bool) -> list[Area]:
    """The areas of the repository, or `NothingToDraft` when it has none."""
    areas, why = _discover(repo)
    if not areas and observed and (layout := _python_one_script(repo)):
        return [Area(".", layout)]
    if not areas:
        raise NothingToDraft(
            why
            or "no Python package, Cargo workspace, TypeScript project or Dart package found "
            "(folder layout and manifest only)."
        )
    return areas


CONFIG: Final = "archkeel.toml"
CONTRACT: Final = "architecture-contract.json"
SYSTEM: Final = "docs/architecture/architecture-system.json"
# A contract must cite a file that exists, and a cited document must hold the marked component
# graph (release 4.0.1 wrote it too). The draft draws the components and no edge: the core then
# reports `graph.drift` with the edges that it found, and that list is the first decision to make.
_PAGE: Final = "architecture.md"
_FOLDER: Final = "docs/architecture"
_SPEC_DEPTH: Final = 4
_SCHEMA: Final = "3.14.0"
_SPECS: Final = re.compile(r"(openapi|swagger|asyncapi)[^/]*\.(json|ya?ml)$|\.proto$", re.I)


@dataclass(frozen=True)
class File:
    """One file of a draft. `unless` is a path whose existence stops this file: the contract and
    its page belong together, and an existing contract is the user's."""

    path: str
    text: str
    unless: str = ""


@dataclass(frozen=True)
class Draft:
    """The files of a draft and what they name."""

    files: tuple[File, ...]
    language: str
    namespace: str
    components: tuple[str, ...]
    note: str = ""
    parts: tuple[str, ...] = ()
    interfaces: tuple[str, ...] = ()
    entry: str = CONFIG
    # The first `stated` interfaces are stated by the manifests (AD-784); the others are open.
    stated: int = 0


def _page(components: tuple[str, ...]) -> str:
    nodes = "".join(f"    {label}\n" for label in components)
    return (
        "# Architecture\n\nTODO: write the decisions of this architecture here.\n\n"
        f"<!-- archkeel-component-graph -->\n```mermaid\ngraph TD\n{nodes}```\n"
    )


def _component(part: Part, prefix: str, page: str) -> dict[str, object]:
    return {
        "id": "-".join(x for x in ("COMP", prefix, _slug(part.label)) if x),
        "label": part.label,
        "role": "component",
        "packages": list(part.packages),
        "exact_modules": list(part.modules),
        # `decided_by: architect` with the word TODO: the core reports `responsibility.missing`.
        "responsibilities": ["TODO"],
        "forbidden_responsibilities": [],
        "provenance": [page],
        "decided_by": "architect",
        "public": [],
    }


def _rule(
    identifier: str,
    kind: str,
    page: str,
    rationale: str = "TODO: say why this rule holds.",
    **fields: object,
) -> dict[str, object]:
    return {
        "id": identifier,
        "kind": kind,
        **fields,
        "rationale": rationale,
        "provenance": [page],
        "decided_by": "architect",
    }


def _toml(layout: Layout, contract: str) -> str:
    roots = ", ".join(json.dumps(root, ensure_ascii=False) for root in layout.roots)
    return (
        f'[scan]\nlanguage = "{layout.language}"\nnamespace = "{layout.namespace}"\n'
        f'roots = [{roots}]\ncontract = "{contract}"\n{layout.extra}'
    )


def _unit(
    layout: Layout, folder: str, prefix: str, shape: Shape | None = None
) -> tuple[list[File], tuple[str, ...]]:
    """The configuration, the contract and the page of one scan, in `folder` ("" is the root)."""
    at = f"{folder}/" if folder else ""
    contract, page = f"{at}{CONTRACT}", f"{folder or _FOLDER}/{_PAGE}"
    parts = [part for part in layout.parts if part.packages or part.modules]
    labels = tuple(part.label for part in parts)
    ids = (f"{prefix}-ASSIGNMENT-COMPLETE", f"{prefix}-COMPONENT-NO-CYCLES")
    sources = (
        (layout.namespace,)
        if layout.namespace
        else tuple(name for part in parts for name in (*part.packages, *part.modules))
    )
    assignment = [
        _rule(
            ids[0].strip("-") if len(sources) == 1 else f"{ids[0].strip('-')}-{index}",
            "complete_assignment",
            page,
            source=source,
        )
        for index, source in enumerate(sources, 1)
    ]
    preset = (
        shape.rules({part.label: (*part.packages, *part.modules) for part in parts})
        if shape
        else []
    )
    layers = shape.layer_of() if shape else {}
    document = {
        "schema_version": _SCHEMA,
        "components": [
            _component(part, prefix, page)
            | ({"layer": layers[part.label]} if part.label in layers else {})
            for part in parts
        ],
        "rules": [
            *assignment,
            _rule(ids[1].strip("-"), "no_component_cycles", page),
            *(_rule(name, kind, page, why, **fields) for name, kind, why, fields in preset),
        ],
    }
    files = [
        File(f"{at}{CONFIG}", _toml(layout, contract)),
        File(contract, json.dumps(document, indent=2) + "\n", unless=contract),
        File(page, _page(labels), unless=contract),
    ]
    return files, labels


def _files(repo: Path) -> list[Path]:
    """The files of the repository down to four folders, without hidden or generated folders."""
    found = []
    for folder, names, files in os.walk(repo):
        depth = len(Path(folder).relative_to(repo).parts)
        names[:] = sorted(
            name
            for name in names
            if depth < _SPEC_DEPTH and not name.startswith(".") and name not in _IGNORED
        )
        found += [Path(folder) / name for name in sorted(files) if _SPECS.search(name)]
    return found


_NAMES: Final = {"python": "Python", "rust": "Rust", "typescript": "TypeScript", "dart": "Dart"}


def _unique_ids(areas: list[Area]) -> list[str]:
    """One part id for each area: the folder name, or the project name for the root, made
    unique."""
    labels = [area.label for area in areas]
    return [
        label if labels.count(label) == 1 else f"{area.layout.language}-{label}"
        for area, label in zip(areas, labels, strict=True)
    ]


def _title_of(area: Area, identifier: str) -> str:
    """The title of a part: the language and the id."""
    return f"{_NAMES[area.layout.language]} {identifier}"


def _specs(repo: Path, areas: list[Area]) -> list[tuple[str, int]]:
    """The files that state an interface (OpenAPI, Swagger, AsyncAPI, proto), each with the index
    of the area whose folder holds it most closely."""
    found = []
    for path in _files(repo):
        relative = path.relative_to(repo)
        holders = [
            (len(Path(a.folder).parts) if a.folder != "." else 0, i)
            for i, a in enumerate(areas)
            if a.folder == "." or relative.is_relative_to(a.folder)
        ]
        if holders:
            found.append((relative.as_posix(), max(holders)[1]))
    return found


def _bindings(repo: Path, areas: list[Area], ids: list[str]) -> list[dict[str, str]]:
    """The interface from each Python part to each Rust part whose PyO3 binding it uses, as the
    manifests state both ends (AD-784). The title names the module: the binding is stated."""
    found: list[dict[str, str]] = []
    for target, area in enumerate(areas):
        for crate in area.layout.crates:
            stated = _binding(repo, repo / crate)
            if stated is None:
                continue
            for source, user in enumerate(areas):
                project = user.layout.project
                if user.layout.language != "python" or not project:
                    continue
                if _uses(repo / project, repo / crate, stated):
                    found.append(
                        {
                            "id": f"{ids[source]}-to-{ids[target]}-{len(found) + 1}",
                            "source": ids[source],
                            "target": ids[target],
                            "title": f"Python extension module {stated.module} "
                            "(PyO3 binding, maturin)",
                            "schema": stated.schema,
                        }
                    )
    return found


def _system(repo: Path, areas: list[Area], folder: str = _FOLDER) -> Draft:
    ids = _unique_ids(areas)
    files: list[File] = []
    parts, names = [], []
    for area, identifier in zip(areas, ids, strict=True):
        unit, labels = _unit(area.layout, f"{folder}/{identifier}", _slug(identifier))
        files += unit
        names += [f"{identifier}/{label}" for label in labels]
        title = _title_of(area, identifier)
        parts.append(
            {
                "id": identifier,
                "title": title,
                "config": unit[0].path,
                "responsibilities": [f"TODO: state what {title} is responsible for."],
                "forbidden_responsibilities": [f"TODO: state what {title} must not do."],
                "provides": [f"TODO: state what {title} gives to the other parts."],
            }
        )
    interfaces = _bindings(repo, areas, ids)
    stated = len(interfaces)
    for spec, holder in _specs(repo, areas):
        for index, source in enumerate(ids):
            if index != holder:
                interfaces.append(
                    {
                        "id": f"{source}-to-{ids[holder]}-{len(interfaces) + 1}",
                        "source": source,
                        "target": ids[holder],
                        "title": f"TODO: confirm that {source} uses {spec}",
                        "schema": spec,
                    }
                )
    system = {
        "schema_version": "archkeel-system-contract-1",
        "kind": "system",
        "title": repo.name,
        "parts": parts,
        "interfaces": interfaces,
        "rules": [],
    }
    entry = f"{folder}/{Path(SYSTEM).name}"
    files.insert(0, File(entry, json.dumps(system, indent=2) + "\n"))
    languages = ", ".join(sorted({a.layout.language for a in areas}))
    note = " ".join(dict.fromkeys(a.layout.note for a in areas if a.layout.note))
    return Draft(
        tuple(files),
        languages,
        repo.name,
        tuple(names),
        note,
        tuple(_title_of(a, i) for a, i in zip(areas, ids, strict=True)),
        tuple(str(i["id"]) for i in interfaces),
        entry,
        stated,
    )


def draft(root: Path, *, scan_folder: str = "", shape: Shape | None = None) -> Draft:
    """Draft the files for the layout of `root`, or raise `NothingToDraft`.

    A `shape` (a preset with the layers of the user) needs one language area."""
    areas = _detect(root, observed=bool(scan_folder))
    if len(areas) > 1:
        if shape:
            raise NothingToDraft(
                "--preset drafts one language area, and this repository has several "
                f"({', '.join(area.label for area in areas)}). Run `archkeel init --root <folder>`."
            )
        return _system(root, areas, scan_folder or _FOLDER)
    layout = areas[0].layout
    files, labels = _unit(layout, scan_folder, "", shape)
    # One scan at the root keeps the plain names of the rules and components.
    return Draft(
        tuple(files),
        layout.language,
        layout.namespace or areas[0].label,
        labels,
        layout.note,
        entry=files[0].path,
    )


def _blocked(root: Path, item: File) -> bool:
    return (root / item.path).exists() or bool(item.unless and (root / item.unless).exists())


def write_missing(root: Path, result: Draft) -> list[str]:
    """Write each file of the draft that does not exist, and return their names.

    A file whose `unless` path exists is skipped: an existing contract is the user's, and its
    page stays with it. A file is created exclusively, so a file that appears meanwhile is never
    replaced. A failure removes what this call wrote, then raises `OSError`.
    """
    written: list[Path] = []
    # What stops a file is decided before the first write: the contract stops its page, too.
    blocked = {item.path for item in result.files if _blocked(root, item)}
    try:
        for item in result.files:
            target = root / item.path
            if item.path in blocked:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8") as handle:
                written.append(target)
                handle.write(item.text)
    except OSError:
        for target in written:
            target.unlink(missing_ok=True)
        raise
    return [path.relative_to(root).as_posix() for path in written]
