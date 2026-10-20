# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Collect Python source facts without loading or interpreting architecture policy."""

from __future__ import annotations

import ast
import hashlib
import re
import sys
import sysconfig
from dataclasses import dataclass, replace
from importlib.machinery import (
    BYTECODE_SUFFIXES,
    EXTENSION_SUFFIXES,
    BuiltinImporter,
    FrozenImporter,
)
from pathlib import Path, PurePosixPath
from time import monotonic

from archkeel.analyzer.process import ProcessCollector
from archkeel.analyzer.runtime import (
    collector_provenance,
    python_requirement,
)
from archkeel.ir.facts import (
    CALL_ARGUMENTS_FEATURE,
    CALL_BINDINGS_FEATURE,
    EXTENDED_CALL_BINDINGS_FEATURE,
    NATIVE_CALL_TARGETS,
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
    Language,
    LocalTarget,
    ProviderBinding,
    ProviderBindingKind,
    ResolutionInput,
    ResolutionRole,
    SourceFacts,
    SourceInfo,
    SourceProfile,
    SourceSectionName,
    UnresolvedTarget,
    stable_id,
)
from archkeel.ir.facts_codec import RawEvidence, RawRecord, parse_evidence, parse_record, raw_record
from archkeel.ir.protocol import (
    PYTHON_IMPORT_SURVEY_SECTIONS,
    CollectionError,
    CollectionErrorKind,
    CollectionRequest,
    ProtocolVersion,
    PythonCollectionPhase,
    PythonProviderSource,
    PythonSettings,
)

from .bindings import collect_bindings
from .callable_signatures import (
    contextmanager_dependency_bindings,
    contextmanager_signatures,
)
from .calls import collect_calls_with_resolvers
from .constructs import collect_constructs
from .imports import (
    collect_dynamic_imports,
    collect_imports,
    explicit_factory_unsafe_providers,
    resolve_reexports,
)
from .private_attributes import collect_private_attributes
from .references import collect_references
from .resolve import build_symbol_index
from .source import (
    ParsedModule,
    add_evidence,
    class_header_static,
    exposes_dynamic_namespace,
    file_evidence,
    member_binding_closure,
    package_for,
    parse_sources,
    resolve_static_name,
    stable_direct_module_bindings,
    unproven_member_bindings,
)
from .source import (
    provider_source_eligible as _provider_source_eligible,
)
from .state import collect_state
from .symbols import collect_symbols
from .type_shapes import collect_type_shapes, symbol_type_expressions
from .typing_signals import collect_typing_signals

_SECTION_NAMES: tuple[SourceSectionName, ...] = (
    SourceSectionName.SYMBOLS,
    SourceSectionName.IMPORTS,
    SourceSectionName.CALLS,
    SourceSectionName.REFERENCES,
    SourceSectionName.BINDINGS,
    SourceSectionName.TYPING_SIGNALS,
    SourceSectionName.CONSTRUCTS,
    SourceSectionName.UNKNOWNS,
)


