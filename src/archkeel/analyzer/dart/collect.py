# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Assemble Dart source evidence without evaluating architecture policy."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter

from archkeel.analyzer.runtime import collector_provenance
from archkeel.ir.facts import (
    BuiltinTarget,
    Capabilities,
    CollectionCoverage,
    EvidenceClass,
    ExternalPackageTarget,
    FactSection,
    FileFact,
    LocalTarget,
    Record,
    SourceFacts,
    SourceInfo,
    SourceSectionName,
    UnresolvedTarget,
    stable_id,
)
from archkeel.ir.facts_codec import RawEvidence, RawRecord, parse_evidence, parse_record
from archkeel.ir.protocol import CollectionRequest, DartSettings
from archkeel.ir.source_records import RawData, classified, file_evidence, record_evidence

from .parse import Definition, Member, Parameter, Site, Span, Syntax, parse
from .resolve import (
    ConstructionResolution,
    ResolvedBinding,
    ResolvedParameter,
    ResolvedSite,
    Resolver,
)
from .snapshot import Snapshot, read_snapshot

_SECTIONS: tuple[SourceSectionName, ...] = (
    "imports",
    "unknowns",
    "symbols",
    "calls",
    "references",
    "bindings",
)


def collect(request: CollectionRequest) -> SourceFacts:
    if not isinstance(request.resolver, DartSettings):
        raise ValueError("Dart collector requires the Dart resolver")
    snapshot = read_snapshot(request)
    syntax: dict[str, Syntax] = {}
    for source in snapshot.sources:
        syntax[source.rel_path] = parse(source.content)
    resolver = Resolver(snapshot, syntax)
    collection = _Collection(request, snapshot, syntax, resolver)
    return collection.facts()


