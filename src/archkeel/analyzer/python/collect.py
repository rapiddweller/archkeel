# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Collect Python source facts without loading or interpreting architecture policy."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Literal

from archkeel.analyzer.runtime import (
    collector_provenance,
    python_requirement,
)
from archkeel.ir.facts import (
    BuiltinTarget,
    Capabilities,
    CollectionCoverage,
    ConstructCapability,
    ConstructSupport,
    Evidence,
    ExternalPackageTarget,
    FactSection,
    FileFact,
    ForbiddenConstructKind,
    ImportTarget,
    LocalTarget,
    ResolutionInput,
    SourceFacts,
    SourceInfo,
    SourceSectionName,
    UnresolvedTarget,
    stable_id,
)
from archkeel.ir.facts_codec import RawEvidence, RawRecord, parse_evidence, parse_record, raw_record
from archkeel.ir.protocol import CollectionRequest

from .bindings import collect_bindings
from .calls import collect_calls
from .constructs import collect_constructs
from .imports import collect_imports, resolve_reexports
from .private_attributes import collect_private_attributes
from .references import collect_references
from .resolve import build_symbol_index
from .source import file_evidence, parse_sources, stable_direct_module_bindings
from .state import collect_state
from .symbols import collect_symbols
from .type_shapes import collect_type_shapes, symbol_type_expressions
from .typing_signals import collect_typing_signals

_SECTION_NAMES: tuple[SourceSectionName, ...] = (
    "symbols",
    "imports",
    "calls",
    "references",
    "bindings",
    "typing_signals",
    "constructs",
    "unknowns",
)


def collect(request: CollectionRequest) -> SourceFacts:
    """Collect all source-only facts selected by a Python collection request."""
    root = Path(request.snapshot.root).resolve()
    selected = tuple(
        sorted(
            path
            for source_root in (root / source for source in request.scope.roots)
            if source_root.is_dir()
            for path in source_root.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    )
    selected = tuple(path for path in selected if path.resolve().is_relative_to(root))
    parsed_sources = parse_sources(selected, root=root, namespace=request.scope.namespace)
    modules = parsed_sources.modules
    evidence: dict[str, RawEvidence] = {}

    imports = collect_imports(
        modules,
        {module.module for module in modules},
        evidence,
        namespace=request.scope.namespace,
    )
    uncertain = resolve_reexports(
        imports,
        {module.module: module.all_exports for module in modules},
        modules,
    )
    symbols, symbol_nodes, symbol_owners = collect_symbols(modules, evidence)
    type_shapes = collect_type_shapes(symbol_type_expressions(symbols))
    symbol_index = build_symbol_index(symbols)
    calls = collect_calls(modules, symbol_index, evidence)
    references = collect_references(modules, symbol_index, evidence)
    bindings = collect_bindings(modules, evidence)
    typing_signals = collect_typing_signals(modules, calls, symbols, imports, evidence)
    constructs = collect_constructs(modules, evidence)
    typed_symbols = tuple(parse_record(symbol) for symbol in symbols)
    state, state_evidence = collect_state(modules, typed_symbols, symbol_nodes, symbol_owners)
    source_unknowns, private_evidence = collect_private_attributes(modules)
    candidate_by_id = {item.id: item for item in state_evidence}

    files = tuple(
        FileFact(
            stable_id("FILE", module.module),
            module.rel_path,
            module.module,
            module.package,
            frozenset(module.all_exports),
            module.all_literal,
            module.compatibility_logic_free,
            stable_direct_module_bindings(module),
            not module.tree.body,
            file_evidence(evidence, module.rel_path, module.lines),
        )
        for module in modules
    )
    inputs, source_digest = _inputs(root, selected)
    import_targets = _import_targets(imports, files)
    records: dict[SourceSectionName, list[RawRecord]] = {
        "symbols": symbols,
        "imports": imports,
        "calls": calls,
        "references": references,
        "bindings": bindings,
        "typing_signals": typing_signals,
        "constructs": constructs,
        "unknowns": [
            *parsed_sources.failures,
            *(raw_record(record) for record in source_unknowns),
        ],
    }
    for item in private_evidence:
        evidence[item.id] = _raw_evidence(item)

    required, requirement_state = python_requirement(root)
    adapter, runtime = collector_provenance(
        "python", required=required, requirement_state=requirement_state
    )
    return SourceFacts(
        "archkeel-python-analyzer",
        adapter,
        runtime,
        SourceInfo(
            request.snapshot.git_head,
            request.snapshot.dirty,
            source_digest,
            tuple(f"{source}/**/*.py" for source in request.scope.roots),
        ),
        Capabilities(
            _SECTION_NAMES,
            constructs=tuple(
                ConstructCapability(kind, ConstructSupport.DECIDED)
                for kind in ForbiddenConstructKind
            ),
        ),
        inputs,
        files,
        import_targets,
        tuple(
            FactSection(name, tuple(parse_record(record) for record in records[name]))
            for name in _SECTION_NAMES
        ),
        CollectionCoverage(
            tuple(path.relative_to(root).as_posix() for path in selected),
            parsed_sources.files_read,
            len(modules),
            len(modules) == len(selected),
            tuple(parse_record(record) for record in parsed_sources.failures),
        ),
        tuple(parse_evidence(evidence[key]) for key in sorted(evidence)),
        tuple((binding, tuple(sorted(origins))) for binding, origins in sorted(uncertain.items())),
        tuple(sorted(type_shapes.items())),
        state,
        tuple(sorted(candidate_by_id.values(), key=lambda item: item.id)),
    )


def _raw_evidence(item: Evidence) -> RawEvidence:
    return {
        "id": item.id,
        "file": item.file,
        "line": item.line,
        "end_line": item.end_line,
        "column": item.column,
        "excerpt": item.excerpt,
    }


def _inputs(root: Path, selected: tuple[Path, ...]) -> tuple[tuple[ResolutionInput, ...], str]:
    paths: dict[str, tuple[Path, Literal["selected", "resolution"]]] = {
        path.relative_to(root).as_posix(): (path, "selected") for path in selected
    }
    config = root / "pyproject.toml"
    if config.is_file() and config.resolve().is_relative_to(root):
        paths["pyproject.toml"] = (config, "resolution")
    inputs: list[ResolutionInput] = []
    source = hashlib.sha256()
    for rel_path, (path, role) in sorted(paths.items()):
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        digest = hashlib.sha256(raw).hexdigest()
        inputs.append(ResolutionInput(rel_path, digest, role))
        source.update(rel_path.encode("utf-8") + b"\0" + raw + b"\0")
    return tuple(inputs), source.hexdigest()


def _import_targets(
    imports: list[RawRecord], files: tuple[FileFact, ...]
) -> tuple[ImportTarget, ...]:
    by_module = {file.module: file for file in files}
    targets: list[ImportTarget] = []
    for item in imports:
        data = item["data"]
        if not isinstance(data, dict):
            continue
        import_id = item["id"]
        module = data.get("target_module")
        package = data.get("target_package")
        if not isinstance(module, str) or not isinstance(package, str):
            targets.append(
                UnresolvedTarget(import_id, str(module or ""), "target identity unavailable")
            )
        elif module in by_module:
            file = by_module[module].rel_path
            targets.append(LocalTarget(import_id, module, file))
        elif module in sys.stdlib_module_names or module == "builtins":
            targets.append(BuiltinTarget(import_id, module))
        elif package:
            targets.append(ExternalPackageTarget(import_id, package))
        else:
            targets.append(UnresolvedTarget(import_id, module, "module source not found"))
    return tuple(targets)
