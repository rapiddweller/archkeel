# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Collect TypeScript import facts; whatever cannot be proven is an UNKNOWN gap, never a PASS."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from typing import Final

from archkeel.analyzer.runtime import collector_provenance
from archkeel.ir.facts import (
    BuiltinTarget,
    Capabilities,
    CollectionCoverage,
    EvidenceClass,
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

from .config import Snapshot, join, load_config, within
from .parse import Reference, Span, Syntax, parse
from .resolve import Format, Found, Resolver, Unknown, is_builtin, is_relative, package_name

_SECTIONS: tuple[SourceSectionName, ...] = ("imports", "unknowns")
_SOURCE: Final = re.compile(r"\.(?:[cm]?ts|tsx|[cm]?js|jsx)$")
_DECLARATION: Final = re.compile(r"\.d\.[cm]?ts$")
_EXPLICIT_RUNTIME: Final = re.compile(r"\.(?:cjs|mjs|js)$")
# What the compiler's `trim()` removes, which Python's `strip()` does not match exactly.
_WHITESPACE: Final = " \t\n\v\f\r                 　﻿"
_FEATURES: Final = (
    "literal-imports",
    "relative-specifiers",
    "node-builtins",
    "local-runtime-closure",
)


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
        # Every file to read, in discovery order; an entry added while walking is walked too.
        self.queue: list[str] = list(self.config.files)
        self.evidence: dict[str, RawEvidence] = {}
        self.imports: list[RawRecord] = []
        self.gaps: dict[str, RawRecord] = {}
        self.targets: list[ImportTarget] = []
        self.files: list[FileFact] = []
        self.read = 0

    def facts(self) -> SourceFacts:
        index = 0
        while index < len(self.queue):
            self._file(self.queue[index])
            index += 1
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
        adapter, runtime = collector_provenance("typescript")
        listing = json.dumps(
            [{"path": item.path, "digest": item.digest, "role": item.role} for item in inputs],
            separators=(",", ":"),
            ensure_ascii=False,
        )
        records: dict[SourceSectionName, tuple[Record, ...]] = {
            "imports": imports,
            "unknowns": unknowns,
        }
        return SourceFacts(
            "archkeel-typescript-imports",
            adapter,
            runtime,
            SourceInfo(
                self.request.snapshot.git_head,
                self.request.snapshot.dirty,
                hashlib.sha256(listing.encode("utf-8")).hexdigest(),
                tuple(f"{root}/**" if self.snapshot.is_dir(root) else root for root in self.roots),
            ),
            Capabilities(_SECTIONS, _FEATURES),
            inputs,
            tuple(self.files),
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

    def _gap(self, reason: str, evidence: tuple[str, ...] = (), module: str = "") -> None:
        identity = stable_id("UNKNOWN", reason, *evidence, module)
        self.gaps.setdefault(
            identity,
            classified(
                item_id=identity,
                evidence_class=EvidenceClass.UNKNOWN,
                area="source",
                kind="collection_gap",
                title=reason,
                subjects=[module],
                evidence_ids=list(evidence),
                data={"reason": reason, "module": module},
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
        if content is not None and self._selected(rel) and _SOURCE.search(rel):
            if rel not in self.queue:
                self.queue.append(rel)
        elif content is not None:
            self._gap(f"Local dependency outside selected source scope: {rel}")
        return content

    def _file(self, rel: str) -> None:
        content = self.snapshot.read(rel)
        if content is None:
            self._gap(f"Unreadable selected source: {rel}")
            return
        try:
            module = module_identity(self.namespace, rel)
        except ValueError:
            self._gap(f"Source path has no module identity: {rel}")
            return
        self.read += 1
        self.snapshot.select(rel)
        text = str(content, "utf-8", "replace")
        evidence = file_evidence(self.evidence, rel, (text.partition("\n")[0],))
        self.files.append(
            FileFact(
                stable_id("FILE", module),
                rel,
                module,
                module.rpartition(".")[0],
                frozenset(),
                False,
                False,
                frozenset(),
                not text.strip(_WHITESPACE),
                evidence,
            )
        )
        syntax = parse(rel, text.encode("utf-8"))
        if syntax.first_error is not None:
            line = syntax.first_error.line
            self._gap(
                f"Syntax error in {rel}: unparseable construct at line {line}", (evidence,), module
            )
        for concern in syntax.concerns:
            self._gap(concern.reason, (self._cite(rel, concern.span),), module)
        self._references(rel, module, syntax)

    def _references(self, rel: str, module: str, syntax: Syntax) -> None:
        options = self.config.options
        form = self.resolver.format_of(rel)
        cjs = (
            rel.endswith((".cjs", ".cts"))
            or options.module == "commonjs"
            or (form == "cjs" and options.module in ("nodenext", "node16"))
        )
        for reference in syntax.references:
            evidence = self._cite(rel, reference.span)
            if reference.form == "require" and (not cjs or syntax.shadows_require):
                self._gap("Unproven or shadowed require call", (evidence,), module)
            elif reference.specifier is None:
                self._gap(f"Computed {reference.form} cannot be resolved", (evidence,), module)
            else:
                self._import(rel, module, reference, evidence, form)

    def _import(
        self,
        rel: str,
        module: str,
        reference: Reference,
        evidence: str,
        form: Format | Unknown | None,
    ) -> None:
        specifier = reference.specifier or ""
        identity = stable_id(
            "IMP", module, reference.span.line, reference.span.column, reference.form
        )
        target = self._target(rel, module, reference, identity, form)
        self.targets.append(target)
        if isinstance(target, LocalTarget):
            target_module, target_package = target.module, target.module.rpartition(".")[0]
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
                kind=reference.form,
                title=f"{module} imports {specifier}",
                subjects=[module, target_module],
                evidence_ids=[evidence],
                data={
                    "source_module": module,
                    "source_package": module.rpartition(".")[0],
                    "target_module": target_module,
                    "target_package": target_package,
                    "symbol": None,
                    "binding": None,
                    "symbols_known": False,
                    "specifier": specifier,
                    "type_only": reference.type_only,
                    "relative_level": 0,
                    "under_type_checking": reference.type_only,
                    "reexport": reference.form == "reexport",
                    "module_level_import": reference.module_level,
                },
            )
        )

    def _unresolved(self, module: str, identity: str, specifier: str, reason: str) -> ImportTarget:
        self._gap(reason, (), module)
        return UnresolvedTarget(identity, specifier, reason)

    def _target(
        self,
        rel: str,
        module: str,
        reference: Reference,
        identity: str,
        form: Format | Unknown | None,
    ) -> ImportTarget:
        specifier = reference.specifier or ""
        if not reference.type_only and specifier.startswith("node:") and is_builtin(specifier):
            return BuiltinTarget(identity, specifier)
        if reference.mode_override:
            return self._unresolved(
                module,
                identity,
                specifier,
                f"Resolution mode override is not observed: {specifier}",
            )
        if (blocked := self.resolver.blocked()) is not None:
            return self._unresolved(module, identity, specifier, blocked.reason)
        if isinstance(form, Unknown):
            return self._unresolved(module, identity, specifier, form.reason)
        mode: Format | None = form
        if reference.form == "dynamic_import":
            mode = "esm" if form is not None else None
        elif reference.form in ("require", "import_equals"):
            mode = "cjs" if form is not None else None
        found = self.resolver.resolve(specifier, rel, mode)
        if isinstance(found, Unknown):
            return self._unresolved(module, identity, specifier, found.reason)
        if found is None:
            if is_builtin(specifier):
                return BuiltinTarget(identity, specifier)
            return self._unresolved(module, identity, specifier, f"Unresolved module: {specifier}")
        return self._local(rel, module, reference, identity, found)

    def _local(
        self, rel: str, module: str, reference: Reference, identity: str, found: Found
    ) -> ImportTarget:
        specifier = reference.specifier or ""
        path = found.path
        if self.snapshot.read(path) is None:
            return self._unresolved(
                module, identity, specifier, f"Unavailable local target: {specifier}"
            )
        if "node_modules" in path.split("/") or (not self._selected(path) and found.external):
            if specifier.startswith("#"):
                reason = f"External package alias identity is not observed: {specifier}"
            elif is_relative(specifier):
                reason = f"Unidentified external package: {specifier}"
            else:
                return ExternalPackageTarget(identity, package_name(specifier))
            return self._unresolved(module, identity, specifier, reason)
        type_only = reference.type_only
        relative = specifier.startswith(("./", "../"))
        lookup = join(posixpath.dirname(rel) or ".", specifier)
        declaration = path if _DECLARATION.search(path) else None
        runtime = None if declaration else path
        explicit = relative and _EXPLICIT_RUNTIME.search(specifier) is not None
        direct = reference.form in ("require", "import_equals")
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
                    else f"CommonJS runtime file is unavailable: {specifier}"
                )
        self._observe(path)
        if not type_only and (not relative or found.directory_package or common_lookup):
            runtime = None
            if common_lookup:
                reason = f"CommonJS runtime target is not proven: {specifier}"
            elif found.directory_package:
                reason = f"Local directory runtime metadata is not proven: {specifier}"
            else:
                reason = f"Local alias runtime conditions are not proven: {specifier}"
            self._gap(reason, (), module)
        file = runtime if not type_only and runtime else path
        return LocalTarget(
            identity, module_identity(self.namespace, file), file, runtime, declaration
        )