class _Collection:
    def __init__(
        self,
        request: CollectionRequest,
        snapshot: Snapshot,
        syntax: dict[str, Syntax],
        resolver: Resolver,
    ) -> None:
        self.request = request
        self.snapshot = snapshot
        self.syntax = syntax
        self.resolver: Resolver = resolver
        self.sources = snapshot.source_by_path
        self.modules: dict[str, str] = {}
        self.evidence: dict[str, RawEvidence] = {}
        self.gaps: dict[str, RawRecord] = {}
        self.imports: list[RawRecord] = []
        self.targets: list[
            LocalTarget | BuiltinTarget | ExternalPackageTarget | UnresolvedTarget
        ] = []
        self.symbols: list[RawRecord] = []
        self.calls: list[RawRecord] = []
        self.references: list[RawRecord] = []
        self.bindings: list[RawRecord] = []
        self.symbol_by_name: dict[str, RawRecord] = {}
        self.definition_ids: dict[tuple[str, int, int], str] = {}
        self.definition_names: dict[tuple[str, int], str] = {}
        self.scope_candidates: list[tuple[str, str, str, str, Span, int, int]] = []
        self.parsed: set[str] = set()
        self.sdk_supported = True
        self.incomplete_inventory_paths: set[str] = set()
        self.incomplete_inventory_ids: set[str] = set()

    def facts(self) -> SourceFacts:
        self._prepare_sources()
        self._collect_records()
        return self._source_facts()

    def _prepare_sources(self) -> None:
        for source in self.snapshot.sources:
            syntax = self.syntax[source.rel_path]
            self.modules[source.rel_path] = source.module
            if syntax.first_error is None:
                self.parsed.add(source.rel_path)
            else:
                self.incomplete_inventory_paths.add(source.rel_path)
                self._gap(
                    source.rel_path,
                    syntax.first_error,
                    "SyntaxError",
                    "syntax errors prevent complete source facts",
                )
            for concern in syntax.concerns:
                if concern.kind == "syntax_error" and syntax.first_error is not None:
                    continue
                kind = {
                    "unsupported_directive": "DirectiveError",
                    "unsupported_declaration": "UnsupportedDeclaration",
                    "unsupported_member": "UnsupportedMember",
                    "unsupported_parameter": "UnsupportedParameter",
                }.get(concern.kind, concern.kind)
                self._gap(source.rel_path, concern.span, kind, concern.message)

        for problem in self.snapshot.problems:
            kind = {
                "SymlinkError": "DartSourceLink"
                if problem.path.endswith(".dart")
                else problem.kind,
                "ModuleIdCollision": "DartModuleCollision",
            }.get(problem.kind, problem.kind)
            self._gap(problem.path, _file_span(), kind, problem.message)
        self._sdk_constraints()

        for rel in tuple(self.parsed):
            module = self.resolver.module_for(rel)
            if module is None:
                self.parsed.remove(rel)
                self._gap(
                    rel, _file_span(), "PartError", "source has no unique selected library owner"
                )
            else:
                self.modules[rel] = module
        self._language_overrides()

    def _collect_records(self) -> None:
        self._declarations()
        self._imports()
        self._bases()
        self._sites()
        self._duplicates()
        self._resolver_gaps()
        self._finalize_inventories()

    def _resolver_gaps(self) -> None:
        for problem in self.resolver.problems:
            kind = {
                "ImportError": "DirectiveError",
                "PartError": "PartError",
            }.get(problem.kind, problem.kind)
            self._gap(
                problem.path,
                problem.span or _file_span(),
                kind,
                problem.message,
            )

    def _source_facts(self) -> SourceFacts:
        inputs = tuple(self.snapshot.inputs)
        listing = b"".join(
            json.dumps(
                {"path": item.path, "digest": item.digest, "role": item.role},
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            for item in inputs
        )
        adapter, runtime = collector_provenance("dart")
        records: dict[SourceSectionName, tuple[Record, ...]] = {
            "imports": tuple(
                parse_record(item) for item in sorted(self.imports, key=lambda x: x["id"])
            ),
            "unknowns": tuple(parse_record(item) for _, item in sorted(self.gaps.items())),
            "symbols": tuple(
                parse_record(item) for item in sorted(self.symbols, key=lambda x: x["id"])
            ),
            "calls": tuple(
                parse_record(item) for item in sorted(self.calls, key=lambda x: x["id"])
            ),
            "references": tuple(
                parse_record(item) for item in sorted(self.references, key=lambda x: x["id"])
            ),
            "bindings": tuple(
                parse_record(item) for item in sorted(self.bindings, key=lambda x: x["id"])
            ),
        }
        files = tuple(sorted(self._files(), key=lambda item: item.rel_path))
        return SourceFacts(
            "archkeel-dart-analyzer",
            adapter,
            runtime,
            SourceInfo(
                self.request.snapshot.git_head,
                self.request.snapshot.dirty,
                hashlib.sha256(listing).hexdigest(),
                tuple(
                    f"{root}/**/*.dart" if root != "." else "**/*.dart"
                    for root in self.snapshot.roots
                ),
            ),
            Capabilities(_SECTIONS, ("inner-uml-v1",)),
            inputs,
            files,
            tuple(self.targets),
            tuple(FactSection(name, records[name]) for name in _SECTIONS),
            CollectionCoverage(
                tuple(sorted(self.sources)),
                len(self.sources),
                len(self.parsed),
                not self.gaps and bool(self.sources),
                records["unknowns"],
            ),
            tuple(parse_evidence(item) for _, item in sorted(self.evidence.items())),
        )

    def _declarations(self) -> None:
        for rel, syntax in sorted(self.syntax.items()):
            if rel not in self.parsed:
                continue
            module = self.modules[rel]
            for definition in syntax.definitions:
                self._definition(rel, module, definition, None, None)

    def _sdk_constraints(self) -> None:
        if self.snapshot.sdk_constraint_state == "requirement_missing":
            return
        if self.snapshot.sdk_constraint_state != "declared":
            self.sdk_supported = False
            self._gap(
                "pubspec.yaml",
                _file_span(),
                "SdkConstraintError",
                "Dart SDK support constraint is missing or invalid",
            )
            return
        constraint = self.snapshot.sdk_constraint
        if constraint is None:
            self.sdk_supported = False
            self._gap(
                "pubspec.yaml", _file_span(), "SdkConstraintError", "Dart SDK constraint is missing"
            )
            return
        if not _valid_constraint(constraint):
            self.sdk_supported = False
            self._gap(
                "pubspec.yaml",
                _file_span(),
                "SdkConstraintError",
                "Dart SDK constraint is malformed",
            )
            return
        floor = _constraint_floor(constraint)
        if floor is None:
            self.sdk_supported = False
            self._gap(
                "pubspec.yaml",
                _file_span(),
                "SdkConstraintError",
                "Dart SDK constraint does not prove support within 2.12 through 3.12",
            )
            return
        minimum = floor
        if minimum[:2] < (2, 12) or minimum[:2] > (3, 12):
            self.sdk_supported = False
            self._gap(
                "pubspec.yaml",
                _file_span(),
                "SdkConstraintError",
                "Dart SDK constraint is outside parser support 2.12 through 3.12",
            )

    def _language_overrides(self) -> None:
        versions: dict[str, dict[str, tuple[int, int, int]]] = {}
        for rel in self.parsed:
            content = self.sources[rel].content.decode("utf-8", "replace")
            match = re.search(r"(?m)^\s*//\s*@dart=([^\s]+)", content)
            if match is None:
                continue
            raw = match.group(1)
            if re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", raw) is None:
                self._gap(
                    rel,
                    _file_span(),
                    "LanguageVersionError",
                    f"unsupported Dart language version override {raw!r}",
                )
                continue
            version = _version(raw)
            if version[:2] < (2, 12) or version[:2] > (3, 12):
                self._gap(
                    rel,
                    _file_span(),
                    "LanguageVersionError",
                    f"unsupported Dart language version override {raw!r}",
                )
                continue
            versions.setdefault(self.modules[rel], {})[rel] = version
        for module, paths in versions.items():
            if len(set(paths.values())) <= 1:
                continue
            main = next(
                (path for path in paths if self.sources[path].module == module), next(iter(paths))
            )
            self._gap(
                main,
                _file_span(),
                "LanguageVersionError",
                "library parts declare inconsistent Dart language versions",
            )

    def _definition(
        self,
        rel: str,
        module: str,
        definition: Definition,
        parent: str | None,
        parent_id: str | None,
    ) -> str:
        name = definition.name
        qualified = f"{parent}.{name}" if parent else f"{module}.{name}"
        kind = definition.kind
        record_kind = {
            "typedef": "alias",
            "mixin": "class",
            "enum": "class",
            "interface": "class",
            "getter": "function",
            "setter": "function",
        }.get(kind, kind)
        symbol_id = stable_id("DARTDEF", rel, definition.span.start_byte, qualified, record_kind)
        self.definition_ids[(rel, definition.span.line, definition.span.column)] = symbol_id
        data = self._meta(
            rel, module, name, kind, qualified, parent, parent_id, definition.visibility
        )
        data["symbol_category"] = "type_alias" if kind in {"typedef", "alias"} else record_kind
        data["modifiers"] = list(definition.modifiers)
        if kind in {"class", "mixin", "enum", "interface"}:
            self._class_definition(rel, module, definition, qualified, symbol_id, data)
        elif kind in {"function", "getter", "setter"}:
            parameters = self._parameters(definition.parameters)
            if kind in {"getter", "setter"}:
                qualified = f"{qualified}::{kind}"
                data["qualified_name"] = qualified
                data["accessor_kind"] = kind
            data.update(
                annotation=None,
                returns="void"
                if kind == "setter" and definition.return_type is None
                else definition.return_type,
                parameters=parameters,
                method_kind="static",
                signature_complete=all(p["default_known"] for p in parameters),
            )
        elif kind in {"typedef", "alias"}:
            data.update(symbol_category="type_alias", annotation=definition.alias, constant=None)
        elif kind in {"variable", "constant", "attribute"}:
            record_kind = "constant" if definition.constant else "attribute"
            data.update(
                symbol_category=record_kind,
                annotation=definition.return_type,
                constant=definition.literal if definition.constant else None,
            )
            if definition.constant:
                data["symbol_category"] = "constant"
        else:
            self._gap(
                rel,
                definition.span,
                "UnsupportedDeclaration",
                f"declaration kind {kind!r} is not represented",
            )
            return symbol_id
        self._publish_definition(
            rel, name, qualified, kind, record_kind, symbol_id, definition, data
        )
        return symbol_id

    def _publish_definition(
        self,
        rel: str,
        name: str,
        qualified: str,
        kind: str,
        record_kind: str,
        symbol_id: str,
        definition: Definition,
        data: RawData,
    ) -> None:
        self._add_symbol(
            self._record(
                symbol_id,
                "source",
                record_kind,
                f"{qualified} declaration",
                [qualified],
                [self._cite(rel, definition.span)],
                data,
            )
        )
        self.definition_names[(rel, definition.span.start_byte)] = qualified
        if kind in {"function", "getter", "setter"}:
            scope_end = min(
                (
                    item.span.start_byte
                    for item in self.syntax[rel].definitions
                    if item.span.start_byte > definition.span.start_byte
                ),
                default=len(self.sources[rel].content),
            )
            self.scope_candidates.append(
                (
                    rel,
                    name,
                    qualified,
                    symbol_id,
                    definition.span,
                    definition.span.start_byte,
                    scope_end,
                )
            )

    def _class_definition(
        self,
        rel: str,
        module: str,
        definition: Definition,
        qualified: str,
        symbol_id: str,
        data: RawData,
    ) -> None:
        class_kind = {
            "class": "class",
            "interface": "protocol",
            "mixin": "mixin",
            "enum": "enum",
        }[definition.kind]
        attributes: list[RawData] = []
        methods: list[str] = []
        if definition.kind == "enum":
            for literal, span in zip(
                definition.enum_members, definition.enum_member_spans, strict=True
            ):
                attributes.append(
                    self._attribute(rel, span, qualified, literal, None, True, None, True)
                )
        for member in definition.members:
            if member.kind == "field":
                attributes.append(
                    self._attribute(
                        rel,
                        member.span,
                        qualified,
                        member.name,
                        member.annotation,
                        member.static,
                        member.initializer,
                        member.constant,
                    )
                )
            elif member.kind in {"method", "constructor", "getter", "setter", "operator"}:
                methods.append(
                    self._member(rel, module, qualified, symbol_id, definition.name, member)
                )
            else:
                self.incomplete_inventory_ids.add(symbol_id)
                self._gap(
                    rel,
                    member.span,
                    "UnsupportedMember",
                    f"member kind {member.kind!r} is not represented",
                )
        data.update(
            class_kind=class_kind,
            enum_members=list(definition.enum_members),
            attribute_declarations=attributes,
            member_inventories=[
                _inventory("attribute", [item["definition_id"] for item in attributes]),
                _inventory("method", methods),
            ],
        )
        if definition.kind in {"class", "mixin"}:
            data["mixin_capable"] = definition.kind == "mixin" or "mixin" in definition.modifiers

    def _member(
        self,
        rel: str,
        module: str,
        parent: str,
        parent_id: str,
        class_name: str,
        member: Member,
    ) -> str:
        name = member.name
        accessor = f"::{member.kind}" if member.kind in {"getter", "setter"} else ""
        qualified = f"{parent}.{name}{accessor}"
        identity = stable_id("DARTDEF", rel, member.span.start_byte, qualified, "method")
        constructor = member.kind == "constructor"
        owner = self._owner_definition(rel, module, parent)
        parameters = self._member_parameters(rel, owner, member, constructor)
        returns = None if constructor else member.return_type
        if member.kind == "setter" and returns is None:
            returns = "void"
        if constructor:
            returns = (
                f"{class_name}<{', '.join(owner.type_parameters)}>"
                if owner is not None and owner.type_parameters
                else class_name
            )
        signature_complete = all(
            p["default_known"] and (not p.get("field_formal") or p.get("annotation") is not None)
            for p in parameters
        )
        member_spelling = name.rsplit(".", 1)[-1]
        visibility = (
            ("private" if member_spelling.startswith("_") else "public")
            if constructor
            else member.visibility
        )
        data = self._meta(rel, module, name, "method", qualified, parent, parent_id, visibility)
        data.update(
            annotation=None,
            returns=returns,
            parameters=parameters,
            method_kind=(
                "factory"
                if member.factory
                else "constructor"
                if constructor
                else "static"
                if member.static
                else "instance"
            ),
            signature_complete=signature_complete,
        )
        if member.kind in {"getter", "setter"}:
            data["accessor_kind"] = member.kind
        self._add_symbol(
            self._record(
                identity,
                "source",
                "method",
                f"{qualified} declaration",
                [qualified],
                [self._cite(rel, member.span)],
                data,
            )
        )
        self.definition_ids[(rel, member.span.line, member.span.column)] = identity
        self.definition_names[(rel, member.span.start_byte)] = qualified
        owner_start = owner.span.start_byte if owner is not None else member.span.start_byte
        owner_end = owner.span.end_byte if owner is not None else member.span.end_byte
        self.scope_candidates.append(
            (rel, name, qualified, identity, member.span, owner_start, owner_end)
        )
        return identity

    def _owner_definition(self, rel: str, module: str, parent: str) -> Definition | None:
        return next(
            (
                definition
                for definition in self.syntax[rel].definitions
                if f"{module}.{definition.name}" == parent
            ),
            None,
        )

    def _member_parameters(
        self, rel: str, owner: Definition | None, member: Member, constructor: bool
    ) -> list[RawData]:
        if not constructor or owner is None:
            return self._parameters(member.parameters)
        resolution = self.resolver.resolve_parameters(rel, owner, member)
        for problem in resolution.problems:
            self._gap(
                problem.path,
                problem.span or member.span,
                problem.kind,
                problem.message,
            )
        return self._resolved_parameters(resolution.parameters)

    def _attribute(
        self,
        rel: str,
        span: Span,
        parent: str,
        name: str,
        annotation: str | None,
        static: bool,
        constant: str | None,
        is_constant: bool = False,
    ) -> RawData:
        identity = stable_id("DARTATTR", rel, span.start_byte, parent, name)
        qualified = f"{parent}.{name}"
        self.definition_names[(rel, span.start_byte)] = qualified
        self.definition_ids[(rel, span.line, span.column)] = identity
        return {
            "name": name,
            "annotation": annotation,
            "visibility": {
                "kind": "private" if name.startswith("_") else "public",
                "basis": "language",
                "spelling": name,
            },
            "definition_id": identity,
            "evidence_ids": [self._cite(rel, span)],
            "static": static,
            "constant": constant if is_constant else None,
        }

    def _meta(
        self,
        rel: str,
        module: str,
        name: str,
        kind: str,
        qualified: str,
        parent: str | None,
        parent_id: str | None,
        visibility: str,
    ) -> RawData:
        return {
            "qualified_name": qualified,
            "module": module,
            "source_file": rel,
            "package": module.rpartition(".")[0],
            "name": name,
            "parent": parent,
            "lexical_parent_id": parent_id,
            "visibility_detail": {
                "kind": "private" if visibility == "private" else "public",
                "basis": "language",
                "spelling": name.rsplit(".", 1)[-1],
            },
            "symbol_category": "type_alias" if kind in {"typedef", "alias"} else kind,
            "source_binding_unique": True,
            "source_member_binding_static": True,
            "class_header_static": True,
            "decorators": [],
            "signature_complete": True,
            "overload_signature": False,
        }

    def _parameters(self, values: tuple[Parameter, ...]) -> list[RawData]:
        return [
            {
                "name": item.name,
                "annotation": item.annotation,
                "kind": "keyword_only" if item.kind == "named" else "positional",
                "default": (
                    item.default if item.default is not None else "null" if item.optional else None
                ),
                "default_known": item.default_known,
            }
            for item in values
        ]

    @staticmethod
    def _resolved_parameters(values: tuple[ResolvedParameter, ...]) -> list[RawData]:
        return [
            {
                "name": item.name,
                "annotation": item.annotation,
                "kind": "keyword_only" if item.kind == "named" else "positional",
                "default": item.default,
                "default_known": item.default_known,
            }
            for item in values
        ]

    def _add_symbol(self, record: RawRecord) -> None:
        self.symbols.append(record)
        qualified = record["data"].get("qualified_name")
        if isinstance(qualified, str):
            self.symbol_by_name[qualified] = record

    def _imports(self) -> None:
        for rel, syntax in sorted(self.syntax.items()):
            if rel not in self.parsed:
                continue
            module = self.modules[rel]
            for directive in syntax.directives:
                if directive.kind not in {"import", "export"}:
                    continue
                resolved = self.resolver.resolve_directive(rel, directive)
                selected: set[str] | None = None
                for mode, values in directive.combinators:
                    names = set(values)
                    if mode == "show":
                        selected = names if selected is None else selected & names
                    elif selected is not None:
                        selected -= names
                symbols: tuple[str | None, ...] = tuple(sorted(selected)) if selected else (None,)
                for target in resolved:
                    for symbol in symbols:
                        identity = stable_id(
                            "DARTIMP", rel, directive.span.start_byte, target.uri, symbol
                        )
                        evidence_id = self._cite(rel, directive.span)
                        target_module = target.module
                        known = selected is not None and bool(selected)
                        self.imports.append(
                            self._record(
                                identity,
                                "dependencies",
                                "import",
                                f"{module} imports {target.uri}",
                                [module, target_module],
                                [evidence_id],
                                {
                                    "source_module": module,
                                    "source_package": module.rpartition(".")[0],
                                    "target_module": target_module,
                                    "target_package": (
                                        target_module.rpartition(".")[0]
                                        if target.rel_path is not None
                                        else target.package
                                    ),
                                    "symbol": symbol,
                                    "binding": symbol
                                    or (directive.prefix if directive.kind == "import" else None),
                                    "symbols_known": known,
                                    "relative_level": 0,
                                    "under_type_checking": False,
                                    "ordinary_module": True,
                                    "module_level_import": True,
                                    "reexport": directive.kind == "export",
                                    "reexport_chain": []
                                    if symbol is None
                                    else [f"{target_module}.{symbol}"],
                                    "origin_definition": None
                                    if symbol is None
                                    else f"{target_module}.{symbol}",
                                    "symbol_visibility": None
                                    if symbol is None
                                    else ("private" if symbol.startswith("_") else "public_name"),
                                },
                            )
                        )
                        if target.rel_path is not None:
                            self.targets.append(
                                LocalTarget(identity, target_module, target.rel_path)
                            )
                        elif target.uri.startswith("dart:"):
                            self.targets.append(BuiltinTarget(identity, target_module))
                        elif target.package != self.snapshot.package_name:
                            self.targets.append(ExternalPackageTarget(identity, target.package))
                        else:
                            self.targets.append(
                                UnresolvedTarget(identity, target.uri, "target is not selected")
                            )

    def _bases(self) -> None:
        for rel, syntax in sorted(self.syntax.items()):
            if rel not in self.parsed:
                continue
            module = self.modules[rel]
            for definition in syntax.definitions:
                if definition.kind not in {"class", "interface", "mixin", "enum"}:
                    continue
                qualified = f"{module}.{definition.name}"
                record = self.symbol_by_name.get(qualified)
                if record is None:
                    continue
                bases = []
                for kind, names in (
                    ("inherits", definition.extends),
                    ("mixes_in", definition.with_types),
                    ("realizes", definition.implements),
                ):
                    for name in names:
                        targets = self.resolver.resolve_name(rel, name)
                        if len(targets) == 1:
                            target = self._canonical_target(targets[0])
                            target_record = self.symbol_by_name.get(target)
                        else:
                            target, target_record = "", None
                        is_class = target_record is not None and target_record["kind"] == "class"
                        mixin_target = bool(
                            target_record is not None
                            and (
                                target_record["data"].get("class_kind") == "mixin"
                                or target_record["data"].get("mixin_capable") is True
                            )
                        )
                        resolved = is_class and (kind != "mixes_in" or mixin_target)
                        bases.append(
                            {
                                "id": stable_id(
                                    "DARTBASE", rel, definition.span.start_byte, kind, name
                                ),
                                "relationship_kind": kind,
                                "status": "resolved" if resolved else "unresolved",
                                "targets": [target] if resolved else [],
                                "candidate_count": 1 if resolved else len(targets),
                                "candidates_truncated": False,
                                "expression": name,
                                "reason": "Analyzer resolved local declared type"
                                if resolved
                                else (
                                    "with target is not proven to be a local "
                                    "mixin-capable declaration"
                                    if kind == "mixes_in"
                                    else "base type is external or unresolved"
                                ),
                                "evidence_ids": [self._cite(rel, definition.span)],
                            }
                        )
                record["data"]["base_declarations"] = bases

    def _canonical_target(self, qualified: str) -> str:
        record = self.symbol_by_name.get(qualified)
        if record is None or record["kind"] != "alias":
            return qualified
        annotation = record["data"].get("annotation")
        if not isinstance(annotation, str) or self.resolver is None:
            return qualified
        targets = self.resolver.resolve_name(record["data"]["source_file"], annotation)
        return targets[0] if len(targets) == 1 else qualified

    def _sites(self) -> None:
        for rel, _syntax in sorted(self.syntax.items()):
            if rel not in self.parsed:
                continue
            module = self.modules[rel]
            resolved_sites = self.resolver.resolved_sites(rel)
            site_bindings = self._binding_sites(rel, module, resolved_sites)
            for resolved in resolved_sites:
                if resolved.site.kind in {
                    "binding",
                    "assignment",
                    "extends",
                    "implements",
                    "with",
                    "field_formal",
                    "super_formal",
                }:
                    continue
                self._site_record(rel, module, resolved, site_bindings)

    def _binding_sites(
        self, rel: str, module: str, sites: tuple[ResolvedSite, ...]
    ) -> list[tuple[Site, RawData]]:
        result: list[tuple[Site, RawData]] = []
        call_expressions = {
            item.site.expression for item in sites if item.site.kind in {"call", "creation"}
        }
        for resolved in sites:
            site = resolved.site
            if site.kind != "binding" or not site.assigned_name:
                continue
            scope, scope_id = self._scope(rel, module, site)
            name = site.assigned_name
            lexical_scope = (
                f"{scope}._closure_{site.scope_span.start_byte}"
                if site.closure_scope and site.scope_span is not None
                else scope
            )
            qualified = f"{lexical_scope}.{name}"
            if any(record["data"].get("qualified_name") == qualified for record in self.symbols):
                qualified = f"{scope}.$local{site.span.start_byte}.{name}"
            identity = stable_id("DARTBIND", rel, site.span.start_byte, scope_id or "", name)
            evidence_id = self._cite(rel, site.span)
            annotation = site.assignment_annotation
            raw_initializer = site.initializer
            initializer = site.initializer_source or raw_initializer
            if initializer and "=>" in initializer:
                initializer = None
            data = self._meta(
                rel,
                module,
                name,
                "binding",
                qualified,
                scope,
                scope_id,
                "private" if name.startswith("_") else "public",
            )
            data.update(
                symbol_category="dynamic_binding",
                annotation=annotation,
                initializer=None if raw_initializer in call_expressions else initializer,
                definition_contexts=[],
            )
            self._add_symbol(
                self._record(
                    identity,
                    "source",
                    "binding",
                    f"{qualified} declaration",
                    [qualified],
                    [evidence_id],
                    data,
                )
            )
            self.definition_names[(rel, site.span.start_byte)] = qualified
            self.definition_ids[(rel, site.span.line, site.span.column)] = identity
            result.append(
                (
                    site,
                    {
                        "id": identity,
                        "name": name,
                        "qualified_name": qualified,
                        "initializer": initializer,
                        "annotation": annotation,
                        "evidence_ids": [evidence_id],
                    },
                )
            )
        return result

    def _site_record(
        self,
        rel: str,
        module: str,
        resolved: ResolvedSite,
        site_bindings: list[tuple[Site, RawData]],
    ) -> None:
        site = resolved.site
        scope, scope_id = self._scope(rel, module, site)
        call = site.kind in {"call", "creation"}
        target_names, construction, status = self._site_target_state(rel, resolved, call)
        identity = stable_id(
            "DARTCALL" if call else "DARTREF",
            rel,
            site.span.start_byte,
            scope_id or "",
            site.expression,
            site.use if not call else "",
        )
        matching = [
            binding
            for binding_site, binding in site_bindings
            if binding_site.initializer == site.expression
            and binding_site.span.start_byte <= site.span.start_byte <= binding_site.span.end_byte
        ]
        if not call and site.use in {"read", "read_write", "value"}:
            for binding_site, binding in reversed(site_bindings):
                if (
                    binding_site.scope_span == site.scope_span
                    and binding_site.span.start_byte <= site.span.start_byte
                    and site.span.end_byte <= binding_site.span.end_byte
                ):
                    scope, scope_id = binding["qualified_name"], binding["id"]
                    break
        call_data: RawData = {
            "source_scope": scope,
            **({"source_definition_id": scope_id} if scope_id else {}),
            "source_module": module,
            "source_file": rel,
            "expression": site.expression_source or site.expression,
            "status": status,
            "targets": target_names if status != "unresolved" else [],
            "candidate_count": len(target_names),
            "candidates_truncated": False,
            "reason": (
                "Analyzer resolved the source element"
                if status == "resolved"
                else "multiple local source candidates remain"
                if status == "partially_resolved"
                else "target is external, dynamic, or unresolved"
            ),
        }
        if not call:
            call_data["use"] = "read" if site.use == "value" else site.use
        if construction is not None:
            call_data["construction"] = construction
        if matching:
            call_data["result_bindings"] = [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "target_kind": "name",
                    "annotation": item["annotation"],
                    "initializer": site.expression_source or site.expression,
                    "evidence_ids": item["evidence_ids"],
                    "definition_contexts": [],
                }
                for item in matching
            ]
        record = self._record(
            identity,
            "source",
            "call" if call else "reference",
            site.expression_source or site.expression,
            [scope],
            [self._cite(rel, site.span)],
            call_data,
        )
        (self.calls if call else self.references).append(record)

    def _site_target_state(
        self, rel: str, resolved: ResolvedSite, call: bool
    ) -> tuple[list[str], RawData | None, str]:
        site = resolved.site
        target_names = sorted(
            {name for item in resolved.bindings if (name := self._binding_name(item)) is not None}
        )
        enum_binding = next(
            (item for item in resolved.bindings if item.kind == "enum_member"), None
        )
        if not call and enum_binding is not None:
            enum_name = enum_binding.name.split(".", 1)[0]
            enum_type = f"{enum_binding.module}.{enum_name}"
            if self._symbol_kind(enum_type) == "class":
                target_names = [enum_type]
        constructor_binding = next(
            (
                item
                for item in resolved.bindings
                if item.kind in {"constructor", "implicit_constructor"}
            ),
            None,
        )
        construction_resolution = (
            self.resolver.resolve_construction(rel, site)
            if call and (site.kind == "creation" or constructor_binding is not None)
            else None
        )
        construction = (
            self._construction_record(construction_resolution) if construction_resolution else None
        )
        if construction_resolution and construction_resolution.binding:
            class_name = construction_resolution.binding.name.split(".", 1)[0]
            qualified_class = f"{construction_resolution.binding.module}.{class_name}"
            target_names = (
                [qualified_class] if self._symbol_kind(qualified_class) == "class" else []
            )
        if call and construction is None:
            target_names = [
                target
                for target in target_names
                if self._symbol_kind(target) in {"method", "function"}
            ]
        status = (
            "resolved"
            if len(target_names) == 1
            and (
                not call
                or construction is not None
                or self._symbol_kind(target_names[0]) in {"method", "function"}
            )
            else "unresolved"
        )
        if resolved.status != "resolved":
            status = "partially_resolved" if call and target_names else "unresolved"
        if construction is not None:
            status = "resolved" if construction["status"] != "unresolved" else "unresolved"
        return target_names, construction, status

    @staticmethod
    def _construction_record(
        resolution: ConstructionResolution,
    ) -> RawData:
        binding = resolution.binding
        class_name = binding.name.split(".", 1)[0] if binding else None
        target = f"{binding.module}.{class_name}" if binding and class_name else None
        if resolution.status == "resolved" and target:
            status = "resolved"
            targets = [target]
        elif binding is not None and target:
            status = "partially_resolved"
            targets = [target]
        else:
            status = "unresolved"
            targets = []
        if status == "resolved":
            reason = "Analyzer resolved a local generative constructor"
        elif status == "partially_resolved":
            reason = "factory construction does not prove a local instance target"
        else:
            reason = resolution.reason or "constructor target is external, dynamic, or unresolved"
        return {
            "status": status,
            "targets": targets,
            "candidates_truncated": False,
            "reason": reason,
        }

    def _scope(self, rel: str, module: str, site: Site) -> tuple[str, str | None]:
        name = site.scope
        candidates = [
            item
            for item in self.scope_candidates
            if item[0] == rel
            and item[5] <= site.span.start_byte < item[6]
            and (name is None or item[1] == name)
        ]
        if site.scope_span is not None:
            containing = [
                item
                for item in candidates
                if item[4].start_byte <= site.scope_span.start_byte <= item[4].end_byte
            ]
            if containing:
                _, _, qualified, identity, _, _, _ = max(
                    containing, key=lambda item: item[4].start_byte
                )
                return qualified, identity
            preceding = [
                item for item in candidates if item[4].start_byte <= site.scope_span.start_byte
            ]
            if preceding:
                _, _, qualified, identity, _, _, _ = max(
                    preceding, key=lambda item: item[4].start_byte
                )
                return qualified, identity
        containing = [
            item
            for item in candidates
            if item[4].start_byte <= site.span.start_byte <= item[4].end_byte
        ]
        if containing:
            _, _, qualified, identity, _, _, _ = max(
                containing, key=lambda item: item[4].start_byte
            )
            return qualified, identity
        if name is None:
            return module, None
        preceding = [item for item in candidates if item[4].start_byte <= site.span.start_byte]
        if preceding:
            _, _, qualified, identity, _, _, _ = max(preceding, key=lambda item: item[4].start_byte)
            return qualified, identity
        return module, None

    def _binding_name(self, binding: ResolvedBinding) -> str:
        key = (binding.rel_path, binding.span.start_byte)
        return self.definition_names.get(key, f"{binding.module}.{binding.name}")

    def _symbol_kind(self, qualified: str) -> str | None:
        record = self.symbol_by_name.get(qualified)
        return record["kind"] if record is not None else None

    def _duplicates(self) -> None:
        counts: Counter[str] = Counter()
        evidence: dict[str, set[str]] = {}
        for record in self.symbols:
            data = record["data"]
            qualified = data.get("qualified_name")
            if isinstance(qualified, str):
                counts[qualified] += 1
                evidence.setdefault(qualified, set()).update(record["evidence_ids"])
                for attribute in data.get("attribute_declarations", ()):
                    name = f"{qualified}.{attribute['name']}"
                    counts[name] += 1
                    evidence.setdefault(name, set()).update(attribute["evidence_ids"])
        for name, count in counts.items():
            if count > 1:
                ids = sorted(evidence[name])
                rel = self.evidence[ids[0]]["file"]
                self._gap(
                    rel, _file_span(), "DuplicateDeclaration", f"duplicate declaration {name}", ids
                )
        for record in self.symbols:
            data = record["data"]
            qualified = data.get("qualified_name")
            if isinstance(qualified, str) and counts[qualified] > 1:
                data["source_binding_unique"] = False
                if data.get("member_inventories") is not None:
                    self.incomplete_inventory_ids.add(record["id"])
            attrs = data.get("attribute_declarations")
            if attrs is not None and isinstance(qualified, str):
                if any(counts[f"{qualified}.{a['name']}"] > 1 for a in attrs):
                    self.incomplete_inventory_ids.add(record["id"])
                unique = [
                    a
                    for a in attrs
                    if counts[f"{qualified}.{a['name']}"] == 1 and counts[qualified] == 1
                ]
                data["attribute_declarations"] = unique
                inventories = data.get("member_inventories", ())
                if inventories:
                    inventories[0]["definition_ids"] = [a["definition_id"] for a in unique]

    def _finalize_inventories(self) -> None:
        for record in self.symbols:
            inventories = record["data"].get("member_inventories")
            if inventories is not None:
                if not self.sdk_supported:
                    record["data"].pop("member_inventories", None)
                    continue
                if (
                    record["id"] not in self.incomplete_inventory_ids
                    and record["data"].get("source_file") not in self.incomplete_inventory_paths
                ):
                    continue
                record["data"]["member_inventories"] = [
                    {
                        **dict(item),
                        "status": "partial",
                        "reason": "source contains unsupported or incomplete declarations",
                    }
                    for item in inventories
                ]

    def _files(self) -> list[FileFact]:
        result = []
        for rel in sorted(self.parsed):
            source = self.sources[rel]
            module = self.modules[rel]
            if module != source.module:
                continue
            excerpt = source.content.decode("utf-8", "replace").splitlines()
            evidence_id = file_evidence(self.evidence, rel, excerpt[:1])
            result.append(
                FileFact(
                    stable_id("FILE", module),
                    rel,
                    module,
                    module.rpartition(".")[0],
                    frozenset(),
                    False,
                    False,
                    frozenset(),
                    not source.content.strip(),
                    evidence_id,
                )
            )
        return result

    def _cite(self, rel: str, span: Span) -> str:
        return record_evidence(
            self.evidence, rel, (span.line, span.end_line, span.column), span.excerpt
        )

    def _gap(
        self, rel: str, span: Span, kind: str, message: str, evidence_ids: list[str] | None = None
    ) -> None:
        identity = stable_id("COVERAGE", rel, span.line, kind, message)
        if identity in self.gaps:
            return
        source = self.sources.get(rel)
        cited = (
            evidence_ids
            if evidence_ids is not None
            else (
                [self._cite(rel, span)]
                if source is not None and span.excerpt
                else [
                    file_evidence(
                        self.evidence,
                        rel,
                        source.content.decode("utf-8", "replace").splitlines()[:1],
                    )
                ]
                if source
                else []
            )
        )
        self.gaps[identity] = classified(
            item_id=identity,
            evidence_class=EvidenceClass.UNKNOWN,
            area="analysis_coverage",
            kind=kind,
            title=f"{rel}:{span.line} could not be analyzed: {message}",
            subjects=[f"{rel}:{span.line}"],
            evidence_ids=cited,
            data={"file": rel, "line": span.line, "message": message},
        )

    def _record(
        self,
        identity: str,
        area: str,
        kind: str,
        title: str,
        subjects: list[str],
        evidence_ids: list[str],
        data: RawData,
    ) -> RawRecord:
        return classified(
            item_id=identity,
            evidence_class=EvidenceClass.FACT,
            area=area,
            kind=kind,
            title=title,
            subjects=subjects,
            evidence_ids=evidence_ids,
            data=data,
        )