@dataclass(frozen=True, slots=True)
class PythonProviderCollector:
    collector: ProcessCollector

    def collect(self, request: CollectionRequest) -> SourceFacts | CollectionError:
        if not (
            isinstance(request.resolver, PythonSettings)
            and request.protocol_version is ProtocolVersion.V3
            and request.resolver.phase is PythonCollectionPhase.COLLECT
            and not request.resolver.provider_sources
        ):
            return self.collector.collect(request)
        deadline = monotonic() + self.collector.timeout_seconds
        timeout = CollectionError(
            CollectionErrorKind.TIMEOUT,
            self.collector.argv[0],
            f"Collector exceeded {self.collector.timeout_seconds:g} seconds.",
        )
        initial_response = self.collector.collect_response(
            replace(
                request,
                resolver=PythonSettings(phase=PythonCollectionPhase.PROVIDERS),
                protocol_version=ProtocolVersion.V4,
            )
        )
        if isinstance(initial_response, CollectionError):
            return initial_response
        initial = initial_response.facts
        if monotonic() >= deadline:
            return timeout
        providers = initial_response.provider_sources
        discovered = {
            item.path: item.digest
            for item in initial.inputs
            if item.path.startswith(".archkeel-providers/")
        }
        if discovered != {item.path: item.digest for item in providers}:
            return CollectionError(
                CollectionErrorKind.PROTOCOL_ERROR,
                self.collector.argv[0],
                "Provider source inputs changed after discovery.",
            )
        remaining = deadline - monotonic()
        if remaining <= 0:
            return timeout
        final_request = (
            replace(
                request,
                resolver=PythonSettings(provider_sources=providers),
                protocol_version=ProtocolVersion.V5,
            )
            if providers
            else replace(request, protocol_version=ProtocolVersion.V5)
        )
        remaining_collector: ProcessCollector = replace(self.collector, timeout_seconds=remaining)
        enriched = remaining_collector.collect(final_request)
        if isinstance(enriched, CollectionError):
            return enriched
        if monotonic() >= deadline:
            return timeout
        if frozenset(enriched.capabilities.sections) != frozenset(_SECTION_NAMES):
            return CollectionError(
                CollectionErrorKind.PROTOCOL_ERROR,
                self.collector.argv[0],
                "Collector did not return complete Python source sections after the import survey.",
            )
        provider_paths = {item.path for item in providers}
        project_inputs = tuple(item for item in enriched.inputs if item.path not in provider_paths)
        if (
            project_inputs
            != tuple(item for item in initial.inputs if item.path not in provider_paths)
            or enriched.profile != initial.profile
            or enriched.adapter != initial.adapter
            or enriched.runtime != initial.runtime
            or enriched.source.scope != initial.source.scope
        ):
            return CollectionError(
                CollectionErrorKind.PROTOCOL_ERROR,
                self.collector.argv[0],
                "Collector source inputs, analyzer, or runtime changed between provider passes.",
            )
        return enriched


def _selected_paths(root: Path, roots: tuple[str, ...]) -> tuple[Path, ...]:
    selected: list[Path] = []
    for source in roots:
        source_root: Path = root / source
        if not source_root.is_dir():
            continue
        for candidate in source_root.rglob("*.py"):
            path: Path = candidate
            if "__pycache__" not in path.parts and path.resolve().is_relative_to(root):
                selected.append(path)
    return tuple(sorted(selected))


def _provider_origin(
    relative: Path, search_roots: tuple[Path, ...], parent: Path | None
) -> Path | None:
    candidates: set[Path] = set()
    for base in search_roots:
        package: Path = base / relative / "__init__.py"
        native = any(package.with_suffix(suffix).is_file() for suffix in EXTENSION_SUFFIXES)
        if not package.is_file():
            module_source: Path = Path(base, relative).with_suffix(".py")
            native |= any(
                Path(base, relative).with_suffix(suffix).is_file() for suffix in EXTENSION_SUFFIXES
            )
            native |= any(package.with_suffix(suffix).is_file() for suffix in BYTECODE_SUFFIXES)
            if not module_source.is_file():
                native |= any(
                    module_source.with_suffix(suffix).is_file() for suffix in BYTECODE_SUFFIXES
                )
        if native:
            return None
        candidate: Path = package if package.is_file() else Path(base, relative).with_suffix(".py")
        if candidate.is_file() and candidate.resolve().is_relative_to(base):
            resolved: Path = candidate.resolve()
            if (
                parent is None
                or parent.name == "__init__.py"
                and resolved.is_relative_to(parent.parent)
            ):
                candidates.add(resolved)
    return next(iter(candidates)) if len(candidates) == 1 else None


def _provider_source_names(facts: SourceFacts) -> tuple[set[str], set[str]]:
    """Keep demanded import names separate from digested discovery sources."""
    imports: set[str] = set()
    discovered_modules: set[str] = set()
    for item in facts.inputs:
        if item.path.startswith(".archkeel-providers/"):
            provider_path = PurePosixPath(item.path).relative_to(".archkeel-providers")
            provider_parts = (
                provider_path.parts[:-1]
                if provider_path.name == "__init__.py"
                else (*provider_path.parts[:-1], provider_path.stem)
            )
            imports.add(".".join(provider_parts))
            discovered_modules.add(".".join(provider_parts))
    for binding in facts.provider_bindings:
        if binding.target is not None:
            imports.update((binding.target, binding.target.rpartition(".")[0]))
    for section in facts.sections:
        if section.name is not SourceSectionName.IMPORTS:
            continue
        for record in section.records:
            target, symbol = record.data.get("target_module"), record.data.get("symbol")
            if isinstance(target, str) and target:
                imports.add(target)
                if isinstance(symbol, str) and symbol.isidentifier():
                    imports.add(f"{target}.{symbol}")
    return imports, discovered_modules


