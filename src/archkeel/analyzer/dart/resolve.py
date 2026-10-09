# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Resolve Dart libraries and source bindings only inside a validated snapshot."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, replace
from typing import Literal
from urllib.parse import unquote, urlsplit

from archkeel.ir.facts import dart_module_name

from .parse import Definition, Directive, Member, Parameter, Site, Span, Syntax
from .snapshot import Snapshot, Source


@dataclass(frozen=True, slots=True)
class ResolutionProblem:
    path: str
    kind: str
    message: str
    span: Span | None = None


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    module: str
    package: str
    rel_path: str | None
    uri: str


@dataclass(frozen=True, slots=True)
class ResolvedBinding:
    module: str
    name: str
    kind: str
    via_prefix: str | None
    declaration_id: str
    rel_path: str
    span: Span


@dataclass(frozen=True, slots=True)
class ResolvedSite:
    site: Site
    status: Literal["resolved", "unknown", "unresolved"]
    bindings: tuple[ResolvedBinding, ...]


@dataclass(frozen=True, slots=True)
class ConstructionResolution:
    status: Literal["resolved", "unknown", "unresolved"]
    binding: ResolvedBinding | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class ResolvedParameter:
    name: str
    annotation: str | None
    kind: Literal["positional", "named"]
    default: str | None
    default_known: bool
    span: Span
    field_formal: bool = False


@dataclass(frozen=True, slots=True)
class ParameterResolution:
    parameters: tuple[ResolvedParameter, ...]
    problems: tuple[ResolutionProblem, ...]


@dataclass(frozen=True, slots=True)
class _Declaration:
    path: str
    module: str
    definition: Definition

    @property
    def identity(self) -> str:
        definition = self.definition
        return f"{self.path}:{definition.span.start_byte}:{definition.kind}:{definition.name}"


