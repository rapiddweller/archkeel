# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Collect Dart directive facts without architecture policy."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from archkeel.analyzer.runtime import collector_provenance
from archkeel.ir.facts import (
    BuiltinTarget,
    Capabilities,
    CollectionCoverage,
    ExternalPackageTarget,
    FactSection,
    FileFact,
    ImportTarget,
    LocalTarget,
    Record,
    ResolutionInput,
    SourceFacts,
    SourceInfo,
    SourceSectionName,
    UnresolvedTarget,
    stable_id,
)
from archkeel.ir.facts_codec import RawRecord, parse_evidence, parse_record
from archkeel.ir.protocol import CollectionRequest
from archkeel.ir.reexports import resolve_reexports

from .resolve import DartSources, read_dart_sources

_SECTION_NAMES: tuple[SourceSectionName, ...] = ("imports", "unknowns")


def collect(request: CollectionRequest) -> SourceFacts:
    """Collect source facts from every selected Dart file, including library parts."""
    root = Path(request.snapshot.root).resolve()
    sources = read_dart_sources(
        root,
        roots=request.scope.roots,
        namespace=request.scope.namespace,
    )
    inputs, digest = _inputs(root, sources)
    files = tuple(
        FileFact(
            stable_id("FILE", library.module),
            library.rel_path,
            library.module,
            library.package,
            library.all_exports,
            library.all_literal,
            library.compatibility_logic_free,
            frozenset(),
            library.module in sources.blank_modules,
            sources.module_evidence[library.module],
        )
        for library in sources.libraries
    )
    uncertain = resolve_reexports(sources.imports, {})
    imports = tuple(_targets(sources.imports, files))
    unknowns = [parse_record(item) for item in sources.failures]
    records: dict[SourceSectionName, tuple[Record, ...]] = {name: () for name in _SECTION_NAMES}
    records["imports"] = tuple(parse_record(item) for item in sources.imports)
    records["unknowns"] = tuple(unknowns)
    adapter, runtime = collector_provenance("dart")
    return SourceFacts(
        "archkeel-dart-directives",
        adapter,
        runtime,
        SourceInfo(
            request.snapshot.git_head,
            request.snapshot.dirty,
            digest,
            tuple(f"{source}/**/*.dart" for source in request.scope.roots),
        ),
        Capabilities(_SECTION_NAMES),
        inputs,
        files,
        imports,
        tuple(FactSection(name, records[name]) for name in _SECTION_NAMES),
        CollectionCoverage(
            tuple(path.relative_to(root).as_posix() for path in sources.paths),
            sources.files_read,
            sources.files_parsed,
            sources.files_parsed == len(sources.paths) and not sources.failures,
            tuple(unknowns),
        ),
        tuple(parse_evidence(item) for item in sources.evidence),
        tuple((binding, tuple(sorted(origins))) for binding, origins in sorted(uncertain.items())),
    )


def _inputs(root: Path, sources: DartSources) -> tuple[tuple[ResolutionInput, ...], str]:
    paths: dict[str, tuple[Path, Literal["selected", "resolution"]]] = {
        path.relative_to(root).as_posix(): (path, "selected") for path in sources.paths
    }
    pubspec = root / "pubspec.yaml"
    if pubspec.is_file() and pubspec.resolve().is_relative_to(root):
        paths["pubspec.yaml"] = (pubspec, "resolution")
    inputs: list[ResolutionInput] = []
    digest = hashlib.sha256()
    for rel_path, (path, role) in sorted(paths.items()):
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        inputs.append(ResolutionInput(rel_path, hashlib.sha256(raw).hexdigest(), role))
        digest.update(rel_path.encode("utf-8") + b"\0" + raw + b"\0")
    return tuple(inputs), digest.hexdigest()


def _targets(imports: list[RawRecord], files: tuple[FileFact, ...]) -> list[ImportTarget]:
    modules = {item.module: item for item in files}
    targets: list[ImportTarget] = []
    for record in imports:
        data = record["data"]
        module = data.get("target_module")
        import_id = record["id"]
        if not isinstance(module, str):
            targets.append(
                UnresolvedTarget(import_id, str(module or ""), "directive target unavailable")
            )
        elif module in modules:
            targets.append(LocalTarget(import_id, module, modules[module].rel_path))
        elif module.startswith("dart."):
            targets.append(BuiltinTarget(import_id, module))
        else:
            package = data.get("target_package")
            if isinstance(package, str) and package:
                targets.append(ExternalPackageTarget(import_id, package))
            else:
                targets.append(UnresolvedTarget(import_id, module, "library source not found"))
    return targets