def provider_sources(
    request: CollectionRequest, facts: SourceFacts
) -> tuple[PythonProviderSource, ...]:
    """Read direct import sources, submodule candidates, and their package initializers."""
    root = Path(request.snapshot.root).resolve()
    imports, discovered_modules = _provider_source_names(facts)
    paths = sysconfig.get_paths()
    # Overlay environments retain their base dependencies on the active import path.
    search_roots = tuple(
        sorted(
            {
                Path(entry).resolve()
                for entry in (
                    *(paths[key] for key in ("stdlib", "platstdlib", "purelib", "platlib")),
                    *sys.path,
                )
                if entry
            }
        )
    )
    sources: dict[str, PythonProviderSource] = {}
    origins: dict[str, Path] = {}
    for import_name in sorted(imports):
        imported: str = import_name
        if imported == request.scope.namespace or imported.startswith(
            request.scope.namespace + "."
        ):
            continue
        parts = imported.split(".")
        for end in range(1, len(parts) + 1):
            name = ".".join(parts[:end])
            if name in sources:
                continue
            if BuiltinImporter.find_spec(name) is not None or (
                FrozenImporter.find_spec(name) is not None
                and not (
                    isinstance(request.resolver, PythonSettings)
                    and request.resolver.phase is PythonCollectionPhase.PROVIDERS
                )
                and name not in discovered_modules
            ):
                continue
            relative = Path(*parts[:end])
            if any(
                Path(base, relative).with_suffix(".py").exists()
                or Path(base, relative).exists()
                or any(
                    Path(base, relative).with_suffix(suffix).is_file()
                    for suffix in (*EXTENSION_SUFFIXES, *BYTECODE_SUFFIXES)
                )
                for base in (root, *(root / source for source in request.scope.roots))
            ):
                continue
            origin = _provider_origin(
                relative, search_roots, origins.get(".".join(parts[: end - 1]))
            )
            if origin is None:
                continue
            path: Path = origin
            try:
                content = path.read_bytes()
                text = content.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            label = ".archkeel-providers/" + relative.as_posix()
            label += "/__init__.py" if path.name == "__init__.py" else ".py"
            sources[name] = PythonProviderSource(
                name, label, text, hashlib.sha256(content).hexdigest()
            )
            origins[name] = path
    return tuple(sources[name] for name in sorted(sources))