_PACKAGE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Resolver:
    """Bind names and URI targets using only snapshotted files and parsed syntax values."""

    def __init__(self, snapshot: Snapshot, syntax: dict[str, Syntax]) -> None:
        self.snapshot = snapshot
        self.syntax = syntax
        self.problems: list[ResolutionProblem] = []
        self.sources = snapshot.source_by_path
        self._module_paths: dict[str, list[str]] = {}
        for source in snapshot.sources:
            self._module_paths.setdefault(source.module, []).append(source.rel_path)
        self._invalid_parts: set[str] = set()
        self._invalid_libraries: set[str] = set()
        self._owners = self._find_part_owners()
        self._definitions = self._index_definitions()
        self._imports: dict[str, list[tuple[str, Directive]]] = {}
        self._exports: dict[str, list[tuple[str, Directive]]] = {}
        for path, parsed in syntax.items():
            module = self.module_for(path)
            if module is None:
                continue
            for directive in parsed.directives:
                if directive.kind not in {"import", "export"}:
                    continue
                destination = self._imports if directive.kind == "import" else self._exports
                destination.setdefault(module, []).append((path, directive))

    def module_for(self, rel_path: str) -> str | None:
        """Return a selected Dart library module; part files inherit their unique library owner."""
        source = self.sources.get(rel_path)
        if source is None or rel_path in self._invalid_parts:
            return None
        if rel_path in self._invalid_libraries:
            return None
        owner = self._owners.get(rel_path)
        parsed = self.syntax.get(rel_path)
        if (
            owner is None
            and parsed is not None
            and any(directive.kind == "part_of" for directive in parsed.directives)
        ):
            return None
        if owner is not None:
            module = self.sources[owner].module
            return module if len(self._module_paths.get(module, ())) == 1 else None
        return source.module if len(self._module_paths.get(source.module, ())) == 1 else None

    def resolve_uri(self, rel_path: str, uri: str) -> ResolvedTarget | None:
        """Resolve one literal URI; an internal result always names a selected regular source."""
        parsed = urlsplit(uri)
        if "\x00" in uri or "\\" in uri or parsed.query or parsed.fragment:
            self._problem(rel_path, "ImportError", f"unsupported URI {uri!r}")
            return None
        if parsed.scheme == "dart":
            path = unquote(parsed.path)
            module_name = _module_path(path)
            if module_name is None:
                self._problem(rel_path, "ImportError", f"unreadable URI {uri!r}")
                return None
            module = f"dart.{module_name}"
            return ResolvedTarget(module, "dart", None, uri)
        if parsed.scheme == "package":
            package, separator, raw_target = uri.removeprefix("package:").partition("/")
            target_path = unquote(raw_target)
            if (
                not separator
                or not _PACKAGE_NAME.fullmatch(package)
                or not target_path
                or target_path.startswith("/")
            ):
                self._problem(rel_path, "ImportError", f"unreadable URI {uri!r}")
                return None
            module_name = _module_path(target_path)
            if module_name is None:
                self._problem(rel_path, "ImportError", f"unreadable URI {uri!r}")
                return None
            if package != self.snapshot.package_name:
                return ResolvedTarget(f"{package}.{module_name}", package, None, uri)
            selected = self._source_at(posixpath.normpath(f"lib/{target_path}"), rel_path, uri)
            if selected is None:
                return None
            return ResolvedTarget(selected.module, package, selected.rel_path, uri)
        if parsed.scheme:
            self._problem(rel_path, "ImportError", f"unsupported URI scheme in {uri!r}")
            return None
        target_path = unquote(parsed.path)
        if target_path.startswith("/"):
            self._problem(rel_path, "ImportError", f"absolute URI {uri!r} is unsupported")
            return None
        importer = self.sources.get(rel_path)
        if importer is None:
            self._problem(rel_path, "ImportError", "importer is not in the selected snapshot")
            return None
        joined = posixpath.normpath(posixpath.join(posixpath.dirname(rel_path), target_path))
        if not self._in_roots(joined):
            self._problem(
                rel_path, "ImportError", f"relative URI {uri!r} leaves the selected roots"
            )
            return None
        selected = self._source_at(joined, rel_path, uri)
        if selected is None:
            return None
        return ResolvedTarget(selected.module, self.snapshot.package_name, selected.rel_path, uri)

    def resolve_directive(self, rel_path: str, directive: Directive) -> tuple[ResolvedTarget, ...]:
        """Resolve the literal and every conditional URI without selecting an environment."""
        uris = tuple(dict.fromkeys((directive.target, *(uri for _, uri in directive.alternatives))))
        targets: list[ResolvedTarget] = []
        for uri in uris:
            if uri is None:
                self._problem(
                    rel_path,
                    "ImportError",
                    "directive URI is not a supported string",
                    directive.span,
                )
                continue
            target = self.resolve_uri(rel_path, uri)
            if target is None:
                # The lower-level issue already identifies the importing source.
                continue
            if all(
                (item.module, item.rel_path) != (target.module, target.rel_path) for item in targets
            ):
                if target.rel_path in self._owners:
                    self._problem(
                        rel_path,
                        "ImportError",
                        f"URI {uri!r} names a part, not a library",
                        directive.span,
                    )
                    continue
                targets.append(target)
        return tuple(targets)

    def resolve_name(self, rel_path: str, name: str) -> tuple[str, ...]:
        """Return uniquely source-addressable qualified declarations visible to one source file."""
        module = self.module_for(rel_path)
        if module is None:
            return ()
        declarations = self._local_declarations(module, name)
        if declarations:
            return tuple(sorted(f"{item.module}.{item.definition.name}" for item in declarations))
        bindings = self._imported_bindings(module, name, prefix=None)
        return tuple(sorted(f"{item.module}.{item.name}" for item in bindings))

    def resolved_sites(self, rel_path: str) -> tuple[ResolvedSite, ...]:
        """Resolve each site locally; unresolved names never inherit a global guess."""
        parsed = self.syntax.get(rel_path)
        if parsed is None:
            return ()
        resolved: list[ResolvedSite] = []
        for site in parsed.sites:
            if site.kind == "reference" and site.use == "read_write":
                resolved.append(self._resolve_site(rel_path, replace(site, use="read")))
                resolved.append(self._resolve_site(rel_path, replace(site, use="write")))
            else:
                resolved.append(self._resolve_site(rel_path, site))
        return tuple(resolved)

    def resolve_construction(self, rel_path: str, site: Site) -> ConstructionResolution:
        """Prove a constructor only from its owning class and a declared or implicit default."""
        if site.kind not in {"call", "creation"} or not site.name:
            return ConstructionResolution("unresolved", None, "site is not a constructor form")
        module = self.module_for(rel_path)
        if module is None:
            return ConstructionResolution("unknown", None, "source has no unique library owner")
        resolved_type = self._construction_type(rel_path, module, site)
        if resolved_type is None:
            return ConstructionResolution("unknown", None, "constructor type is not a simple name")
        class_name, constructor_name, classes = resolved_type
        if len(classes) != 1:
            return ConstructionResolution(
                "unknown" if classes else "unresolved",
                None,
                "constructor type is ambiguous" if classes else "no source class binding",
            )
        binding = classes[0]
        declaration = next(
            (
                item
                for item in self._definitions.get(binding.module, ())
                if item.identity == binding.declaration_id
            ),
            None,
        )
        if declaration is None:
            return ConstructionResolution("unknown", None, "class declaration is incomplete")
        parsed = self.syntax.get(declaration.path)
        if parsed is None or not parsed.complete:
            return ConstructionResolution("unknown", None, "class source is incomplete")
        result = self._declared_constructor(declaration, binding, class_name, constructor_name)
        if (
            result.binding is not None
            and result.binding.name.rpartition(".")[2].startswith("_")
            and declaration.module != module
        ):
            return ConstructionResolution("unknown", None, "private constructor is library-local")
        return result

    def _construction_type(
        self, rel_path: str, module: str, site: Site
    ) -> tuple[str, str | None, list[ResolvedBinding]] | None:
        if site.name is None:
            return None
        constructor_name: str | None = None
        prefix: str | None = None
        prefixed_classes: tuple[ResolvedBinding, ...] = ()
        if site.kind == "creation" or site.receiver is None:
            parts = site.name.split(".")
            class_name = _type_name(parts[0])
            constructor_name = parts[1] if len(parts) > 1 else None
        else:
            prefixed_classes = tuple(
                item
                for item in self._imported_bindings(module, site.name, prefix=site.receiver)
                if item.kind in {"class", "interface", "enum", "mixin"}
            )
            receiver = site.receiver.split(".")
            if prefixed_classes:
                prefix = site.receiver
                class_name = _type_name(site.name)
            elif len(receiver) > 1:
                prefix, class_name = receiver[0], receiver[-1]
                constructor_name = site.name
            else:
                class_name = receiver[0]
                constructor_name = site.name
        if class_name is None:
            return None
        if site.kind == "call" and site.receiver is None:
            candidates = list(self._name_bindings(rel_path, module, class_name, None))
        elif prefix is not None:
            candidates = list(
                prefixed_classes
                if prefixed_classes
                else self._imported_bindings(module, class_name, prefix=prefix)
            )
        else:
            candidates = list(self._name_bindings(rel_path, module, class_name, None))
        classes = [
            binding
            for binding in candidates
            if binding.kind in {"class", "interface", "enum", "mixin"}
        ]
        return class_name, constructor_name, classes

    def _declared_constructor(
        self,
        declaration: _Declaration,
        binding: ResolvedBinding,
        class_name: str,
        requested: str | None,
    ) -> ConstructionResolution:
        constructors = [
            item for item in declaration.definition.members if item.kind == "constructor"
        ]
        if requested is None:
            matches = [
                member for member in constructors if member.name in {class_name, f"{class_name}."}
            ]
            if not constructors:
                if "abstract" in declaration.definition.modifiers:
                    return ConstructionResolution(
                        "unresolved", None, "abstract class has no constructible default"
                    )
                implicit = ResolvedBinding(
                    declaration.module,
                    class_name,
                    "implicit_constructor",
                    binding.via_prefix,
                    f"{declaration.identity}:implicit-constructor",
                    declaration.path,
                    declaration.definition.span,
                )
                return ConstructionResolution("resolved", implicit, None)
        else:
            matches = [
                member
                for member in constructors
                if member.name in {requested, f"{class_name}.{requested}"}
            ]
        if len(matches) != 1:
            return ConstructionResolution(
                "unknown" if len(matches) > 1 else "unresolved",
                None,
                "constructor declaration is ambiguous"
                if len(matches) > 1
                else "constructor is not declared",
            )
        member = matches[0]
        if "abstract" in declaration.definition.modifiers and not member.factory:
            return ConstructionResolution(
                "unresolved", None, "abstract class has no constructible generative constructor"
            )
        resolved = ResolvedBinding(
            declaration.module,
            f"{class_name}.{member.name.rpartition('.')[-1]}",
            "constructor",
            binding.via_prefix,
            f"{declaration.identity}:{member.span.start_byte}:constructor:{member.name}",
            declaration.path,
            member.span,
        )
        if member.factory:
            return ConstructionResolution(
                "unknown", resolved, "factory result is not source-proven"
            )
        return ConstructionResolution("resolved", resolved, None)

    def resolve_parameters(
        self, rel_path: str, definition: Definition, member: Member
    ) -> ParameterResolution:
        """Resolve constructor formals that inherit source facts through a known redirect."""
        declaration = self._declaration_for(rel_path, definition)
        if declaration is None:
            return self._parameter_failure(
                rel_path,
                member.parameters,
                "source_resolution_gap",
                "constructor owner is unresolved",
            )
        if member.factory and member.redirect:
            return self._redirect_parameters(rel_path, declaration, member)
        resolved: list[ResolvedParameter] = []
        problems: list[ResolutionProblem] = []
        for parameter in member.parameters:
            value, problem = self._resolve_formal(rel_path, declaration, parameter, {}, frozenset())
            resolved.append(value)
            if problem is not None:
                problems.append(problem)
        return ParameterResolution(tuple(resolved), tuple(problems))

    def _resolve_formal(
        self,
        rel_path: str,
        declaration: _Declaration,
        parameter: Parameter,
        substitutions: dict[str, str],
        seen: frozenset[str],
        known_type_parameters: frozenset[str] = frozenset(),
    ) -> tuple[ResolvedParameter, ResolutionProblem | None]:
        if parameter.super_formal:
            if declaration.identity in seen:
                return self._parameter_unknown(parameter), self._parameter_problem(
                    rel_path,
                    parameter,
                    "UnsupportedParameter",
                    "super-formal chain contains a cycle",
                )
            parent = self._parent_declaration(declaration)
            if parent is None:
                return self._parameter_unknown(parameter), self._parameter_problem(
                    rel_path, parameter, "source_resolution_gap", "superclass source is unresolved"
                )
            parent_declaration, parent_substitutions = parent
            inherited = self._super_parameter(parent_declaration, parameter.name)
            if inherited is None:
                return self._parameter_unknown(parameter), self._parameter_problem(
                    rel_path, parameter, "UnsupportedParameter", "superclass formal is not proven"
                )
            _, source_parameter = inherited
            value, issue = self._resolve_formal(
                parent_declaration.path,
                parent_declaration,
                source_parameter,
                parent_substitutions,
                seen | {declaration.identity},
                known_type_parameters,
            )
            if issue is not None:
                return self._parameter_unknown(parameter), self._parameter_problem(
                    rel_path, parameter, issue.kind, issue.message
                )
            annotation = _substitute_type(value.annotation, parent_substitutions)
            if annotation is None or not self._type_is_proven(
                rel_path,
                annotation,
                parent_declaration.module,
                parent_declaration.definition,
                known_type_parameters,
            ):
                return self._parameter_unknown(parameter), self._parameter_problem(
                    rel_path,
                    parameter,
                    "UnsupportedParameter",
                    "inherited formal type is unresolved",
                )
            return self._parameter_value(
                parameter, annotation, value.default, value.default_known
            ), None
        annotation = _substitute_type(parameter.annotation, substitutions)
        if parameter.field_formal and annotation is None:
            annotation = self._field_annotation(declaration.definition, parameter.name)
            annotation = _substitute_type(annotation, substitutions)
            if annotation is None:
                return self._parameter_unknown(parameter), self._parameter_problem(
                    rel_path,
                    parameter,
                    "UnsupportedParameter",
                    "field-formal parameter type is unavailable",
                )
        return self._parameter_value(
            parameter, annotation, parameter.default, parameter.default_known
        ), None

    def _redirect_parameters(
        self, rel_path: str, owner: _Declaration, factory: Member
    ) -> ParameterResolution:
        terminal = self._redirect_terminal(rel_path, owner, factory)
        if terminal is None:
            return self._parameter_failure(
                rel_path, factory.parameters, "UnsupportedParameter", "factory redirect is unproven"
            )
        target_class, target_member, substitutions = terminal
        result: list[ResolvedParameter] = []
        problems: list[ResolutionProblem] = []
        for index, parameter in enumerate(factory.parameters):
            target = self._matching_parameter(target_member.parameters, parameter, index)
            if target is None:
                result.append(self._parameter_unknown(parameter))
                problems.append(
                    self._parameter_problem(
                        rel_path,
                        parameter,
                        "UnsupportedParameter",
                        "redirected formal does not match",
                    )
                )
                continue
            resolved, issue = self._resolve_formal(
                target_class.path,
                target_class,
                target,
                substitutions,
                frozenset(),
                frozenset(owner.definition.type_parameters),
            )
            annotation = _substitute_type(resolved.annotation, substitutions)
            declared = _substitute_type(parameter.annotation, {})
            if issue is not None or (
                declared and annotation and _type_key(declared) != _type_key(annotation)
            ):
                result.append(self._parameter_unknown(parameter, declared))
                problems.append(
                    self._parameter_problem(
                        rel_path,
                        parameter,
                        "UnsupportedParameter",
                        issue.message if issue else "redirected formal type does not match",
                    )
                )
                continue
            result.append(
                self._parameter_value(
                    parameter, declared or annotation, resolved.default, resolved.default_known
                )
            )
        return ParameterResolution(tuple(result), tuple(problems))

    def _redirect_terminal(
        self, rel_path: str, owner: _Declaration, factory: Member
    ) -> tuple[_Declaration, Member, dict[str, str]] | None:
        target_type = factory.redirect
        visited: set[str] = {f"{owner.identity}:{factory.span.start_byte}"}
        while target_type:
            resolved = self._class_for_type(rel_path, owner.module, target_type)
            if resolved is None:
                return None
            target, substitutions, requested = resolved
            constructors = [
                item for item in target.definition.members if item.kind == "constructor"
            ]
            candidates = [
                item
                for item in constructors
                if (item.name.rpartition(".")[-1] if "." in item.name else None) == requested
            ]
            if requested is None:
                candidates = [
                    item for item in constructors if item.name in {target.definition.name, ""}
                ]
            if len(candidates) != 1:
                return None
            next_member = candidates[0]
            identity = f"{target.identity}:{next_member.span.start_byte}"
            if identity in visited:
                return None
            visited.add(identity)
            if not next_member.factory:
                return target, next_member, substitutions
            if not next_member.redirect:
                if any(
                    item.optional or item.default is not None for item in next_member.parameters
                ):
                    return None
                return target, next_member, substitutions
            owner = target
            target_type = next_member.redirect
        return None

    def _class_for_type(
        self, rel_path: str, module: str, type_text: str
    ) -> tuple[_Declaration, dict[str, str], str | None] | None:
        raw = type_text.strip()
        type_head = raw.split("<", 1)[0]
        parts = type_head.split(".")
        name = parts[0] if parts else None
        if name is None:
            return None
        constructor_name: str | None = None
        prefix: str | None = None
        if len(parts) > 1:
            local = self._local_declarations(module, parts[0])
            local_classes = [
                item
                for item in local
                if item.definition.kind in {"class", "interface", "enum", "mixin"}
            ]
            if len(local_classes) == 1:
                name = parts[0]
                constructor_name = parts[1] if len(parts) > 1 else None
            elif len(parts) in {2, 3}:
                prefix, name = parts[:2]
                if len(parts) == 3:
                    constructor_name = parts[2]
            else:
                return None
        bindings = (
            self._imported_bindings(module, name, prefix=prefix)
            if prefix
            else self._name_bindings(rel_path, module, name, None)
        )
        classes = [
            item for item in bindings if item.kind in {"class", "interface", "enum", "mixin"}
        ]
        if len({item.declaration_id for item in classes}) != 1:
            return None
        binding = classes[0]
        declaration = next(
            (
                item
                for item in self._definitions.get(binding.module, ())
                if item.identity == binding.declaration_id
            ),
            None,
        )
        if declaration is None:
            return None
        arguments = raw.partition("<")[2].rpartition(">")[0]
        actuals = _split_types(arguments) if arguments else []
        substitutions = dict(zip(declaration.definition.type_parameters, actuals, strict=False))
        return declaration, substitutions, constructor_name

    def _parent_declaration(
        self, declaration: _Declaration
    ) -> tuple[_Declaration, dict[str, str]] | None:
        parents = declaration.definition.extends
        if not parents:
            return None
        resolved = self._class_for_type(declaration.path, declaration.module, parents[0])
        if resolved is None:
            return None
        parent, substitutions, _ = resolved
        return parent, substitutions

    @staticmethod
    def _super_parameter(declaration: _Declaration, name: str) -> tuple[Member, Parameter] | None:
        matches = [
            (member, parameter)
            for member in declaration.definition.members
            if member.kind == "constructor"
            for parameter in member.parameters
            if parameter.name == name
        ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _matching_parameter(
        values: tuple[Parameter, ...], parameter: Parameter, index: int
    ) -> Parameter | None:
        if parameter.kind == "named":
            matches = [
                item for item in values if item.kind == "named" and item.name == parameter.name
            ]
            return matches[0] if len(matches) == 1 else None
        positional = [item for item in values if item.kind == "positional"]
        return positional[index] if index < len(positional) else None

    @staticmethod
    def _field_annotation(definition: Definition, name: str) -> str | None:
        fields = [
            item.annotation
            for item in definition.members
            if item.kind == "field" and item.name == name
        ]
        return fields[0] if len(fields) == 1 else None

    def _type_is_proven(
        self,
        rel_path: str,
        annotation: str,
        module: str,
        definition: Definition,
        known_type_parameters: frozenset[str] = frozenset(),
    ) -> bool:
        builtins = {
            "String",
            "int",
            "double",
            "num",
            "bool",
            "Object",
            "dynamic",
            "void",
            "Never",
            "Null",
            "Function",
            "List",
            "Map",
            "Set",
            "Iterable",
            "Future",
            "FutureOr",
            "Stream",
            "Record",
        }
        names = re.findall(r"[A-Za-z_$][A-Za-z0-9_$]*", annotation)
        allowed = builtins | set(definition.type_parameters) | set(known_type_parameters)
        for name in names:
            if name in allowed:
                continue
            if not self._name_bindings(rel_path, module, name, None):
                return False
        return bool(names)

    @staticmethod
    def _parameter_value(
        parameter: Parameter, annotation: str | None, default: str | None, known: bool
    ) -> ResolvedParameter:
        if default is None and known and parameter.optional:
            default = "null"
        return ResolvedParameter(
            parameter.name,
            annotation,
            parameter.kind,
            default,
            known,
            parameter.span,
            parameter.field_formal,
        )

    @staticmethod
    def _parameter_unknown(
        parameter: Parameter, annotation: str | None = None
    ) -> ResolvedParameter:
        return ResolvedParameter(
            parameter.name,
            annotation or parameter.annotation,
            parameter.kind,
            None,
            False,
            parameter.span,
            parameter.field_formal,
        )

    @staticmethod
    def _parameter_problem(
        path: str, parameter: Parameter, kind: str, message: str
    ) -> ResolutionProblem:
        return ResolutionProblem(path, kind, message, parameter.span)

    def _parameter_failure(
        self, path: str, parameters: tuple[Parameter, ...], kind: str, message: str
    ) -> ParameterResolution:
        return ParameterResolution(
            tuple(self._parameter_unknown(item) for item in parameters),
            tuple(self._parameter_problem(path, item, kind, message) for item in parameters),
        )

    def _declaration_for(self, rel_path: str, definition: Definition) -> _Declaration | None:
        module = self.module_for(rel_path)
        if module is None:
            return None
        return next(
            (
                item
                for item in self._definitions.get(module, ())
                if item.definition.span.start_byte == definition.span.start_byte
                and item.path == rel_path
            ),
            None,
        )

    def _resolve_site(self, rel_path: str, site: Site) -> ResolvedSite:
        module = self.module_for(rel_path)
        if module is None or not site.name:
            return ResolvedSite(site, "unknown", ())
        if site.receiver and site.receiver.split(".", 1)[0] in site.shadowed_names:
            return ResolvedSite(site, "unknown", ())
        if site.name in site.shadowed_names and site.receiver is None:
            return ResolvedSite(site, "unknown", ())
        if self._conditional_site_uncertain(module, site):
            return ResolvedSite(site, "unknown", ())
        if (
            site.kind == "call"
            and site.receiver is None
            and self._has_lexical_binding(rel_path, site, site.name)
        ):
            return ResolvedSite(site, "unknown", ())
        if site.kind == "creation":
            return self._construction_site(rel_path, site)
        if site.kind in {"extends", "implements", "with", "type"}:
            name = _type_name(site.name or "") or site.name
            bindings = self._name_bindings(rel_path, module, name, site.receiver)
            return self._site_result(site, bindings, module)
        if site.kind == "reference" and site.receiver is None:
            lexical = self._lexical_bindings(rel_path, site, site.name)
            if lexical:
                return self._site_result(site, lexical, module)
        if site.receiver:
            receiver_name = site.receiver.split(".", 1)[0]
            if site.kind == "call" and not self._has_lexical_binding(rel_path, site, receiver_name):
                construction = self.resolve_construction(rel_path, site)
                if construction.binding is not None:
                    return self._construction_result(site, construction)
            bindings = self._receiver_bindings(rel_path, module, site)
            if site.kind == "call" and bindings:
                return self._site_result(site, bindings, module)
            if not bindings:
                prefix = site.receiver.rpartition(".")[2]
                shadowed = self._has_lexical_binding(rel_path, site, site.receiver.split(".", 1)[0])
                status: Literal["unknown", "unresolved"] = "unresolved"
                if shadowed or not (
                    self._has_import_prefix(module, prefix)
                    or self._is_filtered_import_name(module, site.receiver)
                ):
                    status = "unknown"
                return ResolvedSite(site, status, ())
            return self._site_result(site, bindings, module)
        bindings = self._name_bindings(rel_path, module, site.name, None)
        if not bindings:
            owner = self._enclosing_class(rel_path, site)
            if owner is not None:
                bindings = self._site_members(site, self._member_bindings(module, owner, site.name))
        bindings = self._site_members(site, bindings)
        if site.kind == "call":
            class_bindings = [
                item for item in bindings if item.kind in {"class", "interface", "enum", "mixin"}
            ]
            if class_bindings:
                return self._construction_site(rel_path, site)
        return self._site_result(site, bindings, module)

    def _has_import_prefix(self, module: str, prefix: str) -> bool:
        return any(directive.prefix == prefix for _, directive in self._imports.get(module, ()))

    def _conditional_site_uncertain(self, module: str, site: Site) -> bool:
        if site.receiver is None:
            return self._conditional_import_uncertain(module, site.name or "", None)
        parts = site.receiver.split(".")
        prefix = parts[0]
        if not self._has_import_prefix(module, prefix):
            return False
        symbol = site.name if len(parts) == 1 else parts[-1]
        return self._conditional_import_uncertain(module, symbol or "", prefix)

    def _conditional_import_uncertain(self, module: str, name: str, prefix: str | None) -> bool:
        for path, directive in self._imports.get(module, ()):
            if directive.prefix != prefix or not directive.alternatives:
                continue
            if not self._visible(directive, name):
                continue
            targets = self.resolve_directive(path, directive)
            if len(targets) < 2:
                return True
            branches: list[frozenset[tuple[str, str, str]]] = []
            for target in targets:
                if target.rel_path is None:
                    branches.append(frozenset())
                else:
                    branches.append(
                        frozenset(
                            (item.module, item.name, item.kind)
                            for item in self._exported_bindings(target.rel_path, name, set(), None)
                        )
                    )
            if any(not branch for branch in branches) or any(
                branch != branches[0] for branch in branches[1:]
            ):
                return True
        return False

    def _is_filtered_import_name(self, module: str, name: str) -> bool:
        for path, directive in self._imports.get(module, ()):
            if directive.prefix is not None:
                continue
            for target in self.resolve_directive(path, directive):
                if target.rel_path is None or self._visible(directive, name):
                    continue
                if self._local_declarations(target.module, name):
                    return True
        return False

    def _construction_site(self, rel_path: str, site: Site) -> ResolvedSite:
        return self._construction_result(site, self.resolve_construction(rel_path, site))

    @staticmethod
    def _construction_result(site: Site, construction: ConstructionResolution) -> ResolvedSite:
        bindings = (construction.binding,) if construction.binding is not None else ()
        return ResolvedSite(site, construction.status, bindings)

    def _site_result(
        self, site: Site, bindings: tuple[ResolvedBinding, ...], requester_module: str
    ) -> ResolvedSite:
        accessible = tuple(
            item
            for item in bindings
            if not item.name.rpartition(".")[2].startswith("_") or item.module == requester_module
        )
        if len({item.declaration_id for item in accessible}) == 1 and accessible:
            return ResolvedSite(site, "resolved", accessible)
        if not accessible and bindings:
            return ResolvedSite(site, "unknown", ())
        return ResolvedSite(site, "unknown" if accessible else "unresolved", accessible)

    def _name_bindings(
        self, rel_path: str, module: str, name: str, receiver: str | None
    ) -> tuple[ResolvedBinding, ...]:
        if receiver is None:
            local = self._local_declarations(module, name)
            if local:
                return tuple(self._binding(item, None) for item in local)
            return self._imported_bindings(module, name, prefix=None)
        prefix = receiver.rpartition(".")[2]
        imports = self._imported_bindings(module, name, prefix=prefix)
        if imports:
            return imports
        local_types = self._local_declarations(module, receiver)
        if any(item.definition.kind in {"class", "enum", "mixin"} for item in local_types):
            static = self._member_bindings(module, receiver, name, static_only=True)
            return static or self._constructor_bindings(module, receiver, name)
        owner = self._receiver_type(rel_path, receiver, None)
        if owner is None:
            return ()
        return self._member_bindings(owner.module, owner.name, name)

    def _receiver_bindings(
        self, rel_path: str, module: str, site: Site
    ) -> tuple[ResolvedBinding, ...]:
        receiver = site.receiver or ""
        if site.computed or receiver.endswith("]"):
            return ()
        if receiver.split(".", 1)[0] in site.shadowed_names:
            return ()
        if receiver.endswith(")"):
            constructed = self._constructed_receiver_bindings(rel_path, module, site, receiver)
            if constructed:
                return constructed
        if receiver in {"this", "super"}:
            owner = self._enclosing_class(rel_path, site)
            if owner and receiver == "super":
                return self._site_members(
                    site, self._inherited_member_bindings(module, owner, site.name or "")
                )
            if owner:
                return self._site_members(
                    site, self._member_bindings(module, owner, site.name or "")
                )
            return ()
        receiver_parts = receiver.split(".")
        lexically_bound = self._has_lexical_binding(rel_path, site, receiver_parts[0])
        if lexically_bound:
            type_binding = self._receiver_type(rel_path, receiver_parts[0], site)
            return (
                self._site_members(
                    site,
                    self._member_bindings(type_binding.module, type_binding.name, site.name or ""),
                )
                if type_binding
                else ()
            )
        if len(receiver_parts) == 2:
            imported_types = [
                item
                for item in self._imported_bindings(
                    module, receiver_parts[1], prefix=receiver_parts[0]
                )
                if item.kind in {"class", "interface", "enum", "mixin"}
            ]
            if len({item.declaration_id for item in imported_types}) == 1:
                type_binding = imported_types[0]
                return self._site_members(
                    site,
                    self._member_bindings(
                        type_binding.module, type_binding.name, site.name or "", static_only=True
                    ),
                )
        prefix = receiver.rpartition(".")[2]
        imports = self._imported_bindings(module, site.name or "", prefix=prefix)
        if imports:
            return imports
        local_types = self._local_declarations(module, receiver)
        if any(item.definition.kind in {"class", "enum", "mixin"} for item in local_types):
            name = site.name or ""
            static = self._member_bindings(module, receiver, name, static_only=True)
            return self._site_members(
                site, static or self._constructor_bindings(module, receiver, name)
            )
        resolved_owner = self._receiver_type(rel_path, receiver, site)
        return (
            self._site_members(
                site,
                self._member_bindings(resolved_owner.module, resolved_owner.name, site.name or ""),
            )
            if resolved_owner
            else ()
        )

    def _constructed_receiver_bindings(
        self, rel_path: str, module: str, site: Site, receiver: str
    ) -> tuple[ResolvedBinding, ...]:
        parsed = self.syntax.get(rel_path)
        receiver_site = (
            next(
                (
                    item
                    for item in parsed.sites
                    if item.kind == "call" and item.expression == receiver
                ),
                None,
            )
            if parsed is not None
            else None
        )
        if receiver_site is None:
            return ()
        resolved_type = self._construction_type(rel_path, module, receiver_site)
        if resolved_type is None:
            return ()
        members: list[ResolvedBinding] = []
        for candidate in resolved_type[2]:
            declaration = next(
                (
                    item
                    for item in self._definitions.get(candidate.module, ())
                    if item.identity == candidate.declaration_id
                ),
                None,
            )
            if declaration is None:
                continue
            members.extend(
                ResolvedBinding(
                    declaration.module,
                    f"{declaration.definition.name}.{member.name}",
                    member.kind,
                    candidate.via_prefix,
                    f"{declaration.identity}:{member.span.start_byte}:{member.kind}:{member.name}",
                    declaration.path,
                    member.span,
                )
                for member in declaration.definition.members
                if member.name == site.name
            )
        return tuple(members)

    @staticmethod
    def _site_members(
        site: Site, bindings: tuple[ResolvedBinding, ...]
    ) -> tuple[ResolvedBinding, ...]:
        if site.use == "read":
            return tuple(item for item in bindings if item.kind != "setter")
        if site.use == "write":
            return tuple(item for item in bindings if item.kind != "getter")
        return bindings

    def _enclosing_class(self, rel_path: str, site: Site | None) -> str | None:
        parsed = self.syntax.get(rel_path)
        if parsed is None:
            return None
        position = site.span.start_byte if site is not None else -1
        if position < 0:
            return None
        candidates = [
            definition
            for definition in parsed.definitions
            if definition.kind in {"class", "mixin", "enum", "extension", "extension_type"}
            and definition.span.start_byte <= position <= definition.span.end_byte
        ]
        return (
            min(candidates, key=lambda item: item.span.end_byte - item.span.start_byte).name
            if candidates
            else None
        )

    def _receiver_type(
        self, rel_path: str, receiver: str, use_site: Site | None
    ) -> ResolvedBinding | None:
        parsed = self.syntax.get(rel_path)
        module = self.module_for(rel_path)
        if parsed is None or module is None:
            return None
        match = re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", receiver)
        if match is None:
            return None
        annotation = self._receiver_annotation(rel_path, parsed, receiver, use_site)
        type_text = (annotation or "").split("<", 1)[0].strip().rstrip("?")
        type_parts = type_text.split(".")
        type_name = type_parts[-1] if type_parts else None
        if type_name is None or type_name in {"dynamic", "Object", "void"}:
            return None
        bindings = (
            self._imported_bindings(module, type_name, prefix=type_parts[0])
            if len(type_parts) > 1
            else self._name_bindings(rel_path, module, type_name, None)
        )
        classes = [
            item for item in bindings if item.kind in {"class", "interface", "enum", "mixin"}
        ]
        return classes[0] if len({item.declaration_id for item in classes}) == 1 else None

    def _receiver_annotation(
        self, rel_path: str, parsed: Syntax, receiver: str, use_site: Site | None
    ) -> str | None:
        visible = [
            binding
            for binding in parsed.sites
            if binding.kind == "binding"
            and (binding.assigned_name or binding.name) == receiver
            and binding.scope_span is not None
            and (use_site is None or binding.span.start_byte < use_site.span.start_byte)
            and (
                use_site is None
                or binding.scope_span is None
                or binding.scope_span.start_byte
                <= use_site.span.start_byte
                <= binding.scope_span.end_byte
            )
        ]
        if visible:
            chosen = max(visible, key=lambda item: (item.scope_depth, item.span.start_byte))
            annotation = chosen.assignment_annotation
            if annotation is None and chosen.initializer:
                annotation = self._inferred_constructor_type(rel_path, parsed, chosen)
            if annotation is None and use_site is not None:
                annotation = self._callback_parameter_annotation(rel_path, parsed, chosen)
            return annotation
        return self._declared_receiver_annotation(parsed, receiver, use_site)

    def _callback_parameter_annotation(
        self,
        rel_path: str,
        parsed: Syntax,
        binding: Site,
    ) -> str | None:
        if binding.scope_span is None:
            return None
        calls = [
            item
            for item in parsed.sites
            if item.kind == "call"
            and item.name == "fold"
            and item.receiver
            and item.span.start_byte <= binding.scope_span.start_byte
            and binding.scope_span.end_byte <= item.span.end_byte
            and len(item.arguments) == 2
        ]
        if len(calls) != 1:
            return None
        siblings = sorted(
            (
                item
                for item in parsed.sites
                if item.kind == "binding"
                and item.scope_span is not None
                and item.scope_span.start_byte == binding.scope_span.start_byte
                and item.scope_span.end_byte == binding.scope_span.end_byte
            ),
            key=lambda item: item.span.start_byte,
        )
        if len(siblings) != 2 or siblings[1] is not binding:
            return None
        call = calls[0]
        collection_type = self._receiver_annotation(rel_path, parsed, call.receiver or "", call)
        if not collection_type:
            return None
        collection_name, _, arguments = collection_type.partition("<")
        if collection_name.strip() not in {"List", "Iterable"} or not arguments.endswith(">"):
            return None
        if self._local_declarations(self.module_for(rel_path) or "", collection_name.strip()):
            return None
        if self._imported_bindings(
            self.module_for(rel_path) or "", collection_name.strip(), prefix=None
        ):
            return None
        element_type = arguments[:-1].strip()
        if not element_type or element_type in {"dynamic", "Object?"}:
            return None
        return element_type

    def _inferred_constructor_type(
        self, rel_path: str, parsed: Syntax, binding: Site
    ) -> str | None:
        initializer = binding.initializer
        if initializer is None:
            return None
        candidates = [
            item
            for item in parsed.sites
            if item.kind == "call"
            and item.expression == initializer
            and binding.span.start_byte <= item.span.start_byte
            and item.span.end_byte <= binding.span.end_byte
        ]
        if len(candidates) != 1:
            return None
        site = candidates[0]
        if site.name is not None and self._has_lexical_binding(rel_path, site, site.name):
            return None
        resolution = self.resolve_construction(rel_path, site)
        if resolution.status != "resolved" or resolution.binding is None:
            return None
        return resolution.binding.name.split(".", 1)[0]

    def _has_lexical_binding(self, rel_path: str, site: Site, name: str) -> bool:
        parsed = self.syntax.get(rel_path)
        if parsed is None:
            return False
        if any(
            item.kind == "binding"
            and (item.assigned_name or item.name) == name
            and item.span.start_byte <= site.span.start_byte
            and item.scope_span is not None
            and item.scope_span.start_byte <= site.span.start_byte <= item.scope_span.end_byte
            for item in parsed.sites
        ):
            return True
        for definition in parsed.definitions:
            if definition.name == site.scope and any(
                parameter.name == name for parameter in definition.parameters
            ):
                return True
            if any(
                member.name == site.scope
                and any(parameter.name == name for parameter in member.parameters)
                for member in definition.members
            ):
                return True
        return False

    def _lexical_bindings(
        self, rel_path: str, site: Site, name: str
    ) -> tuple[ResolvedBinding, ...]:
        parsed = self.syntax.get(rel_path)
        module = self.module_for(rel_path)
        if parsed is None or module is None:
            return ()
        candidates = [
            item
            for item in parsed.sites
            if item.kind == "binding"
            and (item.assigned_name or item.name) == name
            and item.span.start_byte <= site.span.start_byte
            and item.scope_span is not None
            and item.scope_span.start_byte <= site.span.start_byte <= item.scope_span.end_byte
        ]
        if not candidates:
            return ()
        chosen = max(candidates, key=lambda item: (item.scope_depth, item.span.start_byte))
        return (
            ResolvedBinding(
                module,
                name,
                "binding",
                None,
                f"{rel_path}:{chosen.span.start_byte}:binding:{name}",
                rel_path,
                chosen.span,
            ),
        )

    def _declared_receiver_annotation(
        self, parsed: Syntax, receiver: str, site: Site | None
    ) -> str | None:
        if site is None:
            return None
        position = site.span.start_byte
        definitions = [
            item
            for item in parsed.definitions
            if item.span.start_byte <= position
            and (item.span.end_byte >= position or item.name == site.scope)
        ]
        for definition in sorted(
            definitions, key=lambda item: item.span.end_byte - item.span.start_byte
        ):
            parameters = [
                item.annotation for item in definition.parameters if item.name == receiver
            ]
            if parameters:
                return parameters[0]
            members = [
                member
                for member in definition.members
                if member.span.start_byte <= position
                and (member.span.end_byte >= position or member.name == site.scope)
            ]
            for member in members:
                parameters = [
                    item.annotation for item in member.parameters if item.name == receiver
                ]
                if parameters:
                    return parameters[0]
            fields = [item.annotation for item in definition.members if item.name == receiver]
            if fields:
                return fields[0]
        return None

    def _member_bindings(
        self, module: str, owner: str, name: str, *, static_only: bool = False
    ) -> tuple[ResolvedBinding, ...]:
        declarations = self._local_declarations(module, owner)
        if len(declarations) != 1:
            return ()
        definition = declarations[0].definition
        direct = [
            member
            for member in definition.members
            if member.name == name and (not static_only or member.static)
        ]
        if direct:
            return tuple(
                ResolvedBinding(
                    module,
                    f"{owner}.{member.name}",
                    member.kind,
                    None,
                    f"{declarations[0].identity}:{member.span.start_byte}:{member.kind}:{member.name}",
                    declarations[0].path,
                    member.span,
                )
                for member in direct
            )
        if definition.kind == "enum" and name in definition.enum_members:
            span = definition.enum_member_spans[definition.enum_members.index(name)]
            return (
                ResolvedBinding(
                    module,
                    f"{owner}.{name}",
                    "enum_member",
                    None,
                    f"{declarations[0].identity}:{span.start_byte}:enum_member:{name}",
                    declarations[0].path,
                    span,
                ),
            )
        if static_only:
            return ()
        return self._inherited_member_bindings(module, definition, name)

    def _constructor_bindings(
        self, module: str, owner: str, name: str
    ) -> tuple[ResolvedBinding, ...]:
        declarations = self._local_declarations(module, owner)
        if len(declarations) != 1:
            return ()
        declaration = declarations[0]
        constructors = [
            member
            for member in declaration.definition.members
            if member.kind == "constructor" and member.name in {name, f"{owner}.{name}"}
        ]
        return tuple(
            ResolvedBinding(
                declaration.module,
                f"{owner}.{name}",
                "constructor",
                None,
                f"{declaration.identity}:{member.span.start_byte}:constructor:{member.name}",
                declaration.path,
                member.span,
            )
            for member in constructors
        )

    def _inherited_member_bindings(
        self,
        module: str,
        owner: str | Definition,
        name: str,
        seen: frozenset[str] = frozenset(),
    ) -> tuple[ResolvedBinding, ...]:
        if isinstance(owner, str):
            declarations = self._local_declarations(module, owner)
            if len(declarations) != 1:
                return ()
            definition = declarations[0].definition
        else:
            definition = owner
        if definition.name in seen:
            return ()
        seen = seen | {definition.name}
        parents = (*reversed(definition.with_types), *definition.extends)
        for parent_type in parents:
            parent_name = _type_name(parent_type)
            if parent_name is None:
                continue
            parent = self._local_declarations(module, parent_name)
            if len(parent) != 1:
                continue
            members = [member for member in parent[0].definition.members if member.name == name]
            if members:
                return tuple(
                    ResolvedBinding(
                        module,
                        f"{parent_name}.{member.name}",
                        member.kind,
                        None,
                        f"{parent[0].identity}:{member.span.start_byte}:{member.kind}:{member.name}",
                        parent[0].path,
                        member.span,
                    )
                    for member in members
                )
            nested = self._inherited_member_bindings(module, parent[0].definition, name, seen=seen)
            if nested:
                return nested
        return ()

    def _local_declarations(self, module: str, name: str) -> list[_Declaration]:
        return [item for item in self._definitions.get(module, ()) if item.definition.name == name]

    def _imported_bindings(
        self, module: str, name: str, *, prefix: str | None
    ) -> tuple[ResolvedBinding, ...]:
        candidates: list[ResolvedBinding] = []
        for path, directive in self._imports.get(module, ()):
            if directive.prefix != prefix or not self._visible(directive, name):
                continue
            for target in self.resolve_directive(path, directive):
                if target.rel_path is None:
                    continue
                candidates.extend(self._exported_bindings(target.rel_path, name, set(), prefix))
        unique: dict[str, ResolvedBinding] = {item.declaration_id: item for item in candidates}
        return tuple(unique[key] for key in sorted(unique))

    def _exported_bindings(
        self, rel_path: str, name: str, seen: set[str], prefix: str | None
    ) -> list[ResolvedBinding]:
        module = self.module_for(rel_path)
        if module is None or module in seen:
            return []
        seen.add(module)
        direct = [
            item
            for item in self._local_declarations(module, name)
            if item.definition.visibility == "public"
        ]
        if direct:
            return [self._binding(item, prefix) for item in direct]
        result: list[ResolvedBinding] = []
        for path, directive in self._exports.get(module, ()):
            if not self._visible(directive, name):
                continue
            for target in self.resolve_directive(path, directive):
                if target.rel_path is not None:
                    result.extend(
                        self._exported_bindings(target.rel_path, name, seen.copy(), prefix)
                    )
        return result

    def _binding(self, declaration: _Declaration, prefix: str | None) -> ResolvedBinding:
        definition = declaration.definition
        return ResolvedBinding(
            declaration.module,
            definition.name,
            definition.kind,
            prefix,
            declaration.identity,
            declaration.path,
            definition.span,
        )

    @staticmethod
    def _visible(directive: Directive, name: str) -> bool:
        shown: set[str] | None = None
        hidden: set[str] = set()
        for operation, values in directive.combinators:
            names = set(values)
            if operation == "show":
                shown = names if shown is None else shown & names
                shown -= hidden
            elif operation == "hide":
                hidden.update(names)
                if shown is not None:
                    shown -= names
        if not directive.combinators:
            return name in directive.show if directive.show else name not in directive.hide
        return name in shown if shown is not None else name not in hidden

    def _index_definitions(self) -> dict[str, list[_Declaration]]:
        result: dict[str, list[_Declaration]] = {}
        for path, parsed in self.syntax.items():
            source = self.sources.get(path)
            module = self.module_for(path)
            if source is None or module is None:
                continue
            for definition in parsed.definitions:
                result.setdefault(module, []).append(_Declaration(path, module, definition))
        return result

    def _find_part_owners(self) -> dict[str, str]:
        candidates: dict[str, set[str]] = {}
        for path, parsed in self.syntax.items():
            if path not in self.sources:
                continue
            if any(item.kind == "part_of" for item in parsed.directives):
                continue
            for directive in parsed.directives:
                if directive.kind != "part":
                    continue
                target = self.resolve_uri(path, directive.target or "")
                if target is None or target.rel_path is None:
                    self._invalid_libraries.add(path)
                    self._problem(
                        path,
                        "PartError",
                        f"part {directive.target!r} is not a selected source file",
                        directive.span,
                    )
                    continue
                child_syntax = self.syntax.get(target.rel_path)
                part_of = (
                    next((item for item in child_syntax.directives if item.kind == "part_of"), None)
                    if child_syntax
                    else None
                )
                if part_of is None or not self._part_names_owner(
                    part_of.target, path, parsed, target.rel_path
                ):
                    self._invalid_parts.add(target.rel_path)
                    self._invalid_libraries.add(path)
                    self._problem(
                        path,
                        "PartError",
                        f"part {directive.target!r} does not name this library",
                        directive.span,
                    )
                    continue
                candidates.setdefault(target.rel_path, set()).add(path)
        owners: dict[str, str] = {}
        for part, libraries in candidates.items():
            if len(libraries) == 1:
                owners[part] = next(iter(libraries))
            else:
                self._invalid_parts.add(part)
                self._invalid_libraries.update(libraries)
                self._problem(
                    part, "PartOwnershipConflict", "part belongs to more than one selected library"
                )
        for path, parsed in self.syntax.items():
            part_of = next((item for item in parsed.directives if item.kind == "part_of"), None)
            if part_of is not None and path not in owners and path not in self._invalid_parts:
                self._problem(
                    path,
                    "PartError",
                    "part is not listed by exactly one selected library",
                    part_of.span,
                )
        return owners

    def _part_names_owner(
        self, target: str | None, path: str, syntax: Syntax, part_path: str
    ) -> bool:
        if target is None:
            return False
        if _is_uri(target):
            resolved = self.resolve_uri(part_path, target)
            return resolved is not None and resolved.rel_path == path
        library = next((item.target for item in syntax.directives if item.kind == "library"), None)
        return library == target

    def _source_at(self, rel: str, importer: str, uri: str) -> Source | None:
        if rel == ".." or rel.startswith("../") or not self._in_roots(rel):
            self._problem(importer, "ImportError", f"URI {uri!r} leaves the selected roots")
            return None
        source = self.sources.get(rel)
        if source is None or len(self._module_paths.get(source.module, ())) != 1:
            self._problem(
                importer, "ImportError", f"URI {uri!r} names no unique selected Dart source"
            )
            return None
        return source

    def _in_roots(self, rel: str) -> bool:
        path = rel.rstrip("/")
        return any(
            root == "." or path == root or path.startswith(f"{root}/")
            for root in self.snapshot.roots
        )

    def _problem(self, path: str, kind: str, message: str, span: Span | None = None) -> None:
        issue = ResolutionProblem(path, kind, message, span)
        if issue not in self.problems:
            self.problems.append(issue)


def _module_path(path: str) -> str | None:
    if not path or path.startswith("/") or ".." in _path_parts(path):
        return None
    return dart_module_name(path)


def _path_parts(path: str) -> tuple[str, ...]:
    return tuple(part for part in path.split("/") if part not in {"", "."})


def _is_uri(value: str) -> bool:
    return ":" in value or "/" in value or value.endswith(".dart")


def _type_name(value: str) -> str | None:
    match = re.match(r"\s*([A-Za-z_$][A-Za-z0-9_$]*)", value)
    return match.group(1) if match is not None else None


def _substitute_type(value: str | None, substitutions: dict[str, str]) -> str | None:
    if value is None:
        return None
    for name, replacement in substitutions.items():
        value = re.sub(rf"(?<![A-Za-z0-9_$]){re.escape(name)}(?![A-Za-z0-9_$])", replacement, value)
    return value


def _type_key(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _split_types(value: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(value):
        if char == "<":
            depth += 1
        elif char == ">":
            depth = max(depth - 1, 0)
        elif char == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    if value[start:].strip():
        parts.append(value[start:].strip())
    return parts
