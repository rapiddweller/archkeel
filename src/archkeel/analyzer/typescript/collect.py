# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Collect TypeScript import facts; whatever cannot be proven is an UNKNOWN gap, never a PASS."""

from __future__ import annotations

import hashlib
import json
import posixpath
from collections.abc import Sequence
from dataclasses import replace
from enum import Enum
from typing import Final

from archkeel.analyzer.runtime import collector_provenance
from archkeel.ir.facts import (
    SOURCE_RESOLUTION_GAP_KIND,
    SOURCE_SCRIPT_GLOBAL_KIND,
    BuiltinTarget,
    Capabilities,
    CollectionCoverage,
    ConstructCapability,
    ConstructSupport,
    EvidenceClass,
    ExternalPackageTarget,
    FactSection,
    FileFact,
    ForbiddenConstructKind,
    ImportTarget,
    Language,
    LocalTarget,
    Record,
    ResolutionInput,
    SourceFacts,
    SourceInfo,
    SourceProfile,
    SourceResolution,
    SourceSectionName,
    UnresolvedTarget,
    stable_id,
)
from archkeel.ir.facts_codec import (
    RawEvidence,
    RawRecord,
    classified,
    file_evidence,
    parse_evidence,
    parse_record,
    record_evidence,
)
from archkeel.ir.identity import module_identity
from archkeel.ir.protocol import CollectionRequest, TypeScriptSettings

from .config import (
    ModuleKind,
    ModuleResolution,
    Snapshot,
    join,
    load_config,
    standard_globals,
    within,
)
from .parse import parse, umd_publication
from .resolve import Found, Resolver, Unknown
from .source_input import (
    ModuleFormat,
    PathToken,
    SourceKind,
    SpecifierKind,
    classify_asset,
    classify_file,
    classify_specifier,
)
from .syntax import (
    Base,
    Definition,
    DefinitionKind,
    Member,
    ReceiverKind,
    Reference,
    ReferenceForm,
    ScriptAlias,
    ScriptGlobal,
    ScriptRoot,
    Site,
    SiteKind,
    SiteUse,
    Span,
    Syntax,
    Visibility,
)