def collect(request: CollectionRequest) -> SourceFacts:
    """Collect selected Python source evidence for the requested phase."""
    root = Path(request.snapshot.root).resolve()
    selected = _selected_paths(root, request.scope.roots)
    parsed_sources = parse_sources(selected, root=root, namespace=request.scope.namespace)
    modules = parsed_sources.modules
    evidence: dict[str, RawEvidence] = {}

    imports: list[RawRecord] = collect_imports(
        modules,
        {module.module for module in modules},
        evidence,
        namespace=request.scope.namespace,
    )
    coverage = CollectionCoverage(
        tuple(path.relative_to(root).as_posix() for path in selected),
        parsed_sources.files_read,
        len(modules),
        len(modules) == len(selected),
        tuple(parse_record(record) for record in parsed_sources.failures),
    )
    if (
        isinstance(request.resolver, PythonSettings)
        and request.resolver.phase is not PythonCollectionPhase.COLLECT
    ):
        files = _file_facts(modules, evidence)
        inputs, source_digest = _inputs(root, selected)
        required, requirement_state = python_requirement(root)
        adapter, runtime = collector_provenance(
            Language.PYTHON, required=required, requirement_state=requirement_state
        )
        survey_records = {
            SourceSectionName.IMPORTS: imports,
            SourceSectionName.UNKNOWNS: parsed_sources.failures,
        }
        survey = SourceFacts(
            SourceProfile.PYTHON,
            adapter,
            runtime,
            SourceInfo(
                request.snapshot.git_head,
                request.snapshot.dirty,
                source_digest,
                tuple(f"{source}/**/*.py" for source in request.scope.roots),
            ),
            Capabilities(PYTHON_IMPORT_SURVEY_SECTIONS),
            inputs,
            files,
            _import_targets(imports, files),
            tuple(
                FactSection(name, tuple(parse_record(record) for record in survey_records[name]))
                for name in PYTHON_IMPORT_SURVEY_SECTIONS
            ),
            coverage,
            tuple(parse_evidence(evidence[key]) for key in sorted(evidence)),
        )
        if request.resolver.phase is PythonCollectionPhase.PROVIDERS:
            sources = provider_sources(request, survey)
            while True:
                survey_bindings = _provider_bindings(
                    _provider_modules(sources, modules), modules, imports, evidence, discover=True
                )
                inputs, source_digest = _inputs(root, selected, sources)
                survey = replace(
                    survey,
                    inputs=inputs,
                    source=replace(survey.source, source_digest=source_digest),
                    evidence=tuple(parse_evidence(evidence[key]) for key in sorted(evidence)),
                    provider_bindings=survey_bindings,
                )
                expanded = provider_sources(request, survey)
                if expanded == sources:
                    break
                sources = expanded
        return survey
    captured_sources = (
        request.resolver.provider_sources if isinstance(request.resolver, PythonSettings) else ()
    )
    uncertain, unsafe_creation_providers = resolve_reexports(
        imports,
        {module.module: module.all_exports for module in modules},
        modules,
    )
    providers = _provider_modules(captured_sources, modules)
    provider_bindings = _provider_bindings(providers, modules, imports, evidence)
    required, requirement_state = python_requirement(root)
    adapter, runtime = collector_provenance(
        Language.PYTHON, required=required, requirement_state=requirement_state
    )
    symbols, symbol_nodes, symbol_owners = collect_symbols(
        modules,
        evidence,
        unsafe_creation_providers=unsafe_creation_providers,
        unsafe_source_header_providers=explicit_factory_unsafe_providers(imports, modules),
    )
    if request.protocol_version in {ProtocolVersion.V4, ProtocolVersion.V5}:
        contextmanager_signatures(modules, providers, symbols, provider_bindings, evidence)
    type_shapes = collect_type_shapes(symbol_type_expressions(symbols))
    symbol_index = build_symbol_index(symbols)
    calls, call_resolvers = collect_calls_with_resolvers(
        modules, symbol_index, evidence, provider_bindings, runtime
    )
    dynamic_imports, dynamic_limits = collect_dynamic_imports(
        modules, calls, imports, evidence, namespace=request.scope.namespace
    )
    imports.extend(dynamic_imports)
    references = collect_references(modules, symbol_index, evidence)
    bindings = collect_bindings(modules, evidence)
    typing_signals = collect_typing_signals(modules, calls, symbols, imports, evidence)
    constructs = collect_constructs(
        modules,
        evidence,
        imports=imports,
        symbol_index=symbol_index,
        receiver_resolvers=call_resolvers,
    )
    typed_symbols = tuple(parse_record(symbol) for symbol in symbols)
    state, state_evidence = collect_state(modules, typed_symbols, symbol_nodes, symbol_owners)
    source_unknowns, private_evidence = collect_private_attributes(modules)
    candidate_by_id = {item.id: item for item in state_evidence}

    files = _file_facts(modules, evidence)
    inputs, source_digest = _inputs(root, selected, captured_sources)
    import_targets = _import_targets(imports, files)
    records: dict[SourceSectionName, list[RawRecord]] = {
        SourceSectionName.SYMBOLS: symbols,
        SourceSectionName.IMPORTS: imports,
        SourceSectionName.CALLS: calls,
        SourceSectionName.REFERENCES: references,
        SourceSectionName.BINDINGS: bindings,
        SourceSectionName.TYPING_SIGNALS: typing_signals,
        SourceSectionName.CONSTRUCTS: constructs,
        SourceSectionName.UNKNOWNS: [
            *parsed_sources.failures,
            *dynamic_limits,
            *(raw_record(record) for record in source_unknowns),
        ],
    }
    for item in private_evidence:
        evidence[item.id] = _raw_evidence(item)

    return SourceFacts(
        SourceProfile.PYTHON,
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
            resolution_features=(
                CALL_BINDINGS_FEATURE,
                EXTENDED_CALL_BINDINGS_FEATURE,
                CALL_ARGUMENTS_FEATURE,
            ),
            constructs=tuple(
                ConstructCapability(kind, ConstructSupport.DECIDED)
                for kind in ForbiddenConstructKind
            ),
        ),
        inputs,
        files,
        import_targets,
        tuple(
            FactSection(
                name,
                typed_symbols
                if name is SourceSectionName.SYMBOLS
                else tuple(parse_record(record) for record in records[name]),
            )
            for name in _SECTION_NAMES
        ),
        coverage,
        tuple(parse_evidence(evidence[key]) for key in sorted(evidence)),
        tuple((binding, tuple(sorted(origins))) for binding, origins in sorted(uncertain.items())),
        tuple(sorted(type_shapes.items())),
        state,
        tuple(sorted(candidate_by_id.values(), key=lambda item: item.id)),
        provider_bindings,
    )


