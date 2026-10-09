# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Collect TypeScript import facts; whatever cannot be proven is an UNKNOWN gap, never a PASS."""

from __future__ import annotations

import hashlib
import json
import posixpath
from typing import Final

from archkeel.analyzer.runtime import collector_provenance
from archkeel.ir.facts import (
    SOURCE_RESOLUTION_GAP_KIND,
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
from .parse import Base, Definition, Reference, Site, Span, Syntax, parse
from .resolve import Format, Found, Resolver, Unknown, is_builtin, is_relative, package_name

_SECTIONS: tuple[SourceSectionName, ...] = (
    "imports",
    "unknowns",
    "symbols",
    "calls",
    "references",
    "bindings",
)
_SOURCE: Final = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
_DECLARATION: Final = (".d.ts", ".d.mts", ".d.cts")
_EXPLICIT_RUNTIME: Final = (".cjs", ".mjs", ".js")
# What the compiler's `trim()` removes, which Python's `strip()` does not match exactly.
_WHITESPACE: Final = " \t\n\v\f\r                 　﻿"
_FEATURES: Final = (
    "literal-imports",
    "relative-specifiers",
    "node-builtins",
    "local-runtime-closure",
    "inner-uml-v1",
)


def _package_of(module: str) -> str:
    return module.rpartition(".")[0]


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
        self.syntax: dict[str, Syntax] = {}
        self.modules: dict[str, str] = {}
        self.import_targets: dict[str, ImportTarget] = {}
        self.import_sites: dict[str, tuple[str, int, int]] = {}
        self.read = 0

    def facts(self) -> SourceFacts:
        index = 0
        while index < len(self.queue):
            self._file(self.queue[index])
            index += 1
        symbols, calls, references, bindings = self._inner_facts()
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
        listing: str = json.dumps(
            [{"path": item.path, "digest": item.digest, "role": item.role} for item in inputs],
            separators=(",", ":"),
            ensure_ascii=False,
        )
        records: dict[SourceSectionName, tuple[Record, ...]] = {
            "imports": imports,
            "unknowns": unknowns,
            "symbols": tuple(parse_record(item) for item in symbols),
            "calls": tuple(parse_record(item) for item in calls),
            "references": tuple(parse_record(item) for item in references),
            "bindings": tuple(parse_record(item) for item in bindings),
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
                definition.kind,
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
                module,
                qualified,
                parent_name,
                parent_id,
                definition,
                len(by_qualified[qualified]) == 1,
            )
            if definition.kind in {"class", "interface", "enum"}:
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
                if definition.kind == "method":
                    data["method_kind"] = "static" if definition.static else "instance"
            symbols.append(
                classified(
                    item_id=identity,
                    evidence_class=EvidenceClass.FACT,
                    area="source",
                    kind=(
                        "class"
                        if definition.kind in {"class", "interface", "enum"}
                        else definition.kind
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
        module: str,
        qualified: str,
        parent_name: str | None,
        parent_id: str | None,
        definition: Definition,
        binding_unique: bool,
    ) -> dict[str, object]:
        category = "class" if definition.kind in {"class", "interface", "enum"} else definition.kind
        return {
            "qualified_name": qualified,
            "module": module,
            "package": _package_of(module),
            "name": definition.name,
            "parent": parent_name,
            "lexical_parent_id": parent_id,
            "visibility_detail": {
                "kind": definition.visibility or "public",
                "basis": "language",
                "spelling": definition.name,
            },
            "symbol_category": category,
            "source_binding_unique": binding_unique,
            "source_member_binding_static": True,
            "class_header_static": True,
            "decorators": [],
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
        if definition.kind in {"interface", "enum"}:
            data["class_kind"] = "protocol" if definition.kind == "interface" else "enum"
        attribute_declarations: list[dict[str, object]] = [
            {
                "name": member.name,
                "annotation": member.annotation,
                "visibility": {
                    "kind": member.visibility or "public",
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
                "static": member.static,
            }
            for member in definition.members
        ]
        data["attribute_declarations"] = attribute_declarations
        if definition.kind == "enum":
            data["enum_members"] = [member.name for member in definition.members]
        methods = [
            ids[(child_rel, child.span.line, child.span.column)]
            for child_rel, child_module, child in definitions
            if child_module == module
            and child.kind == "method"
            and child.parent == (qualified.removeprefix(f"{module}."))
            and child.parent_line == definition.span.line
            and child.parent_column == definition.span.column
        ]
        attrs = [item["definition_id"] for item in attribute_declarations]
        status = (
            "complete"
            if definition.members_complete and len(by_qualified[qualified]) == 1
            else "partial"
        )
        member_reason = None if status == "complete" else "computed or unsupported member syntax"
        data["member_inventories"] = [
            {
                "schema_version": "1.0.0",
                "kind": "attribute",
                "status": status,
                "definition_ids": attrs,
                "reason": member_reason,
            },
            {
                "schema_version": "1.0.0",
                "kind": "method",
                "status": status,
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
        bindings: list[RawRecord] = []
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
                if site.kind == "reference":
                    references.append(
                        self._reference_record(
                            module, scope, source_id, site, candidates, status, reason, evidence
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
                    calls.append(call)
                    bindings.extend(result_bindings)
        return calls, references, bindings

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
    ) -> tuple[list[str], str, str | None]:
        name = site.name
        candidates: list[str] = []
        reason: str | None = None
        unique_this_member = False
        if (
            name
            and not site.computed
            and not site.scope_ambiguous
            and name not in site.shadowed_names
            and name not in syntax.rebound_names
        ):
            if site.receiver is None:
                candidates.extend(
                    f"{module}.{item.name}"
                    for _, item in top_by_module.get(module, [])
                    if item.name == name
                )
                for target_module, imported, namespace, type_only in import_by_local.get(
                    module, {}
                ).get(name, []):
                    if namespace or (type_only and site.use != "type"):
                        continue
                    candidates.extend(
                        f"{target_module}.{item.name}"
                        for item in definitions_by_module.get(target_module, [])
                        if item.name == imported and item.exported
                    )
            elif site.kind == "reference" and site.receiver == "this":
                class_scope = scope.rpartition(".")[0]
                local_class = by_qualified.get(class_scope, [])
                field_definitions = [
                    definition
                    for _, definition in local_class
                    if definition.kind in {"class", "interface"}
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
            "resolved"
            if len(candidates) == 1
            and reason is None
            and (
                unique_this_member
                or all(len(by_qualified.get(target, [])) == 1 for target in candidates)
            )
            else "partially_resolved"
            if candidates
            else "unresolved"
        )
        if status == "partially_resolved" and reason is None:
            reason = "multiple definition sites share the target name"
        if reason is None and status != "resolved":
            reason = "definition is missing or ambiguous"
        return candidates, status, reason

    def _reference_record(
        self,
        module: str,
        scope: str,
        source_id: str | None,
        site: Site,
        candidates: list[str],
        status: str,
        reason: str | None,
        evidence: str,
    ) -> RawRecord:
        data: dict[str, object] = {
            "source_scope": scope,
            "source_module": module,
            "expression": site.expression,
            "status": status,
            "targets": candidates,
            "candidate_count": len(candidates),
            "candidates_truncated": False,
            "use": site.use,
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
        status: str,
        reason: str | None,
        evidence: str,
        by_qualified: dict[str, list[tuple[str, Definition]]],
    ) -> tuple[RawRecord, list[RawRecord]]:
        call_id = stable_id("TSCALL", module, site.span.line, site.span.column, site.expression)
        data: dict[str, object] = {
            "source_scope": scope,
            "source_module": module,
            "expression": site.expression,
            "status": status,
            "targets": candidates,
            "candidate_count": len(candidates),
            "candidates_truncated": False,
        }
        if reason:
            data["reason"] = reason
        if source_id:
            data["source_definition_id"] = source_id
        binding_records: list[RawRecord] = []
        if site.kind == "new":
            targets = sorted(
                target
                for target in candidates
                if any(item.kind == "class" for _, item in by_qualified.get(target, []))
            )
            create_status = (
                "resolved"
                if len(targets) == 1 and status == "resolved"
                else "partially_resolved"
                if targets
                else "unresolved"
            )
            data["construction"] = {
                "status": create_status,
                "targets": targets,
                "candidates_truncated": False,
                "reason": "Unique local classifier construction"
                if create_status == "resolved"
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
            if definition.kind in {"class", "interface"}
        ]
        targets = [qualified] if classifier_targets else []
        evidence = self._cite(rel, base.span)
        status = (
            "resolved"
            if len(classifier_targets) == 1
            else "partially_resolved"
            if targets
            else "unresolved"
        )
        result: dict[str, object] = {
            "id": stable_id("TSBASE", owner, base.span.line, base.span.column, name),
            "relationship_kind": base.relationship,
            "status": status,
            "targets": targets,
            "candidate_count": len(classifier_targets),
            "candidates_truncated": False,
            "expression": name,
            "evidence_ids": [evidence],
        }
        if not targets:
            result["reason"] = "Base is not a unique local classifier"
        elif status == "partially_resolved":
            result["reason"] = "multiple classifier definition sites share the target name"
        return result

    def _gap(
        self,
        reason: str,
        evidence: tuple[str, ...] = (),
        module: str = "",
        *,
        kind: str = "collection_gap",
    ) -> None:
        identity = stable_id("UNKNOWN", reason, *evidence, module)
        self.gaps.setdefault(
            identity,
            classified(
                item_id=identity,
                evidence_class=EvidenceClass.UNKNOWN,
                area="source",
                kind=kind,
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
        if content is not None and self._selected(rel) and rel.endswith(_SOURCE):
            if rel not in self.queue:
                self.queue.append(rel)
        elif content is not None:
            self._gap(
                f"Local dependency outside selected source scope: {rel}",
                kind=SOURCE_RESOLUTION_GAP_KIND,
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
        self.syntax[rel] = syntax
        self.modules[rel] = module
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
        resolver: Resolver = self.resolver
        form = resolver.format_of(rel)
        cjs = (
            rel.endswith((".cjs", ".cts"))
            or options.module == "commonjs"
            or (form == "cjs" and options.module in ("nodenext", "node16"))
        )
        for reference in syntax.references:
            evidence = self._cite(rel, reference.span)
            if reference.form == "require" and (not cjs or syntax.shadows_require):
                self._gap(
                    "Unproven or shadowed require call",
                    (evidence,),
                    module,
                    kind=SOURCE_RESOLUTION_GAP_KIND,
                )
            elif reference.specifier is None:
                self._gap(
                    f"Computed {reference.form} cannot be resolved",
                    (evidence,),
                    module,
                    kind=SOURCE_RESOLUTION_GAP_KIND,
                )
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
        specifier: str = reference.specifier or ""
        identity = stable_id(
            "IMP", module, reference.span.line, reference.span.column, reference.form
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
                kind=reference.form,
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
                    "reexport": reference.form == "reexport",
                    "module_level_import": reference.module_level,
                },
            )
        )

    def _unresolved(self, module: str, identity: str, specifier: str, reason: str) -> ImportTarget:
        self._gap(reason, (), module, kind=SOURCE_RESOLUTION_GAP_KIND)
        return UnresolvedTarget(identity, specifier, reason)

    def _target(
        self,
        rel: str,
        module: str,
        reference: Reference,
        identity: str,
        form: Format | Unknown | None,
    ) -> ImportTarget:
        specifier: str = reference.specifier or ""
        if not reference.type_only and specifier.startswith("node:") and is_builtin(specifier):
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
        mode: Format | None = form
        if reference.form == "dynamic_import":
            mode = "esm" if form is not None else None
        elif reference.form in ("require", "import_equals"):
            mode = "cjs" if form is not None else None
        found = self.resolver.resolve(specifier, rel, mode, prefer_builtin=not reference.type_only)
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
        specifier: str = reference.specifier or ""
        path: str = found.path
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
        declaration = path if path.endswith(_DECLARATION) else None
        runtime = None if declaration else path
        explicit = relative and specifier.endswith(_EXPLICIT_RUNTIME)
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
                    else f"CommonJS runtime file is unavailable: {specifier}",
                    kind=SOURCE_RESOLUTION_GAP_KIND,
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
            self._gap(reason, (), module, kind=SOURCE_RESOLUTION_GAP_KIND)
        file = runtime if not type_only and runtime else path
        return LocalTarget(
            identity, module_identity(self.namespace, file), file, runtime, declaration
        )