def _inventory(kind: str, definition_ids: list[str]) -> RawData:
    return {
        "schema_version": "1.0.0",
        "kind": kind,
        "status": "complete",
        "definition_ids": definition_ids,
        "reason": None,
    }


def _version(raw: str) -> tuple[int, int, int]:
    values = [int(item) for item in raw.split(".")]
    values.extend([0] * (3 - len(values)))
    return values[0], values[1], values[2]


def _constraint_floor(value: str) -> tuple[int, int, int] | None:
    version_pattern = r"(\d+(?:\.\d+){0,2})(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
    constraints = [
        (match.group(1), _version(match.group(2)))
        for match in re.finditer(rf"(\^|>=|>|<=|<|=)\s*{version_pattern}", value)
    ]
    lower: tuple[tuple[int, int, int], bool] | None = None
    upper: tuple[tuple[int, int, int], bool] | None = None
    for operator, version in constraints:
        if operator == "^":
            lower_candidate = (version, True)
            if version[0] > 0:
                upper_candidate = ((version[0] + 1, 0, 0), False)
            elif version[1] > 0:
                upper_candidate = ((0, version[1] + 1, 0), False)
            else:
                upper_candidate = ((0, 0, version[2] + 1), False)
            lower = _tighter_lower(lower, lower_candidate)
            upper = _tighter_upper(upper, upper_candidate)
        elif operator in {">=", ">", "="}:
            lower = _tighter_lower(lower, (version, operator != ">"))
            if operator == "=":
                upper = _tighter_upper(upper, (version, True))
        else:
            upper = _tighter_upper(upper, (version, operator == "<="))
    if lower is None:
        return None
    if upper is not None and (
        lower[0] > upper[0] or (lower[0] == upper[0] and not (lower[1] and upper[1]))
    ):
        return None
    return lower[0]


def _tighter_lower(
    current: tuple[tuple[int, int, int], bool] | None,
    candidate: tuple[tuple[int, int, int], bool],
) -> tuple[tuple[int, int, int], bool]:
    if current is None or candidate[0] > current[0]:
        return candidate
    if candidate[0] < current[0]:
        return current
    return current[0], current[1] and candidate[1]


def _tighter_upper(
    current: tuple[tuple[int, int, int], bool] | None,
    candidate: tuple[tuple[int, int, int], bool],
) -> tuple[tuple[int, int, int], bool]:
    if current is None or candidate[0] < current[0]:
        return candidate
    if candidate[0] > current[0]:
        return current
    return current[0], current[1] and candidate[1]


def _valid_constraint(value: str) -> bool:
    version = r"\d+(?:\.\d+){0,2}(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
    return (
        re.fullmatch(
            rf"\s*(?:\^\s*{version}|(?:>=|>|<=|<|=)\s*{version}(?:\s*,?\s*(?:>=|>|<=|<|=)\s*{version})*)\s*",
            value,
        )
        is not None
    )


def _file_span() -> Span:
    return Span(1, 1, 0, "", 0, 0)