def _file_facts(
    modules: list[ParsedModule], evidence: dict[str, RawEvidence]
) -> tuple[FileFact, ...]:
    return tuple(
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


def _raw_evidence(item: Evidence) -> RawEvidence:
    return {
        "id": item.id,
        "file": item.file,
        "line": item.line,
        "end_line": item.end_line,
        "column": item.column,
        "excerpt": item.excerpt,
    }


def _inputs(
    root: Path,
    selected: tuple[Path, ...],
    providers: tuple[PythonProviderSource, ...] = (),
) -> tuple[tuple[ResolutionInput, ...], str]:
    paths: dict[str, tuple[Path, ResolutionRole]] = {
        path.relative_to(root).as_posix(): (path, ResolutionRole.SELECTED) for path in selected
    }
    config = root / "pyproject.toml"
    if config.is_file() and config.resolve().is_relative_to(root):
        paths["pyproject.toml"] = (config, ResolutionRole.RESOLUTION)
    if set(paths) & {item.path for item in providers}:
        raise ValueError("provider source collides with selected snapshot")
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
    for provider in sorted(providers, key=lambda item: item.path):
        provider_path: str = provider.path
        provider_source: str = provider.source
        inputs.append(ResolutionInput(provider_path, provider.digest, ResolutionRole.RESOLUTION))
        source.update(
            provider_path.encode("utf-8") + b"\0" + provider_source.encode("utf-8") + b"\0"
        )
    return tuple(sorted(inputs, key=lambda item: item.path)), source.hexdigest()


def _provider_modules(
    sources: tuple[PythonProviderSource, ...], selected: list[ParsedModule]
) -> list[ParsedModule]:
    governed = {module.module for module in selected}
    providers: list[ParsedModule] = []
    for source in sources:
        if source.module in governed:
            raise ValueError("provider source duplicates a governed module")
        source_text: str = source.source
        try:
            tree = ast.parse(source_text, filename=source.path)
        except (SyntaxError, ValueError):
            continue
        providers.append(
            ParsedModule(
                Path(source.path),
                source.path,
                source.module,
                package_for(source.module),
                source_text,
                source_text.encode("utf-8"),
                re.split(r"\r\n?|\n", source_text),
                tree,
            )
        )
    return [module for module in providers if _provider_source_eligible(module)]


def _provider_bindings(
    providers: list[ParsedModule],
    selected: list[ParsedModule],
    imports: list[RawRecord],
    evidence: dict[str, RawEvidence],
    *,
    discover: bool = False,
) -> tuple[ProviderBinding, ...]:
    """Bind direct provider declarations to their captured source evidence."""
    if not providers:
        return ()
    by_module = {module.module: module for module in providers}
    provider_imports = collect_imports(providers, set(by_module), evidence, namespace="")
    wanted = {
        f"{item['data']['target_module']}.{item['data']['symbol']}"
        for item in imports
        if item["data"]["symbol"] not in {None, "*"}
    }
    wanted.update(
        item["data"]["target_module"] for item in imports if item["data"]["symbol"] is None
    )
    imported_modules = {item["data"]["target_module"] for item in imports}
    wanted.update(
        target for target in NATIVE_CALL_TARGETS if _first_part(target, ".") in imported_modules
    )
    decorators = {
        resolve_static_name(module, node.decorator_list[0])
        for module in selected
        for node in module.all_nodes
        if isinstance(node, ast.FunctionDef)
        and len(node.decorator_list) == 1
        and not isinstance(node.decorator_list[0], ast.Call)
    }
    wanted.update(decorators)
    wanted.update(contextmanager_dependency_bindings(providers, decorators))
    direct_wanted = wanted.copy()
    bindings = _provider_aliases(wanted, by_module, provider_imports, evidence, discover=discover)
    for module in providers:
        runtime_parent = _provider_parents_static(module.module, by_module)
        stdlib_root = module.module in sys.stdlib_module_names and "." not in module.module
        if not _provider_module_is_relevant(module, runtime_parent, stdlib_root, by_module):
            continue
        if _provider_module_binding(module, runtime_parent, stdlib_root, wanted):
            evidence_id = file_evidence(evidence, module.rel_path, module.lines)
            bindings.append(ProviderBinding(module.module, ProviderBindingKind.MODULE, evidence_id))
        bindings.extend(
            _provider_member_bindings(
                module, runtime_parent, stdlib_root, wanted, direct_wanted, evidence
            )
        )
    return tuple(sorted(bindings, key=lambda item: item.qualified_name))


def _provider_module_is_relevant(
    module: ParsedModule,
    runtime_parent: bool,
    stdlib_root: bool,
    by_module: dict[str, ParsedModule],
) -> bool:
    return (
        runtime_parent
        or stdlib_root
        or _provider_parents_static(module.module, by_module, source_identity=True)
    )


def _provider_module_binding(
    module: ParsedModule,
    runtime_parent: bool,
    stdlib_root: bool,
    wanted: set[str],
) -> bool:
    return (
        (runtime_parent or stdlib_root)
        and module.module in wanted
        and _provider_identity_static(module, registry_identity=False)
    )


def _provider_member_bindings(
    module: ParsedModule,
    runtime_parent: bool,
    stdlib_root: bool,
    wanted: set[str],
    direct_wanted: set[str],
    evidence: dict[str, RawEvidence],
) -> list[ProviderBinding]:
    bindings: list[ProviderBinding] = []
    for node in module.tree.body:
        for name, kind in _provider_declarations(node):
            qualified = f"{module.module}.{name}"
            if not _provider_declaration_selected(module, name, qualified, kind, wanted):
                continue
            if not runtime_parent:
                if qualified in direct_wanted and not stdlib_root:
                    continue
                if not stdlib_root:
                    kind = ProviderBindingKind.DECLARATION
            bindings.append(ProviderBinding(qualified, kind, add_evidence(evidence, module, node)))
        if isinstance(node, ast.ClassDef):
            bindings.extend(_provider_class_member_bindings(module, node, wanted, evidence))
    return bindings


def _provider_declaration_selected(
    module: ParsedModule,
    name: str,
    qualified: str,
    kind: ProviderBindingKind,
    wanted: set[str],
) -> bool:
    return (
        module.scope_bound_names.count(name) == 1
        and name not in module.global_names
        and qualified in wanted
        and _provider_identity_static(
            module, registry_identity=kind is not ProviderBindingKind.DECLARATION
        )
    )


def _provider_class_member_bindings(
    module: ParsedModule,
    node: ast.ClassDef,
    wanted: set[str],
    evidence: dict[str, RawEvidence],
) -> list[ProviderBinding]:
    methods = {
        method.name
        for method in node.body
        if isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    bindings = _provider_class_method_bindings(module, node, wanted, evidence)
    bindings.extend(_provider_native_class_members(module, node, methods, wanted, evidence))
    return bindings


def _provider_class_method_bindings(
    module: ParsedModule,
    node: ast.ClassDef,
    wanted: set[str],
    evidence: dict[str, RawEvidence],
) -> list[ProviderBinding]:
    bindings: list[ProviderBinding] = []
    for method in node.body:
        if not isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        qualified = f"{module.module}.{node.name}.{method.name}"
        if (
            qualified in wanted
            and not method.decorator_list
            and node.name not in module.global_names
            and module.scope_bound_names.count(node.name) == 1
            and class_header_static(node)
            and _provider_identity_static(module, registry_identity=False)
        ):
            bindings.append(
                ProviderBinding(
                    qualified,
                    ProviderBindingKind.FUNCTION,
                    add_evidence(evidence, module, method),
                )
            )
    return bindings


def _provider_native_class_members(
    module: ParsedModule,
    node: ast.ClassDef,
    methods: set[str],
    wanted: set[str],
    evidence: dict[str, RawEvidence],
) -> list[ProviderBinding]:
    bindings: list[ProviderBinding] = []
    for native_target in wanted & NATIVE_CALL_TARGETS:
        prefix = f"{module.module}.{node.name}."
        member = native_target[len(prefix) :] if _starts_with(native_target, prefix) else ""
        if (
            member
            and member not in methods
            and class_header_static(node)
            and _provider_identity_static(module, registry_identity=False)
        ):
            bindings.append(
                ProviderBinding(
                    native_target,
                    ProviderBindingKind.FUNCTION,
                    add_evidence(evidence, module, node),
                )
            )
    return bindings


def _provider_aliases(
    wanted: set[str],
    by_module: dict[str, ParsedModule],
    provider_imports: list[RawRecord],
    evidence: dict[str, RawEvidence],
    *,
    discover: bool,
) -> list[ProviderBinding]:
    """Expand demanded aliases without promoting unbound terminals to declarations."""
    bindings: list[ProviderBinding] = []
    pending = sorted(wanted)
    visited: set[str] = set()
    while pending:
        qualified = pending.pop()
        if qualified in visited:
            continue
        visited.add(qualified)
        name, _, binding = qualified.rpartition(".")
        module = by_module.get(name)
        if module is None or not _provider_parents_static(name, by_module, source_identity=True):
            continue
        star = _provider_star_alias(
            module, binding, by_module, provider_imports, evidence, discover=discover
        )
        if star is not None and star.target is not None:
            bindings.append(star)
            wanted.add(star.target)
            pending.append(star.target)
            continue
        if not _provider_identity_static(module, registry_identity=False):
            continue
        matches = [
            item
            for item in provider_imports
            if item["data"]["source_module"] == name
            and item["data"]["binding"] == binding
            and item["data"]["module_level_import"] is True
            and item["data"]["under_type_checking"] is False
        ]
        if len(matches) != 1 or binding not in stable_direct_module_bindings(module):
            continue
        item = matches[0]
        data = item["data"]
        target = data["target_module"]
        if data["symbol"] is not None:
            target += "." + data["symbol"]
        if target == qualified or not all(part.isidentifier() for part in target.split(".")):
            continue
        bindings.append(
            ProviderBinding(qualified, ProviderBindingKind.ALIAS, item["evidence_ids"][0], target)
        )
        wanted.add(target)
        pending.append(target)
    return bindings


def _provider_star_alias(
    module: ParsedModule,
    binding: str,
    by_module: dict[str, ParsedModule],
    imports: list[RawRecord],
    evidence: dict[str, RawEvidence],
    *,
    discover: bool,
) -> ProviderBinding | None:
    if (
        binding in module.scope_bound_names
        or binding in module.global_names
        or not all(
            isinstance(node, ast.ImportFrom)
            or isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            for node in module.tree.body
        )
    ):
        return None
    stars = [
        item
        for item in imports
        if item["data"]["source_module"] == module.module and item["data"]["symbol"] == "*"
    ]
    if len(stars) != 1:
        return None
    [star] = stars
    target = star["data"]["target_module"]
    if not all(part.isidentifier() for part in target.split(".")):
        return None
    provider = by_module.get(target)
    support: tuple[str, ...] = ()
    if provider is None:
        if not discover:
            return None
    else:
        if (
            not provider.all_literal
            or binding not in provider.all_exports
            or "__all__" not in stable_direct_module_bindings(provider)
            or not _provider_identity_static(provider, registry_identity=False)
        ):
            return None
        support = (file_evidence(evidence, provider.rel_path, provider.lines),)
    return ProviderBinding(
        f"{module.module}.{binding}",
        ProviderBindingKind.ALIAS,
        star["evidence_ids"][0],
        f"{target}.{binding}",
        support,
    )


def _provider_declarations(node: ast.stmt) -> tuple[tuple[str, ProviderBindingKind], ...]:
    if isinstance(node, ast.ClassDef):
        if class_header_static(node) and not any(
            isinstance(item, ast.Call) for base in node.bases for item in ast.walk(base)
        ):
            return ((node.name, ProviderBindingKind.CLASS),)
    elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        kind = (
            ProviderBindingKind.DECLARATION if node.decorator_list else ProviderBindingKind.FUNCTION
        )
        return ((node.name, kind),)
    elif isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
        targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
        if all(isinstance(target, ast.Name) for target in targets):
            return tuple(
                (target.id, ProviderBindingKind.DECLARATION)
                for target in targets
                if isinstance(target, ast.Name)
            )
    return ()


def _provider_identity_nodes(module: ParsedModule) -> tuple[ast.AST, ...]:
    """Source identity does not require purity of deferred callable bodies."""
    deferred = {
        child
        for node in module.all_nodes
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda)
        for body in ((node.body,) if isinstance(node, ast.Lambda) else node.body)
        for child in ast.walk(body)
    }
    return tuple(node for node in module.all_nodes if node not in deferred)


def _provider_identity_static(module: ParsedModule, *, registry_identity: bool = True) -> bool:
    nodes = _provider_identity_nodes(module)
    system_names = member_binding_closure(
        nodes,
        {name for name, binding in module.aliases.items() if binding.target == "sys"},
        member_surface=False,
    )
    return (
        module.binding_names is not None
        and "__getattr__" not in module.scope_bound_names
        and "__path__" not in module.global_names
        and not any(
            exposes_dynamic_namespace(module, node)
            or isinstance(node, ast.Name)
            and node.id == "__path__"
            or registry_identity
            and isinstance(node, ast.Name | ast.Attribute)
            and resolve_static_name(module, node) == "sys.modules"
            or registry_identity
            and isinstance(node, ast.Attribute)
            and node.attr == "modules"
            and isinstance(node.value, ast.Name)
            and node.value.id in system_names
            for node in nodes
        )
    )


def _provider_parents_static(
    name: str, modules: dict[str, ParsedModule], *, source_identity: bool = False
) -> bool:
    parts = name.split(".")
    for end in range(1, len(parts)):
        parent = modules.get(".".join(parts[:end]))
        if (
            parent is None
            or parent.path.name != "__init__.py"
            or not _provider_identity_static(parent, registry_identity=not source_identity)
            or parts[end] in parent.global_names
            or any(
                alias.target == parent.module and binding in unproven_member_bindings(parent)
                for binding, alias in parent.aliases.items()
            )
            or any(
                isinstance(node, ast.Name | ast.Attribute)
                and resolve_static_name(parent, node)
                in {
                    "getattr",
                    "builtins.getattr",
                    "setattr",
                    "builtins.setattr",
                    "vars",
                    "builtins.vars",
                }
                for node in _provider_identity_nodes(parent)
            )
        ):
            return False
        child = parts[end]
        if child in parent.scope_bound_names:
            imported = parent.aliases.get(child)
            if (
                child not in stable_direct_module_bindings(parent)
                or imported is None
                or imported.target != ".".join(parts[: end + 1])
            ):
                return False
    return True


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


def _first_part(value: str, separator: str) -> str:
    for index in range(len(value)):
        if value[index] == separator:
            return value[:index]
    return value


def _starts_with(value: str, prefix: str) -> bool:
    length = len(prefix)
    return len(value) >= length and value[:length] == prefix