class _InventoryStatus(Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class _GapKind(Enum):
    COLLECTION = "collection_gap"
    RESOLUTION = SOURCE_RESOLUTION_GAP_KIND


class _GapDimension(Enum):
    IMPORTS = "imports"
    RUNTIME_EFFECTS = "runtime_effects"


class _ScriptHostName(Enum):
    EXPORTS = "exports"
    MODULE = "module"
    DEFINE = "define"
    WINDOW = "window"
    GLOBAL = "global"
    SELF = "self"


_SECTIONS: tuple[SourceSectionName, ...] = (
    SourceSectionName.IMPORTS,
    SourceSectionName.UNKNOWNS,
    SourceSectionName.SYMBOLS,
    SourceSectionName.CALLS,
    SourceSectionName.REFERENCES,
    SourceSectionName.BINDINGS,
    SourceSectionName.CONSTRUCTS,
)
# What the compiler's `trim()` removes, which Python's `strip()` does not match exactly.
_WHITESPACE: Final = " \t\n\v\f\r                 　﻿"
# The reserved identity of an asset edge; a colon cannot occur in an npm package name.
BUNDLER_ASSET: Final = "bundler:asset"
_BUNDLER_FEATURE: Final = "bundler-mode-v1"
_FEATURES: Final = (
    "literal-imports",
    "relative-specifiers",
    "node-builtins",
    "local-runtime-closure",
    "inner-uml-v1",
)
_SCRIPT_ROOTS: Final = frozenset(item.value for item in ScriptRoot)
_SCRIPT_HOST_NAMES: Final = frozenset(item.value for item in _ScriptHostName)
_SCRIPT_LOADER_NAMES: Final = frozenset(
    item.value for item in (_ScriptHostName.EXPORTS, _ScriptHostName.MODULE, _ScriptHostName.DEFINE)
)


def _package_of(module: str) -> str:
    return module.rpartition(".")[0]


def _script_stable_publication(
    name: str,
    publishers: list[tuple[str, ScriptGlobal]],
    writes: Sequence[tuple[str, str | None, Span]],
) -> bool:
    return (
        len(publishers) == 1
        and publishers[0][1].stable
        and [
            (writer_rel, span)
            for writer_rel, written, span in writes
            if written is None or written == name
        ]
        == [(publishers[0][0], publishers[0][1].span)]
    )


def _script_source_origin(
    name: str,
    publishers: list[tuple[str, ScriptGlobal]],
    writes: Sequence[tuple[str, str | None, Span]],
) -> bool:
    return (
        len(publishers) == 1
        and (publishers[0][1].stable or publishers[0][1].source_origin)
        and [(rel, span) for rel, written, span in writes if written is None or written == name]
        == [(publishers[0][0], publishers[0][1].span)]
    )


def _script_site_aliases(
    syntax: Syntax, site: Site
) -> tuple[ScriptAlias | None, ScriptAlias | None]:
    call = next(
        (
            alias
            for alias in syntax.script_aliases
            if (site.kind is SiteKind.CALL or alias.factory)
            and len(site.path) == 2
            and site.path[0] == alias.name
            and site.span in (*alias.calls, *alias.reads)
        ),
        None,
    )
    initializer = next(
        (
            alias
            for alias in syntax.script_aliases
            if alias.reference_span == site.span
            and (site.kind is SiteKind.REFERENCE or alias.factory)
        ),
        None,
    )
    return call, initializer


def collect(request: CollectionRequest) -> SourceFacts:
    if not isinstance(request.resolver, TypeScriptSettings):
        raise ValueError("TypeScript collector requires the TypeScript resolver")
    return _Collection(request, request.resolver).facts()


class _Collection:
    def __init__(self, request: CollectionRequest, settings: TypeScriptSettings) -> None:
        self.request = request
        self.namespace = request.scope.namespace
        self.roots = tuple(join(".", root) for root in request.scope.roots)
        self.snapshot = Snapshot(request.snapshot.root)
        self.config = load_config(self.snapshot, settings.tsconfig, self.roots)
        self.resolver = Resolver(self.snapshot, self.config)
        self.requested_bundler = settings.bundler
        self.bundler = (
            settings.bundler
            and self.resolver.blocked is None
            and self.config.options.resolution is ModuleResolution.BUNDLER
        )
        # Every file to read, in discovery order; an entry added while walking is walked too.
        self.queue: list[str] = list(self.config.files)
        self.evidence: dict[str, RawEvidence] = {}
        self.imports: list[RawRecord] = []
        self.gaps: dict[str, RawRecord] = {}
        self.targets: list[ImportTarget] = []
        self.files: list[FileFact] = []
        self.syntax: dict[str, Syntax] = {}
        self.modules: dict[str, str] = {}
        self.import_targets: dict[str, ImportTarget] = {}
        self.import_sites: dict[str, tuple[str, int, int]] = {}
        self.import_binding_facts: dict[str, RawRecord] = {}
        self.read = 0
        self.script_resolution: dict[tuple[str, Site], tuple[str, ...]] = {}
        self.script_evidence: dict[tuple[str, Site], tuple[str, ...]] = {}
        self.script_fact_ids: dict[tuple[str, Site], tuple[str, ...]] = {}
        self.script_publications: dict[str, RawRecord] = {}
        self.script_effects: list[RawRecord] = []
        self.script_pending_effects: list[tuple[str, Span]] = []
        self.script_source_writes: tuple[tuple[str, str | None, Span], ...] = ()
        self.script_vendors: dict[str, list[str]] = {}
        self.script_vendors_complete = False
        self.script_vendor_writes: set[str] = set()
        self.script_vendor_writes_unbounded = False

    def facts(self) -> SourceFacts:
        index = 0
        if self.requested_bundler and not self.bundler and self.resolver.blocked is None:
            self._gap("Bundler mode requires moduleResolution bundler", kind=_GapKind.RESOLUTION)
        while index < len(self.queue):
            self._file(self.queue[index])
            index += 1
        self._named_imports()
        self._script_dependencies()
        symbols, calls, references, bindings = self._inner_facts()
        for rel, span in dict.fromkeys(self.script_pending_effects):
            self._script_runtime_effect(rel, span)
        references += self.script_effects
        for problem in sorted(self.snapshot.problems):
            self._gap(problem)
        inputs = tuple(
            ResolutionInput(path, digest, role)
            for path, (digest, role) in sorted(self.snapshot.inputs.items())
        )
        unknowns = tuple(parse_record(item) for _, item in sorted(self.gaps.items()))
        imports = tuple(
            parse_record(item) for item in sorted(self.imports, key=lambda item: item["id"])
        )
        adapter, runtime = collector_provenance(Language.TYPESCRIPT)
        listing: str = json.dumps(
            [{"path": item.path, "digest": item.digest, "role": item.role} for item in inputs],
            separators=(",", ":"),
            ensure_ascii=False,
        )
        records: dict[SourceSectionName, tuple[Record, ...]] = {
            SourceSectionName.IMPORTS: imports,
            SourceSectionName.UNKNOWNS: unknowns,
            SourceSectionName.SYMBOLS: tuple(parse_record(item) for item in symbols),
            SourceSectionName.CALLS: tuple(parse_record(item) for item in calls),
            SourceSectionName.REFERENCES: tuple(parse_record(item) for item in references),
            SourceSectionName.BINDINGS: tuple(parse_record(item) for item in bindings),
            SourceSectionName.CONSTRUCTS: self._constructs(),
        }
        return SourceFacts(
            SourceProfile.TYPESCRIPT,
            adapter,
            runtime,
            SourceInfo(
                self.request.snapshot.git_head,
                self.request.snapshot.dirty,
                hashlib.sha256(listing.encode("utf-8")).hexdigest(),
                tuple(f"{root}/**" if self.snapshot.is_dir(root) else root for root in self.roots),
            ),
            Capabilities(
                _SECTIONS,
                _FEATURES
                + (
                    ("script-globals-v1",)
                    if self.import_binding_facts
                    or any(self._global_dependency_scope(rel) for rel in self.syntax)
                    else ()
                )
                + ((_BUNDLER_FEATURE,) if self.bundler else ()),
                (
                    ConstructCapability(
                        ForbiddenConstructKind.STRING_LITERAL_COMPARE, ConstructSupport.PARTIAL
                    ),
                ),
            ),
            inputs,
            tuple(sorted(self.files, key=lambda item: item.rel_path)),
            tuple(self.targets),
            tuple(FactSection(name, records[name]) for name in _SECTIONS),
            CollectionCoverage(
                tuple(sorted(self.queue)),
                self.read,
                len(self.files),
                not unknowns,
                unknowns,
            ),
            tuple(parse_evidence(item) for _, item in sorted(self.evidence.items())),
        )

    def _named_imports(self) -> None:
        imports: list[RawRecord] = []
        targets: dict[str, list[ImportTarget]] = {}
        for item in self.imports:
            identity = item["id"]
            rel, line, column = self.import_sites[identity]
            syntax = self.syntax[rel]
            bindings = [
                binding
                for binding in syntax.import_bindings
                if (binding.span.line, binding.span.column) == (line, column)
            ]
            target = self.import_targets[identity]
            if not bindings:
                imports.append(item)
                continue
            destination = self.syntax.get(target.file) if isinstance(target, LocalTarget) else None
            targets[identity] = []
            for ordinal, binding in enumerate(bindings):
                matches = (
                    [
                        (declaration, exported)
                        for name, declaration, exported in destination.module_exports
                        if name == binding.imported
                    ]
                    if destination is not None
                    else []
                )
                known = bool(
                    binding.source_unique
                    and not binding.namespace
                    and not binding.type_only
                    and syntax.first_error is None
                    and not self.config.partial
                    and isinstance(target, LocalTarget)
                    and target.runtime_file is not None
                    and destination is not None
                    and destination.first_error is None
                    and len(matches) == 1
                )
                bound_id = stable_id("IMP_BINDING", identity, ordinal)
                witnesses: list[str] = []
                if known and isinstance(target, LocalTarget):
                    witness = self._export_binding(target, binding.imported, matches[0])
                    witnesses.append(witness)
                imports.append(
                    {
                        **item,
                        "id": bound_id,
                        "fact_ids": witnesses,
                        "data": {
                            **item["data"],
                            "symbol": None if binding.namespace else binding.imported,
                            "binding": binding.local,
                            "symbols_known": known,
                            "reexport_chain": [f"{target.module}.{binding.imported}"]
                            if known and isinstance(target, LocalTarget)
                            else [],
                            "type_only": binding.type_only,
                            "under_type_checking": binding.type_only,
                        },
                    }
                )
                targets[identity].append(replace(target, import_id=bound_id))
        self.imports = imports
        self.targets = [
            expanded
            for target in self.targets
            for expanded in targets.get(target.import_id, [target])
        ]

    def _export_binding(self, target: LocalTarget, name: str, spans: tuple[Span, Span]) -> str:
        witness = stable_id("ESM_EXPORT", target.module, name)
        self.import_binding_facts[witness] = classified(
            item_id=witness,
            evidence_class=EvidenceClass.FACT,
            area="source",
            kind="bindings",
            title="Exported source binding",
            subjects=[target.module],
            evidence_ids=list(dict.fromkeys(self._cite(target.file, span) for span in spans)),
            data={
                "module": target.module,
                "source_module": target.module,
                "source_scope": target.module,
                "name": name,
            },
        )
        return witness

    def _global_dependency_scope(self, rel: str) -> bool:
        suffix = classify_file(rel)
        form = self.resolver.format_of(rel)
        return bool(
            suffix is not None
            and suffix.source_kind is not SourceKind.DECLARATION
            and suffix.format_hint is not ModuleFormat.CJS
            and form is not ModuleFormat.CJS
            and not isinstance(form, Unknown)
        )

    def _script_dependencies(self) -> None:
        self._script_vendor_publications()
        publications: dict[str, list[tuple[str, ScriptGlobal]]] = {}
        for rel, syntax in self.syntax.items():
            for publication in syntax.script_globals:
                publications.setdefault(publication.name, []).append((rel, publication))
        writes = self._script_global_writes(publications)
        source_writes = {
            (rel, name, span)
            for rel, syntax in self.syntax.items()
            for name, span in syntax.script_source_writes
        }
        self.script_source_writes = tuple(source_writes)
        self._script_unbounded_effects(publications, writes)
        loader_sites = {
            (rel, reference.span.line, reference.span.column)
            for rel, syntax in self.syntax.items()
            for reference in syntax.references
            if reference.form is ReferenceForm.REQUIRE
        } & set(self.import_sites.values())
        for rel, syntax in self.syntax.items():
            if not self._global_dependency_scope(rel):
                continue
            for site in syntax.sites:
                if (
                    site.kind is SiteKind.CALL
                    and (rel, site.span.line, site.span.column) in loader_sites
                ):
                    continue
                destructures = [
                    item for item in syntax.script_destructures if item.span == site.span
                ]
                if destructures:
                    for item in destructures:
                        for published, _, span in item.members:
                            path = (*item.path[1:], published)
                            self._script_dependency(
                                rel,
                                replace(site, span=span, path=path),
                                path,
                                None,
                                None,
                                publications.get(path[0], []),
                                writes,
                            )
                    continue
                alias_call, alias_initializer = _script_site_aliases(syntax, site)
                alias = alias_call or alias_initializer
                path = (
                    (*alias_call.path, *(() if alias_call.factory else site.path[1:]))
                    if alias_call is not None
                    else site.path
                )
                if self._script_root_escape(rel, site, path):
                    continue
                if path and path[0] in _SCRIPT_ROOTS:
                    path = path[1:]
                if (
                    alias_initializer is not None
                    and not alias_initializer.factory
                    and self._script_alias_decomposition(
                        rel,
                        site,
                        alias_initializer,
                        path,
                        publications.get(path[0], []),
                        source_writes,
                    )
                ):
                    continue
                if (
                    not path
                    or not (site.script_free or alias_call is not None)
                    or alias_call is None
                    and site.path[0] in site.shadowed_names
                ):
                    continue
                self._script_dependency(
                    rel, site, path, alias_call, alias, publications.get(path[0], []), writes
                )

    def _script_root_escape(self, rel: str, site: Site, path: tuple[str, ...]) -> bool:
        if (
            len(path) == 1
            and path[0] in _SCRIPT_ROOTS
            and site.script_free
            and (site.script_escape or site.computed or site.kind is not SiteKind.REFERENCE)
        ):
            self._gap(
                "Escaped or computed global host dependency is not statically bounded",
                (self._cite(rel, site.span),),
                self.modules[rel],
                kind=_GapKind.RESOLUTION,
            )
            return True
        return False

    def _script_unbounded_effects(
        self,
        publications: dict[str, list[tuple[str, ScriptGlobal]]],
        writes: Sequence[tuple[str, str | None, Span]],
    ) -> None:
        self.script_pending_effects.extend(
            (rel, span)
            for rel, syntax in self.syntax.items()
            for publication in syntax.script_globals
            for span in publication.availability
        )
        self.script_pending_effects.extend(
            (rel, span)
            for rel, name, span in writes
            if self.syntax[rel].script_mode
            and (name is None or name in publications)
            and (rel, name, span) not in self.script_source_writes
        )

    def _script_alias_decomposition(
        self,
        rel: str,
        site: Site,
        alias: ScriptAlias,
        path: tuple[str, ...],
        publications: list[tuple[str, ScriptGlobal]],
        writes: set[tuple[str, str | None, Span]],
    ) -> bool:
        if not alias.calls or not _script_stable_publication(path[0], publications, list(writes)):
            return False
        target_rel, publication = publications[0]
        self._script_alias_evidence(rel, site, alias, target_rel, publication, True)
        return True

    def _script_global_writes(
        self, publications: dict[str, list[tuple[str, ScriptGlobal]]]
    ) -> list[tuple[str, str | None, Span]]:
        writes = [
            (rel, name, span)
            for rel, syntax in self.syntax.items()
            for name, span in syntax.script_writes
        ]
        # An escaped object can be mutated through aliases the collector cannot track.
        for rel, syntax in self.syntax.items():
            for site in syntax.sites:
                path = site.path[1:] if site.path and site.path[0] in _SCRIPT_ROOTS else site.path
                if (
                    site.kind is SiteKind.REFERENCE
                    and site.script_escape
                    and len(path) == 1
                    and path[0] in publications
                    and not any(
                        alias.reference_span == site.span for alias in syntax.script_aliases
                    )
                ):
                    writes.append((rel, path[0], site.span))
        return writes

    def _script_dependency(
        self,
        rel: str,
        site: Site,
        path: tuple[str, ...],
        alias_call: ScriptAlias | None,
        alias: ScriptAlias | None,
        publishers: list[tuple[str, ScriptGlobal]],
        writes: list[tuple[str, str | None, Span]],
    ) -> None:
        module = self.modules[rel]
        evidence = self._cite(rel, site.span)
        stable = _script_stable_publication(path[0], publishers, writes)
        if self._script_external_dependency(rel, site, path, alias_call, publishers):
            return
        if self._script_namespace_dependency(rel, site, path, alias_call, publishers):
            return
        declared = _script_stable_publication(path[0], publishers, self.script_source_writes)
        if alias is not None and alias.factory and not alias.complete:
            self._gap(
                "Factory result uses are not statically bounded",
                (evidence,),
                module,
                kind=_GapKind.RESOLUTION,
            )
        target_rel = publishers[0][0] if publishers else ""
        publication = publishers[0][1] if publishers else None
        target_module = self.modules[target_rel] if target_rel else path[0]
        member = path[1] if len(path) == 2 else None
        members = (
            [
                (local, span)
                for published, local, span in publication.source_members
                if published == member and local not in self.syntax[target_rel].rebound_names
            ]
            if declared and publication is not None
            else []
        )
        known = len(members) == 1 and len(path) == 2
        factory = alias_call is not None and alias_call.factory
        proof = None
        if factory:
            proof = (
                self._script_factory_proof(alias_call, target_rel, members[0][0], site)
                if known
                else None
            )
            known = proof is not None
        evidence_ids = (
            list(self._script_alias_evidence(rel, site, alias, target_rel, publication, declared))
            if alias is not None
            else [evidence]
        )
        if proof is not None:
            proof_ids = tuple(
                self._script_factory_source(source_rel, span) for source_rel, span in proof[0]
            )
            self.script_fact_ids[(module, site)] = tuple(
                dict.fromkeys((*self.script_fact_ids.get((module, site), ()), *proof_ids))
            )
        if (
            known
            and stable
            and not factory
            and not site.scope_ambiguous
            and publication is not None
            and any(local == members[0][0] for _, local, _ in publication.members)
        ):
            self.script_resolution[(module, site)] = (f"{target_module}.{members[0][0]}",)
        target_module = self._script_source_target(rel, site, path, publishers, known)
        self._script_import_record(
            rel,
            site,
            path,
            target_module,
            members[0][0] if known else member,
            known,
            evidence_ids,
            alias_call,
        )

    def _script_source_target(
        self,
        rel: str,
        site: Site,
        path: tuple[str, ...],
        publishers: list[tuple[str, ScriptGlobal]],
        known: bool,
    ) -> str:
        module = self.modules[rel]
        identity = stable_id("TSGLOBAL", module, site.span.line, site.span.column, site.kind.value)
        evidence = self._cite(rel, site.span)
        target_rel = (
            publishers[0][0]
            if _script_source_origin(path[0], publishers, self.script_source_writes)
            else ""
        )
        if target_rel:
            target = self.modules[target_rel]
            proof = self._script_publication_evidence(target_rel, publishers[0][1])
            self.script_fact_ids[(module, site)] = tuple(
                dict.fromkeys((*self.script_fact_ids.get((module, site), ()), proof))
            )
            self.targets.append(LocalTarget(identity, target, target_rel, None, None))
            if len(path) > 1 and not known:
                self._gap(
                    f"Script global member {path[0]}.{path[1]} is not statically published",
                    (evidence,),
                    module,
                    kind=_GapKind.RESOLUTION,
                )
            return target
        reason = f"Script global {path[0]} has no unique unconditional publication"
        self.targets.append(UnresolvedTarget(identity, path[0], reason))
        self._gap(reason, (evidence,), module, kind=_GapKind.RESOLUTION)
        return path[0]

    def _script_declaration_fact(self, rel: str, span: Span, name: str) -> str:
        module = self.modules[rel]
        identity = stable_id("SCRIPTDECLARATION", module, span.line, span.column, name)
        self.script_publications[identity] = classified(
            item_id=identity,
            evidence_class=EvidenceClass.FACT,
            area="source",
            kind="bindings",
            title=f"{module} declares script global {name}",
            subjects=[module],
            evidence_ids=[self._cite(rel, span)],
            data={
                "source_module": module,
                "source_scope": module,
                "module": module,
                "binding": name,
                "script_global": name,
            },
        )
        return identity

    def _script_factory_source(self, rel: str, span: Span) -> str:
        module = self.modules[rel]
        identity = stable_id("SCRIPT_FACTORY_SOURCE", module, span.line, span.column)
        self.script_publications[identity] = classified(
            item_id=identity,
            evidence_class=EvidenceClass.FACT,
            area="source",
            kind="bindings",
            title="Factory source declaration",
            subjects=[module],
            evidence_ids=[self._cite(rel, span)],
            data={"module": module, "source_module": module, "source_scope": module},
        )
        return identity

    def _script_global_stable(self, name: str, publishers: list[tuple[str, ScriptGlobal]]) -> bool:
        return (
            not publishers
            and self.script_vendors_complete
            and not self.script_vendor_writes_unbounded
            and name not in self.script_vendor_writes
            and name not in self.script_vendors
            and not self.config.partial
            and all(syntax.first_error is None for syntax in self.syntax.values())
            and not any(
                not path or path == (name,)
                for syntax in self.syntax.values()
                for path in syntax.script_write_paths
            )
        )

    def _script_standard_global(
        self, name: str, publishers: list[tuple[str, ScriptGlobal]]
    ) -> bool:
        return (
            name in standard_globals(self.config.options)
            and self._script_global_stable(name, publishers)
            and not any(name in syntax.script_bindings for syntax in self.syntax.values())
        )

    def _script_declared_global(
        self, name: str, publishers: list[tuple[str, ScriptGlobal]]
    ) -> tuple[str, Span] | None:
        """The first project `declare` of `name`, when nothing else binds or writes the name."""
        declarations = [
            (rel, span)
            for rel, syntax in sorted(self.syntax.items())
            for declared, span in syntax.ambient_globals
            if declared == name
        ]
        # A `declare const` is also a binding of its own file; any other file binding it blocks.
        bound_elsewhere = any(
            name in syntax.script_bindings
            and name not in {declared for declared, _ in syntax.ambient_globals}
            for syntax in self.syntax.values()
        )
        if declarations and not bound_elsewhere and self._script_global_stable(name, publishers):
            return declarations[0]
        return None

    def _script_external_dependency(
        self,
        rel: str,
        site: Site,
        path: tuple[str, ...],
        alias: ScriptAlias | None,
        publishers: list[tuple[str, ScriptGlobal]],
    ) -> bool:
        module = self.modules[rel]
        identity = stable_id("TSGLOBAL", module, site.span.line, site.span.column, site.kind.value)
        facts: tuple[str, ...] = ()
        if self._script_standard_global(path[0], publishers):
            target: ImportTarget = BuiltinTarget(identity, path[0])
            package = path[0]
        elif (declared := self._script_declared_global(path[0], publishers)) is not None:
            target = BuiltinTarget(identity, path[0])
            package = path[0]
            # The declaration sits in another file, so it is a fact, not evidence of this record.
            facts = (self._script_declaration_fact(*declared, path[0]),)
        elif (vendor := self._script_vendor_package(path[0], publishers)) is not None:
            target = ExternalPackageTarget(identity, vendor)
            package = vendor
        else:
            return False
        self.targets.append(target)
        self._script_import_record(
            rel,
            site,
            path,
            package,
            None,
            False,
            [self._cite(rel, site.span)],
            alias,
            target_package=package,
            facts=facts,
        )
        return True

    def _script_vendor_publications(self) -> None:
        publications: dict[str, list[str]] = {}
        resolver: Resolver = self.resolver
        for provider in self.config.script_providers:
            resolved = resolver.script_provider(provider)
            if resolved is None:
                return
            package, content = resolved
            publication = umd_publication(provider.source, content)
            if publication is None or publication[0] in _SCRIPT_LOADER_NAMES:
                return
            publications.setdefault(publication[0], []).append(package)
            writes = publication[2]
            if writes is None:
                self.script_vendor_writes_unbounded = True
            else:
                self.script_vendor_writes.update(writes)
        self.script_vendors = publications
        self.script_vendors_complete = True

    def _script_vendor_package(
        self, name: str, publishers: list[tuple[str, ScriptGlobal]]
    ) -> str | None:
        packages = self.script_vendors.get(name, ())
        collisions = {name, *_SCRIPT_HOST_NAMES}
        if (
            publishers
            or len(packages) != 1
            or self.script_vendor_writes_unbounded
            or collisions.intersection(self.script_vendor_writes)
            or any(syntax.first_error is not None for syntax in self.syntax.values())
            or any(
                collisions.intersection(syntax.script_bindings) for syntax in self.syntax.values()
            )
            or any(
                not path
                or len(path) == 1
                and path[0] in collisions
                or path[0] in _SCRIPT_LOADER_NAMES
                for syntax in self.syntax.values()
                for path in syntax.script_write_paths
            )
        ):
            return None
        return packages[0]

    def _script_namespace_dependency(
        self,
        rel: str,
        site: Site,
        path: tuple[str, ...],
        alias: ScriptAlias | None,
        publishers: list[tuple[str, ScriptGlobal]],
    ) -> bool:
        namespaces = [
            (source_rel, item)
            for source_rel, syntax in self.syntax.items()
            for item in syntax.script_namespaces
            if item.name == path[0]
        ]
        if publishers or len(namespaces) != 1:
            return False
        source_rel, namespace = namespaces[0]
        if any(
            syntax.first_error is not None
            or () in syntax.script_write_paths
            or source_rel != candidate
            and (path[0] in syntax.script_bindings or (path[0],) in syntax.script_write_paths)
            for candidate, syntax in self.syntax.items()
        ):
            return False
        module = self.modules[rel]
        target = self.modules[source_rel]
        identity = stable_id("TSGLOBAL", module, site.span.line, site.span.column, site.kind.value)
        proof = stable_id("SCRIPT_NAMESPACE_SOURCE", target, namespace.name, namespace.span.line)
        self.script_publications[proof] = classified(
            item_id=proof,
            evidence_class=EvidenceClass.FACT,
            area="source",
            kind="bindings",
            title="Script namespace source binding",
            subjects=[target],
            evidence_ids=[
                self._cite(source_rel, namespace.span),
                self._cite(source_rel, namespace.initialization),
            ],
            data={
                "module": target,
                "source_module": target,
                "source_scope": target,
                "binding": namespace.name,
                "script_namespace": namespace.name,
            },
        )
        self.script_fact_ids[(module, site)] = (proof,)
        self.targets.append(LocalTarget(identity, target, source_rel, None, None))
        if len(path) > 1:
            self._gap(
                f"Script namespace member {path[0]}.{path[1]} is not statically published",
                (self._cite(rel, site.span),),
                module,
                kind=_GapKind.RESOLUTION,
            )
        self._script_import_record(
            rel,
            site,
            path,
            target,
            path[0] if len(path) == 1 else path[1],
            len(path) == 1,
            [self._cite(rel, site.span)],
            alias,
        )
        return True

    def _script_factory_proof(
        self,
        alias: ScriptAlias | None,
        rel: str,
        entry: str,
        site: Site,
    ) -> tuple[tuple[tuple[str, Span], ...], bool] | None:
        if alias is None or any(
            path[: len(prefix)] == prefix
            for prefix in alias.escapes
            for syntax in self.syntax.values()
            for path in syntax.script_write_paths
        ):
            return None
        proof = self._script_factory_member(rel, entry, site.path[-1], ())
        return proof if proof is not None and (site.kind is not SiteKind.CALL or proof[1]) else None

    def _script_import_record(
        self,
        rel: str,
        site: Site,
        path: tuple[str, ...],
        target_module: str,
        symbol: str | None,
        known: bool,
        evidence_ids: list[str],
        alias: ScriptAlias | None,
        *,
        target_package: str | None = None,
        facts: tuple[str, ...] = (),
    ) -> None:
        module = self.modules[rel]
        identity = stable_id("TSGLOBAL", module, site.span.line, site.span.column, site.kind.value)
        self.imports.append(
            classified(
                item_id=identity,
                evidence_class=EvidenceClass.FACT,
                area="source",
                kind=SOURCE_SCRIPT_GLOBAL_KIND,
                title=f"{module} uses script global {path[0]}",
                subjects=[module, target_module],
                evidence_ids=evidence_ids,
                fact_ids=[*self.script_fact_ids.get((module, site), ()), *facts],
                data={
                    "source_module": module,
                    "source_package": _package_of(module),
                    "target_module": target_module,
                    "target_package": (
                        target_package if target_package is not None else _package_of(target_module)
                    ),
                    "symbol": symbol,
                    "binding": alias.name if alias is not None else path[0],
                    "symbols_known": known,
                    "specifier": path[0],
                    "type_only": False,
                    "relative_level": 0,
                    "under_type_checking": False,
                    "reexport": False,
                    "module_level_import": False,
                    "script_global": path[0],
                    "script_member": path[1] if len(path) == 2 else None,
                },
            )
        )

    def _script_factory_member(
        self, rel: str, name: str, member: str, seen: tuple[tuple[str, str, str], ...]
    ) -> tuple[tuple[tuple[str, Span], ...], bool] | None:
        identity = (rel, name, member)
        if identity in seen:
            return None
        factories = [
            factory for factory in self.syntax[rel].script_factories if factory.name == name
        ]
        if len(factories) != 1:
            return None
        factory = factories[0]
        members = [item for item in factory.members if item.name == member]
        if len(members) != 1:
            return None
        item = members[0]
        evidence = ((rel, factory.span), (rel, item.span))
        if item.target is not None and item.target_span is not None:
            return (*evidence, (rel, item.target_span)), item.callable
        for alias in self.syntax[rel].script_aliases:
            if not alias.factory or item.forwarded_span not in alias.reads:
                continue
            path = alias.path[1:] if alias.path[0] in _SCRIPT_ROOTS else alias.path
            publications = [
                (source_rel, publication)
                for source_rel, syntax in self.syntax.items()
                for publication in syntax.script_globals
                if publication.name == path[0]
            ]
            writes = self.script_source_writes
            if len(path) != 2 or not _script_stable_publication(path[0], publications, writes):
                return None
            source_rel, publication = publications[0]
            entries = [
                local for published, local, _ in publication.source_members if published == path[1]
            ]
            sites = [site for site in self.syntax[rel].sites if site.span == item.forwarded_span]
            if len(entries) != 1 or len(sites) != 1:
                return None
            result = self._script_factory_member(
                source_rel, entries[0], sites[0].path[-1], (*seen, identity)
            )
            if result is not None:
                return (
                    *evidence,
                    (rel, alias.span),
                    (source_rel, publication.span),
                    *result[0],
                ), result[1]
        return None

    def _script_alias_evidence(
        self,
        rel: str,
        site: Site,
        alias: ScriptAlias,
        target_rel: str,
        publication: ScriptGlobal | None,
        stable: bool,
    ) -> tuple[str, ...]:
        module = self.modules[rel]
        evidence_ids = [self._cite(rel, site.span), self._cite(rel, alias.span)]
        proof_ids = [
            stable_id("SCRIPTALIAS", module, alias.span.line, alias.span.column, alias.name)
        ]
        if stable and publication is not None:
            proof_ids.append(self._script_publication_evidence(target_rel, publication))
        self.script_evidence[(module, site)] = tuple(evidence_ids)
        self.script_fact_ids[(module, site)] = tuple(proof_ids)
        return tuple(evidence_ids)

    def _script_publication_evidence(self, rel: str, publication: ScriptGlobal) -> str:
        module = self.modules[rel]
        identity = stable_id(
            "SCRIPTPUBLICATION",
            module,
            publication.span.line,
            publication.span.column,
            publication.name,
        )
        evidence = [self._cite(rel, publication.span)]
        for _, _, span in publication.source_members:
            member = self._cite(rel, span)
            if member not in evidence:
                evidence.append(member)
        self.script_publications[identity] = classified(
            item_id=identity,
            evidence_class=EvidenceClass.FACT,
            area="source",
            kind="bindings",
            title=f"{module} publishes script global {publication.name}",
            subjects=[module],
            evidence_ids=evidence,
            data={
                "source_module": module,
                "source_scope": module,
                "module": module,
                "binding": publication.name,
                "script_global": publication.name,
            },
        )
        return identity

    def _constructs(self) -> tuple[Record, ...]:
        """Publish witnessed syntax; a partial construct inventory cannot prove absence."""
        kind = ForbiddenConstructKind.STRING_LITERAL_COMPARE
        records: list[Record] = []
        for rel, syntax in self.syntax.items():
            module = self.modules[rel]
            for comparison in syntax.string_comparisons:
                owner = f"{module}.{comparison.scope}" if comparison.scope else module
                records.append(
                    parse_record(
                        classified(
                            item_id=stable_id(
                                "TSCONSTRUCT",
                                rel,
                                comparison.span.line,
                                comparison.span.column,
                                kind.value,
                            ),
                            evidence_class=EvidenceClass.FACT,
                            area="constructs",
                            kind=kind.value,
                            title=f"{owner} compares a written string literal",
                            subjects=[owner],
                            evidence_ids=[self._cite(rel, comparison.span)],
                            data={"owner": owner, "construct": kind.value},
                        )
                    )
                )
        return tuple(sorted(records, key=lambda item: item.id))

    def _inner_facts(
        self,
    ) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord], list[RawRecord]]:
        """Publish syntax facts only; unresolved dispatch remains local to each site."""
        definitions: list[tuple[str, str, Definition]] = []
        for rel, syntax in self.syntax.items():
            module = self.modules[rel]
            definitions.extend((rel, module, item) for item in syntax.definitions)
        ids: dict[tuple[str, int, int], str] = {}
        by_qualified: dict[str, list[tuple[str, Definition]]] = {}
        for rel, module, definition in definitions:
            qualified = (
                f"{module}.{definition.parent}.{definition.name}"
                if definition.parent
                else f"{module}.{definition.name}"
            )
            identity = stable_id(
                "TSDEF",
                rel,
                definition.span.line,
                definition.span.column,
                qualified,
                definition.kind.value,
            )
            ids[(rel, definition.span.line, definition.span.column)] = identity
            by_qualified.setdefault(qualified, []).append((identity, definition))
        scope_ids = {
            (
                f"{module}.{definition.parent}.{definition.name}"
                if definition.parent
                else f"{module}.{definition.name}",
                definition.span.line,
                definition.span.column,
            ): ids[(rel, definition.span.line, definition.span.column)]
            for rel, module, definition in definitions
        }

        symbols = self._inner_symbols(definitions, ids, by_qualified, scope_ids)
        calls, references, bindings = self._inner_sites(definitions, ids, by_qualified, scope_ids)
        return symbols, calls, references, bindings

    def _inner_symbols(
        self,
        definitions: list[tuple[str, str, Definition]],
        ids: dict[tuple[str, int, int], str],
        by_qualified: dict[str, list[tuple[str, Definition]]],
        scope_ids: dict[tuple[str, int, int], str],
    ) -> list[RawRecord]:
        symbols: list[RawRecord] = []
        for rel, module, definition in definitions:
            qualified = (
                f"{module}.{definition.parent}.{definition.name}"
                if definition.parent
                else f"{module}.{definition.name}"
            )
            identity = ids[(rel, definition.span.line, definition.span.column)]
            evidence = self._cite(rel, definition.span)
            parent_name = f"{module}.{definition.parent}" if definition.parent else None
            parent_id = None
            if definition.parent:
                if definition.parent_line is not None and definition.parent_column is not None:
                    parent_id = scope_ids.get(
                        (parent_name or "", definition.parent_line, definition.parent_column)
                    )
            data = self._symbol_metadata(
                rel,
                module,
                qualified,
                parent_name,
                parent_id,
                definition,
                len(by_qualified[qualified]) == 1,
            )
            if definition.kind in {DefinitionKind.FUNCTION, DefinitionKind.METHOD}:
                data["signature_decorators_proven"] = not definition.decorator_sources
            if definition.kind in {
                DefinitionKind.CLASS,
                DefinitionKind.INTERFACE,
                DefinitionKind.ENUM,
            }:
                data.update(
                    self._classifier_data(
                        rel, module, definition, qualified, definitions, ids, by_qualified
                    )
                )
            else:
                data["annotation"] = definition.annotation
                data["returns"] = definition.returns
                if definition.is_async:
                    data["async"] = True
                data["parameters"] = [
                    {
                        "name": parameter.name,
                        "annotation": parameter.annotation,
                        "kind": "varargs" if parameter.rest else "positional",
                        "default": parameter.default,
                        "default_known": parameter.default is None and not parameter.optional,
                    }
                    for parameter in definition.parameters
                ]
                if definition.kind is DefinitionKind.METHOD:
                    data["method_kind"] = "static" if definition.static else "instance"
            symbols.append(
                classified(
                    item_id=identity,
                    evidence_class=EvidenceClass.FACT,
                    area="source",
                    kind=(
                        "class"
                        if definition.kind
                        in {DefinitionKind.CLASS, DefinitionKind.INTERFACE, DefinitionKind.ENUM}
                        else definition.kind.value
                    ),
                    title=f"{qualified} declaration",
                    subjects=[qualified],
                    evidence_ids=[evidence],
                    data=data,
                )
            )

        return symbols

    def _symbol_metadata(
        self,
        rel: str,
        module: str,
        qualified: str,
        parent_name: str | None,
        parent_id: str | None,
        definition: Definition,
        binding_unique: bool,
    ) -> dict[str, object]:
        category = (
            "class"
            if definition.kind
            in {DefinitionKind.CLASS, DefinitionKind.INTERFACE, DefinitionKind.ENUM}
            else definition.kind.value
        )
        return {
            "qualified_name": qualified,
            "module": module,
            "package": _package_of(module),
            "name": definition.name,
            "parent": parent_name,
            "lexical_parent_id": parent_id,
            "visibility_detail": {
                "kind": definition.visibility.value
                if definition.visibility
                else ("unknown" if definition.top_level else "public"),
                "basis": (
                    "unknown"
                    if definition.top_level and definition.visibility is None
                    else "language"
                ),
                "spelling": definition.name,
            },
            "symbol_category": category,
            "source_binding_unique": binding_unique,
            "source_member_binding_static": True,
            "class_header_static": True,
            "decorators": [spelling for spelling, _ in definition.decorator_sources],
            "decorator_evidence_ids": [
                self._cite(rel, span) for _, span in definition.decorator_sources
            ],
            "signature_complete": definition.signature_complete,
            "overload_signature": definition.overload_signature,
        }

    def _classifier_data(
        self,
        rel: str,
        module: str,
        definition: Definition,
        qualified: str,
        definitions: list[tuple[str, str, Definition]],
        ids: dict[tuple[str, int, int], str],
        by_qualified: dict[str, list[tuple[str, Definition]]],
    ) -> dict[str, object]:
        data: dict[str, object] = {}
        if definition.kind in {DefinitionKind.INTERFACE, DefinitionKind.ENUM}:
            data["class_kind"] = (
                "protocol" if definition.kind is DefinitionKind.INTERFACE else "enum"
            )
        attribute_declarations = [
            self._attribute_declaration(rel, qualified, member) for member in definition.members
        ]
        data["attribute_declarations"] = attribute_declarations
        if definition.kind is DefinitionKind.ENUM:
            data["enum_members"] = [member.name for member in definition.members]
        methods = [
            ids[(child_rel, child.span.line, child.span.column)]
            for child_rel, child_module, child in definitions
            if child_module == module
            and child.kind is DefinitionKind.METHOD
            and child.parent == (qualified.removeprefix(f"{module}."))
            and child.parent_line == definition.span.line
            and child.parent_column == definition.span.column
        ]
        attrs = [item["definition_id"] for item in attribute_declarations]
        status = (
            _InventoryStatus.COMPLETE
            if definition.members_complete and len(by_qualified[qualified]) == 1
            else _InventoryStatus.PARTIAL
        )
        member_reason = (
            None if status is _InventoryStatus.COMPLETE else "computed or unsupported member syntax"
        )
        data["member_inventories"] = [
            {
                "schema_version": "1.0.0",
                "kind": "attribute",
                "status": status.value,
                "definition_ids": attrs,
                "reason": member_reason,
            },
            {
                "schema_version": "1.0.0",
                "kind": "method",
                "status": status.value,
                "definition_ids": methods,
                "reason": member_reason,
            },
        ]
        data["base_declarations"] = [
            self._base_record(rel, module, qualified, base, by_qualified)
            for base in definition.bases
        ]
        return data

    def _inner_sites(
        self,
        definitions: list[tuple[str, str, Definition]],
        ids: dict[tuple[str, int, int], str],
        by_qualified: dict[str, list[tuple[str, Definition]]],
        scope_ids: dict[tuple[str, int, int], str],
    ) -> tuple[list[RawRecord], list[RawRecord], list[RawRecord]]:
        calls: list[RawRecord] = []
        references: list[RawRecord] = []
        bindings = list(self.script_publications.values()) + list(
            self.import_binding_facts.values()
        )
        top_by_module: dict[str, list[tuple[str, Definition]]] = {}
        definitions_by_module: dict[str, list[Definition]] = {}
        for rel, module, definition in definitions:
            definitions_by_module.setdefault(module, []).append(definition)
            if definition.top_level:
                top_by_module.setdefault(module, []).append(
                    (ids[(rel, definition.span.line, definition.span.column)], definition)
                )
        import_by_local = self._local_import_bindings()
        for rel, syntax in self.syntax.items():
            module = self.modules[rel]
            for site in syntax.sites:
                evidence = self._cite(rel, site.span)
                scope = f"{module}.{site.scope}" if site.scope else module
                source_id = (
                    scope_ids.get((scope, site.scope_line, site.scope_column))
                    if site.scope_line is not None and site.scope_column is not None
                    else None
                )
                candidates, status, reason = self._site_resolution(
                    module,
                    syntax,
                    site,
                    scope,
                    top_by_module,
                    import_by_local,
                    definitions_by_module,
                    by_qualified,
                )
                if site.kind is SiteKind.REFERENCE:
                    reference = self._reference_record(
                        module, scope, source_id, site, candidates, status, reason, evidence
                    )
                    reference["evidence_ids"] = list(
                        self.script_evidence.get((module, site), (evidence,))
                    )
                    reference["fact_ids"] = list(self.script_fact_ids.get((module, site), ()))
                    references.append(reference)
                    bindings.extend(
                        self._script_alias_bindings(
                            module, scope, site, reference["evidence_ids"], syntax
                        )
                    )
                else:
                    call, result_bindings = self._call_record(
                        rel,
                        module,
                        scope,
                        source_id,
                        site,
                        candidates,
                        status,
                        reason,
                        evidence,
                        by_qualified,
                    )
                    call["evidence_ids"] = list(
                        self.script_evidence.get((module, site), (evidence,))
                    )
                    call["fact_ids"] = list(self.script_fact_ids.get((module, site), ()))
                    calls.append(call)
                    bindings.extend(result_bindings)
                    bindings.extend(
                        self._script_alias_bindings(
                            module, scope, site, call["evidence_ids"], syntax
                        )
                    )
        return calls, references, bindings

    def _script_alias_bindings(
        self, module: str, scope: str, site: Site, evidence_ids: list[str], syntax: Syntax
    ) -> list[RawRecord]:
        bindings: list[RawRecord] = []
        for alias in syntax.script_aliases:
            if alias.reference_span == site.span and (module, site) in self.script_fact_ids:
                alias_bindings = self._binding_records(
                    module,
                    scope,
                    [
                        {
                            "id": self.script_fact_ids[(module, site)][0],
                            "name": alias.name,
                            "evidence_ids": evidence_ids,
                        }
                    ],
                )
                for alias_binding in alias_bindings:
                    alias_binding["fact_ids"] = list(self.script_fact_ids[(module, site)][1:])
                bindings.extend(alias_bindings)
        return bindings

    def _local_import_bindings(self) -> dict[str, dict[str, list[tuple[str, str, bool, bool]]]]:
        result: dict[str, dict[str, list[tuple[str, str, bool, bool]]]] = {}
        for rel, syntax in self.syntax.items():
            module = self.modules[rel]
            for binding in syntax.import_bindings:
                edge = next(
                    (
                        key
                        for key, site in self.import_sites.items()
                        if site == (rel, binding.span.line, binding.span.column)
                    ),
                    None,
                )
                target = self.import_targets.get(edge or "")
                if isinstance(target, LocalTarget):
                    result.setdefault(module, {}).setdefault(binding.local, []).append(
                        (target.module, binding.imported, binding.namespace, binding.type_only)
                    )
        return result

    def _site_resolution(
        self,
        module: str,
        syntax: Syntax,
        site: Site,
        scope: str,
        top_by_module: dict[str, list[tuple[str, Definition]]],
        import_by_local: dict[str, dict[str, list[tuple[str, str, bool, bool]]]],
        definitions_by_module: dict[str, list[Definition]],
        by_qualified: dict[str, list[tuple[str, Definition]]],
    ) -> tuple[list[str], SourceResolution, str | None]:
        name = site.name
        candidates: list[str] = []
        reason: str | None = None
        unique_this_member = False
        script_targets = self.script_resolution.get((module, site))
        if script_targets is not None:
            candidates.extend(script_targets)
        elif (
            name
            and not site.computed
            and not site.scope_ambiguous
            and name not in site.shadowed_names
            and name not in syntax.rebound_names
        ):
            if site.receiver is None:
                candidates.extend(
                    self._unqualified_candidates(
                        module,
                        name,
                        site,
                        top_by_module,
                        import_by_local,
                        definitions_by_module,
                    )
                )
            elif site.kind is SiteKind.REFERENCE and site.receiver_kind is ReceiverKind.THIS:
                class_scope = scope.rpartition(".")[0]
                local_class = by_qualified.get(class_scope, [])
                field_definitions = [
                    definition
                    for _, definition in local_class
                    if definition.kind in {DefinitionKind.CLASS, DefinitionKind.INTERFACE}
                    and any(member.name == name for member in definition.members)
                ]
                field_count = len(field_definitions)
                if field_count:
                    candidates.append(f"{class_scope}.{name}")
                    unique_this_member = field_count == 1
                else:
                    reason = "receiver member is not declared locally"
            else:
                reason = "receiver dispatch is not proven"
        elif site.computed:
            reason = "computed expression is not statically bound"
        elif site.scope_ambiguous or (name is not None and name in site.shadowed_names):
            reason = "lexical binding may shadow the name"
        elif name is not None and name in syntax.rebound_names:
            reason = "name is rebound in module scope"
        candidates = sorted(set(candidates))
        status = (
            SourceResolution.RESOLVED
            if len(candidates) == 1
            and reason is None
            and (
                unique_this_member
                or all(len(by_qualified.get(target, [])) == 1 for target in candidates)
            )
            else SourceResolution.PARTIALLY_RESOLVED
            if candidates
            else SourceResolution.UNRESOLVED
        )
        if status is SourceResolution.PARTIALLY_RESOLVED and reason is None:
            reason = "multiple definition sites share the target name"
        if reason is None and status is not SourceResolution.RESOLVED:
            reason = "definition is missing or ambiguous"
        return candidates, status, reason

    def _unqualified_candidates(
        self,
        module: str,
        name: str,
        site: Site,
        top_by_module: dict[str, list[tuple[str, Definition]]],
        import_by_local: dict[str, dict[str, list[tuple[str, str, bool, bool]]]],
        definitions_by_module: dict[str, list[Definition]],
    ) -> list[str]:
        candidates = [
            f"{module}.{item.name}"
            for _, item in top_by_module.get(module, [])
            if item.name == name
            and (
                site.kind is SiteKind.REFERENCE
                or (site.kind is SiteKind.CALL and item.kind is DefinitionKind.FUNCTION)
                or (site.kind is SiteKind.NEW and item.kind is DefinitionKind.CLASS)
            )
        ]
        for target_module, imported, namespace, type_only in import_by_local.get(module, {}).get(
            name, []
        ):
            if namespace or (type_only and site.use is not SiteUse.TYPE):
                continue
            candidates.extend(
                f"{target_module}.{item.name}"
                for item in definitions_by_module.get(target_module, [])
                if item.name == imported
                and item.exported
                and (
                    site.kind is SiteKind.REFERENCE
                    or (site.kind is SiteKind.CALL and item.kind is DefinitionKind.FUNCTION)
                    or (site.kind is SiteKind.NEW and item.kind is DefinitionKind.CLASS)
                )
            )
        return candidates

    def _reference_record(
        self,
        module: str,
        scope: str,
        source_id: str | None,
        site: Site,
        candidates: list[str],
        status: SourceResolution,
        reason: str | None,
        evidence: str,
    ) -> RawRecord:
        data: dict[str, object] = {
            "source_scope": scope,
            "source_module": module,
            "expression": site.expression,
            "status": status.value,
            "targets": candidates,
            "candidate_count": len(candidates),
            "candidates_truncated": False,
            "use": site.use.value,
        }
        if reason:
            data["reason"] = reason
        if source_id:
            data["source_definition_id"] = source_id
        return classified(
            item_id=stable_id("TSREF", module, site.span.line, site.span.column, site.expression),
            evidence_class=EvidenceClass.FACT,
            area="source",
            kind="references",
            title=site.expression,
            subjects=[scope, *candidates],
            evidence_ids=[evidence],
            data=data,
        )

    def _call_record(
        self,
        rel: str,
        module: str,
        scope: str,
        source_id: str | None,
        site: Site,
        candidates: list[str],
        status: SourceResolution,
        reason: str | None,
        evidence: str,
        by_qualified: dict[str, list[tuple[str, Definition]]],
    ) -> tuple[RawRecord, list[RawRecord]]:
        call_id = stable_id("TSCALL", module, site.span.line, site.span.column, site.expression)
        data: dict[str, object] = {
            "source_scope": scope,
            "source_module": module,
            "expression": site.expression,
            "status": status.value,
            "targets": candidates,
            "candidate_count": len(candidates),
            "candidates_truncated": False,
        }
        if reason:
            data["reason"] = reason
        if source_id:
            data["source_definition_id"] = source_id
        binding_records: list[RawRecord] = []
        if site.kind is SiteKind.NEW:
            targets = sorted(
                target
                for target in candidates
                if any(
                    item.kind is DefinitionKind.CLASS for _, item in by_qualified.get(target, [])
                )
            )
            create_status = (
                SourceResolution.RESOLVED
                if len(targets) == 1 and status is SourceResolution.RESOLVED
                else SourceResolution.PARTIALLY_RESOLVED
                if targets
                else SourceResolution.UNRESOLVED
            )
            data["construction"] = {
                "status": create_status.value,
                "targets": targets,
                "candidates_truncated": False,
                "reason": "Unique local classifier construction"
                if create_status is SourceResolution.RESOLVED
                else reason or "Construction target is not proven",
            }
            result_bindings = self._result_binding(rel, site, call_id)
            data["result_bindings"] = result_bindings
            binding_records = self._binding_records(module, scope, result_bindings)
        call = classified(
            item_id=call_id,
            evidence_class=EvidenceClass.FACT,
            area="source",
            kind="calls",
            title=site.expression,
            subjects=[scope, *candidates],
            evidence_ids=[evidence],
            data=data,
        )
        return call, binding_records

    def _binding_records(
        self, module: str, scope: str, values: list[dict[str, object]]
    ) -> list[RawRecord]:
        result: list[RawRecord] = []
        for value in values:
            identity = value.get("id")
            name = value.get("name")
            evidence_ids = value.get("evidence_ids")
            if (
                not isinstance(identity, str)
                or not isinstance(name, str)
                or not isinstance(evidence_ids, list)
                or any(not isinstance(item, str) for item in evidence_ids)
            ):
                continue
            result.append(
                classified(
                    item_id=identity,
                    evidence_class=EvidenceClass.FACT,
                    area="source",
                    kind="bindings",
                    title=f"{scope}.{name} binding",
                    subjects=[scope],
                    evidence_ids=evidence_ids,
                    data={
                        "module": module,
                        "source_scope": scope,
                        "source_module": module,
                        "binding": name,
                    },
                )
            )
        return result

    def _result_binding(self, rel: str, site: Site, call_id: str) -> list[dict[str, object]]:
        if not site.assigned_name or site.assignment_span is None or not site.initializer:
            return []
        identity = stable_id(
            "VALUEBIND",
            call_id,
            site.assignment_span.line,
            site.assignment_span.column,
            site.assigned_name,
        )
        return [
            {
                "id": identity,
                "name": site.assigned_name,
                "target_kind": "name",
                "annotation": site.assignment_annotation,
                "initializer": site.initializer,
                "evidence_ids": [self._cite(rel, site.assignment_span)],
                "definition_contexts": [],
            }
        ]

    def _attribute_declaration(self, rel: str, qualified: str, member: Member) -> dict[str, object]:
        return {
            "name": member.name,
            "annotation": member.annotation,
            "visibility": {
                "kind": member.visibility.value if member.visibility else Visibility.PUBLIC.value,
                "basis": "language",
                "spelling": member.name,
            },
            "definition_id": stable_id(
                "TSATTR",
                rel,
                member.span.line,
                member.span.column,
                qualified,
                member.name,
            ),
            "evidence_ids": [self._cite(rel, member.span)],
            "decorators": [spelling for spelling, _ in member.decorator_sources],
            "decorator_evidence_ids": [
                self._cite(rel, span) for _, span in member.decorator_sources
            ],
            "static": member.static,
        }

    def _base_record(
        self,
        rel: str,
        module: str,
        owner: str,
        base: Base,
        by_qualified: dict[str, list[tuple[str, Definition]]],
    ) -> dict[str, object]:
        name = base.name
        qualified = f"{module}.{name}"
        classifier_targets = [
            item_id
            for item_id, definition in by_qualified.get(qualified, [])
            if definition.kind in {DefinitionKind.CLASS, DefinitionKind.INTERFACE}
        ]
        targets = [qualified] if classifier_targets else []
        evidence = self._cite(rel, base.span)
        status = (
            SourceResolution.RESOLVED
            if len(classifier_targets) == 1
            else SourceResolution.PARTIALLY_RESOLVED
            if targets
            else SourceResolution.UNRESOLVED
        )
        result: dict[str, object] = {
            "id": stable_id("TSBASE", owner, base.span.line, base.span.column, name),
            "relationship_kind": base.relationship.value,
            "status": status.value,
            "targets": targets,
            "candidate_count": len(classifier_targets),
            "candidates_truncated": False,
            "expression": name,
            "evidence_ids": [evidence],
        }
        if not targets:
            result["reason"] = "Base is not a unique local classifier"
        elif status is SourceResolution.PARTIALLY_RESOLVED:
            result["reason"] = "multiple classifier definition sites share the target name"
        return result

    def _gap(
        self,
        reason: str,
        evidence: tuple[str, ...] = (),
        module: str = "",
        *,
        kind: _GapKind = _GapKind.COLLECTION,
        dimension: _GapDimension = _GapDimension.IMPORTS,
        fact_ids: tuple[str, ...] = (),
    ) -> None:
        identity = (
            stable_id("UNKNOWN_RUNTIME_EFFECT", fact_ids[0])
            if dimension is _GapDimension.RUNTIME_EFFECTS and len(fact_ids) == 1
            else stable_id("UNKNOWN", reason, *evidence, module)
        )
        self.gaps.setdefault(
            identity,
            classified(
                item_id=identity,
                evidence_class=EvidenceClass.UNKNOWN,
                area="source",
                kind=kind.value,
                title=reason,
                subjects=[module],
                evidence_ids=list(evidence),
                fact_ids=list(fact_ids),
                data={
                    "reason": reason,
                    "module": module,
                    **(
                        {"resolution_dimension": dimension.value}
                        if kind is _GapKind.RESOLUTION
                        else {}
                    ),
                },
            ),
        )

    def _cite(self, rel: str, span: Span) -> str:
        return record_evidence(
            self.evidence, rel, (span.line, span.end_line, span.column), span.excerpt
        )

    def _selected(self, rel: str) -> bool:
        return not self.snapshot.installed(rel) and any(within(root, rel) for root in self.roots)

    def _observe(self, rel: str) -> bytes | None:
        """Read a local dependency; it joins the walk when it is a source file in scope."""
        content = self.snapshot.read(rel)
        suffix = classify_file(rel)
        if (
            content is not None
            and self._selected(rel)
            and suffix is not None
            and suffix.source_kind is not None
        ):
            if rel not in self.queue:
                self.queue.append(rel)
        elif content is not None:
            self._gap(
                f"Local dependency outside selected source scope: {rel}",
                kind=_GapKind.RESOLUTION,
            )
        return content

    def _file(self, rel: str) -> None:
        # A typed local lets the self-scan attribute these calls to the methods they reach.
        snapshot: Snapshot = self.snapshot
        content = snapshot.read(rel)
        if content is None:
            self._gap(f"Unreadable selected source: {rel}")
            return
        try:
            module: str = module_identity(self.namespace, rel)
        except ValueError:
            self._gap(f"Source path has no module identity: {rel}")
            return
        self.read += 1
        snapshot.select(rel)
        text: str = str(content, "utf-8", "replace")
        evidence = file_evidence(self.evidence, rel, (text.partition("\n")[0],))
        self.files.append(
            FileFact(
                stable_id("FILE", module),
                rel,
                module,
                _package_of(module),
                frozenset(),
                False,
                False,
                frozenset(),
                not text.strip(_WHITESPACE),
                evidence,
            )
        )
        syntax = parse(rel, text.encode("utf-8"))
        if syntax.script_mode and (
            self.resolver.format_of(rel) is not None
            or any(
                reference.form in {ReferenceForm.REQUIRE, ReferenceForm.IMPORT_EQUALS}
                for reference in syntax.references
            )
        ):
            syntax = replace(syntax, script_mode=False, script_globals=(), script_aliases=())
        self.syntax[rel] = syntax
        self.modules[rel] = module
        if syntax.first_error is not None:
            line = syntax.first_error.line
            self._gap(
                f"Syntax error in {rel}: unparseable construct at line {line}", (evidence,), module
            )
        for concern in syntax.concerns:
            self._gap(concern.reason, (self._cite(rel, concern.span),), module)
        if syntax.script_mode:
            for name, span in syntax.script_writes:
                if name is None:
                    if (name, span) in syntax.script_source_writes:
                        self._gap(
                            "Script namespace effects are not statically bounded",
                            (self._cite(rel, span),),
                            module,
                            kind=_GapKind.RESOLUTION,
                        )
                    else:
                        self.script_pending_effects.append((rel, span))
        self._references(rel, module, syntax)

    def _script_runtime_effect(self, rel: str, span: Span) -> None:
        module = self.modules[rel]
        evidence = self._cite(rel, span)
        identity = stable_id("TS_RUNTIME_EFFECT", module, span.line, span.column)
        self.script_effects.append(
            classified(
                item_id=identity,
                evidence_class=EvidenceClass.FACT,
                area="source",
                kind="script_namespace_effect",
                title="Opaque script runtime effect",
                subjects=[module],
                evidence_ids=[evidence],
                data={
                    "source_module": module,
                    "source_scope": module,
                    "expression": self.evidence[evidence]["excerpt"],
                    "status": SourceResolution.UNRESOLVED.value,
                    "targets": [],
                    "use": SiteUse.VALUE.value,
                },
            )
        )
        self._gap(
            "Script namespace effects are not statically bounded",
            (evidence,),
            module,
            kind=_GapKind.RESOLUTION,
            dimension=_GapDimension.RUNTIME_EFFECTS,
            fact_ids=(identity,),
        )

    def _references(self, rel: str, module: str, syntax: Syntax) -> None:
        options = self.config.options
        resolver: Resolver = self.resolver
        form = resolver.format_of(rel)
        suffix = classify_file(rel)
        cjs = (
            (suffix is not None and suffix.format_hint is ModuleFormat.CJS)
            or options.module is ModuleKind.COMMONJS
            or (
                form is ModuleFormat.CJS
                and options.module in (ModuleKind.NODENEXT, ModuleKind.NODE16)
            )
        )
        for reference in syntax.references:
            evidence = self._cite(rel, reference.span)
            if reference.form is ReferenceForm.REQUIRE and (not cjs or syntax.shadows_require):
                self._gap(
                    "Unproven or shadowed require call",
                    (evidence,),
                    module,
                    kind=_GapKind.RESOLUTION,
                )
            elif reference.specifier is None:
                self._gap(
                    f"Computed {reference.form.value} cannot be resolved",
                    (evidence,),
                    module,
                    kind=_GapKind.RESOLUTION,
                )
            else:
                self._import(rel, module, reference, evidence, form)

    def _import(
        self,
        rel: str,
        module: str,
        reference: Reference,
        evidence: str,
        form: ModuleFormat | Unknown | None,
    ) -> None:
        specifier: str = reference.specifier or ""
        identity = stable_id(
            "IMP", module, reference.span.line, reference.span.column, reference.form.value
        )
        target = self._target(rel, module, reference, identity, form)
        self.import_targets[identity] = target
        self.import_sites[identity] = (rel, reference.span.line, reference.span.column)
        self.targets.append(target)
        if isinstance(target, LocalTarget):
            target_module, target_package = target.module, _package_of(target.module)
        elif isinstance(target, BuiltinTarget):
            target_module = target_package = target.name
        elif isinstance(target, ExternalPackageTarget):
            target_module = target_package = target.package
        else:
            target_module = target_package = specifier
        self.imports.append(
            classified(
                item_id=identity,
                evidence_class=EvidenceClass.FACT,
                area="source",
                kind=reference.form.value,
                title=f"{module} imports {specifier}",
                subjects=[module, target_module],
                evidence_ids=[evidence],
                data={
                    "source_module": module,
                    "source_package": _package_of(module),
                    "target_module": target_module,
                    "target_package": target_package,
                    "symbol": None,
                    "binding": None,
                    "symbols_known": False,
                    "specifier": specifier,
                    "type_only": reference.type_only,
                    "relative_level": 0,
                    "under_type_checking": reference.type_only,
                    "reexport": reference.form is ReferenceForm.REEXPORT,
                    "module_level_import": reference.module_level,
                },
            )
        )

    def _unresolved(self, module: str, identity: str, specifier: str, reason: str) -> ImportTarget:
        self._gap(reason, (), module, kind=_GapKind.RESOLUTION)
        return UnresolvedTarget(identity, specifier, reason)

    def _target(
        self,
        rel: str,
        module: str,
        reference: Reference,
        identity: str,
        form: ModuleFormat | Unknown | None,
    ) -> ImportTarget:
        specifier: str = reference.specifier or ""
        source = classify_specifier(specifier)
        if not reference.type_only and source.kind is SpecifierKind.NODE and source.builtin:
            return BuiltinTarget(identity, specifier)
        if reference.mode_override:
            return self._unresolved(
                module,
                identity,
                specifier,
                f"Resolution mode override is not observed: {specifier}",
            )
        if (blocked := self.resolver.blocked) is not None:
            return self._unresolved(module, identity, specifier, blocked.reason)
        if isinstance(form, Unknown):
            return self._unresolved(module, identity, specifier, form.reason)
        mode: ModuleFormat | None = form
        if reference.form is ReferenceForm.DYNAMIC_IMPORT:
            mode = ModuleFormat.ESM if form is not None else None
        elif reference.form in (ReferenceForm.REQUIRE, ReferenceForm.IMPORT_EQUALS):
            mode = ModuleFormat.CJS if form is not None else None
        found = self.resolver.resolve(specifier, rel, mode, prefer_builtin=not reference.type_only)
        if isinstance(found, Unknown):
            if self.bundler and found.package_internal and source.npm_package:
                # The bundler picks the file inside the package; the package is the dependency.
                return ExternalPackageTarget(identity, source.package)
            return self._unresolved(module, identity, specifier, found.reason)
        if found is None:
            if source.builtin:
                return BuiltinTarget(identity, specifier)
            asset = self._bundler_asset(rel, identity, specifier) if self.bundler else None
            if asset is not None:
                return asset
            return self._unresolved(module, identity, specifier, f"Unresolved module: {specifier}")
        return self._local(rel, module, reference, identity, found)

    def _bundler_asset(self, rel: str, identity: str, specifier: str) -> ImportTarget | None:
        """An existing asset a bundler loads itself; a missing one stays an unresolved module."""
        path = classify_asset(specifier)
        source = classify_specifier(specifier)
        if path is None:
            return None
        if source.relative_path and self.resolver.file_exists(rel, path):
            return ExternalPackageTarget(identity, BUNDLER_ASSET)
        if not source.relative and self.resolver.alias_file_exists(path):
            return ExternalPackageTarget(identity, BUNDLER_ASSET)
        if source.npm_package and self.resolver.package_file_exists(rel, path):
            return ExternalPackageTarget(identity, source.package)
        return None

    def _local(
        self, rel: str, module: str, reference: Reference, identity: str, found: Found
    ) -> ImportTarget:
        specifier: str = reference.specifier or ""
        source = classify_specifier(specifier)
        path: str = found.path
        suffix = classify_file(path)
        if self.snapshot.read(path) is None:
            return self._unresolved(
                module, identity, specifier, f"Unavailable local target: {specifier}"
            )
        if any(
            PathToken.parse(segment) is PathToken.NODE_MODULES for segment in path.split("/")
        ) or (not self._selected(path) and found.external):
            if source.kind is SpecifierKind.IMPORTS:
                reason = f"External package alias identity is not observed: {specifier}"
            elif source.relative:
                reason = f"Unidentified external package: {specifier}"
            else:
                return ExternalPackageTarget(identity, source.package)
            return self._unresolved(module, identity, specifier, reason)
        if self.bundler and not (
            self._selected(path) and suffix is not None and suffix.source_kind is not None
        ):
            if classify_asset(path) is not None:
                return ExternalPackageTarget(identity, BUNDLER_ASSET)
            if found.via_paths and not source.relative and source.npm_package:
                # A workspace alias outside the scan roots is a dependency on that package.
                return ExternalPackageTarget(identity, source.package)
        type_only = reference.type_only
        relative = source.relative_path
        lookup = join(posixpath.dirname(rel) or ".", specifier)
        declaration = (
            path if suffix is not None and suffix.source_kind is SourceKind.DECLARATION else None
        )
        runtime = None if declaration else path
        named_suffix = classify_file(specifier)
        explicit = relative and named_suffix is not None and named_suffix.explicit_runtime
        direct = reference.form in (ReferenceForm.REQUIRE, ReferenceForm.IMPORT_EQUALS)
        common_lookup = relative and direct and not explicit
        if not type_only:
            # Compiler substitution does not prove the file Node loads.
            if explicit and self.snapshot.is_file(lookup):
                real = self.snapshot.real(lookup) or lookup
                if self._observe(real) is not None:
                    runtime = real
            elif declaration or (explicit and direct):
                runtime = None
                self._gap(
                    f"Runtime implementation unavailable for declaration: {path}"
                    if declaration
                    else f"CommonJS runtime file is unavailable: {specifier}",
                    kind=_GapKind.RESOLUTION,
                )
        self._observe(path)
        alias_proven = self.bundler and found.via_paths and not found.directory_package
        # A bundler resolves `.` and `..` like `./index`; Node does not prove them.
        proven_relative = relative or (self.bundler and source.relative)
        if (
            not type_only
            and not alias_proven
            and (not proven_relative or found.directory_package or common_lookup)
        ):
            runtime = None
            if common_lookup:
                reason = f"CommonJS runtime target is not proven: {specifier}"
            elif found.directory_package and proven_relative:
                reason = f"Local directory runtime metadata is not proven: {specifier}"
            else:
                reason = f"Local alias runtime conditions are not proven: {specifier}"
            self._gap(reason, (), module, kind=_GapKind.RESOLUTION)
        file = runtime if not type_only and runtime else path
        return LocalTarget(
            identity, module_identity(self.namespace, file), file, runtime, declaration
        )
