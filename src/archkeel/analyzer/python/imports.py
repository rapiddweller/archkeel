# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Observe static imports and bounded literal loader dependencies."""

from __future__ import annotations

import ast
import importlib.util
from collections import Counter
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from typing import TypeAlias

from archkeel.ir.facts import EvidenceClass, in_scope, stable_id
from archkeel.ir.facts_codec import RawData as RecordData
from archkeel.ir.facts_codec import RawEvidence, RawRecord, classified
from archkeel.ir.reexports import resolve_reexports as resolve_import_origins

from .binding_types import AliasBinding, BindingKind, ImportKind
from .resolve import dotted_expression
from .scopes import LexicalScopes, NameBinding
from .source import (
    FRAMEWORK_BASES,
    NATIVE_DATACLASS_DECORATOR,
    NATIVE_TYPED_DICT_BASES,
    ParsedModule,
    add_evidence,
    annotation_text,
    call_id,
    class_creation_static,
    class_header_static,
    class_namespace_static,
    explicit_provider_escapes,
    exposes_dynamic_namespace,
    intrinsic_nullable_aliases,
    location,
    member_binding_closure,
    member_escape_references,
    module_scope_bindings,
    native_owner_creation_static,
    native_typed_dict_provider_static,
    package_for,
    proven_annotation_carrier_candidates,
    proven_callable_candidates,
    proven_class_value_candidates,
    proven_constructor_return_candidates,
    proven_map_union_candidates,
    resolve_static_name,
    setter_local_references,
    stable_direct_module_bindings,
    static_overload_bindings,
    unique_direct_module_bindings,
    unproven_member_bindings,
)

_MemberProofKey: TypeAlias = tuple[
    str, bool, bool, frozenset[str] | None, frozenset[str], frozenset[str]
]
_EnumOwnerKey: TypeAlias = tuple[str, str]
_EnumMemberKey: TypeAlias = tuple[str, str, str]
_EnumMutationIndex: TypeAlias = tuple[tuple[ParsedModule, ast.expr], ...]


def _is_type_checking_test(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Name)
        and node.id == "TYPE_CHECKING"
        or (isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING")
    )


def _owning_package(module: ParsedModule) -> str:
    if module.path.name == "__init__.py":
        return module.module
    return module.module.rpartition(".")[0]


def _binds_identical_submodule(node: ast.ImportFrom, alias: ast.alias, *, package: str) -> bool:
    """True exactly for the plain `from . import name` case in `package`'s own `__init__.py`.

    That statement really does bind ``name`` to the identically named submodule, so it must not
    count as an attribute that shadows it (AD-53); a rename (`as`) or an import from anywhere
    else binds ``name`` to something else and does shadow.
    """
    if alias.asname is not None:
        return False
    raw = "." * node.level + (node.module or "")
    try:
        anchor = importlib.util.resolve_name(raw, package) if node.level else node.module or ""
    except (ImportError, ValueError):
        return False
    return anchor == package


def _shadowed_names(module: ParsedModule) -> frozenset[str]:
    """Top-level names `module`'s package body binds ahead of a same-named submodule (AD-53).

    Only unconditional top-level statements count, matching ``literal_all_exports``: a name
    bound inside ``if``/``try`` is not settled at import time the way a bare top-level statement
    is. A ``__getattr__`` or a star import makes every attribute dynamic or unlisted, so either
    one empties the result and the caller keeps today's submodule-if-it-exists reading for the
    whole package -- the narrower blind spot ``docs/rules.md`` names for issue #23.
    """
    package = module.module
    names: set[str] = set()
    for node in module.tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if node.name == "__getattr__":
                return frozenset()
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    return frozenset()
                if not _binds_identical_submodule(node, alias, package=package):
                    names.add(alias.asname or alias.name)
    return frozenset(names)


def collect_package_bindings(parsed: Sequence[ParsedModule]) -> dict[str, frozenset[str]]:
    """Map each scanned package to the names its `__init__.py` binds ahead of a submodule.

    Computed once, before any module's ``from`` imports are resolved, because a module that
    imports from a package needs that package's own bindings even when it is scanned first.
    """
    return {
        module.module: _shadowed_names(module)
        for module in parsed
        if module.path.name == "__init__.py"
    }


class ImportCollector(ast.NodeVisitor):
    def __init__(
        self,
        module: ParsedModule,
        module_names: set[str],
        evidence: dict[str, RawEvidence],
        package_bindings: dict[str, frozenset[str]],
        *,
        namespace: str,
    ) -> None:
        self.module = module
        self.module_names = module_names
        self.evidence = evidence
        self.package_bindings = package_bindings
        self.namespace = namespace
        self.unique_bindings = unique_direct_module_bindings(module)
        self.module_level_imports: set[int] = set()
        stack: list[ast.AST] = [module.tree]
        while stack:
            statement = stack.pop()
            if isinstance(statement, ast.Import | ast.ImportFrom):
                self.module_level_imports.add(id(statement))
            if isinstance(
                statement,
                ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda,
            ):
                continue
            stack.extend(ast.iter_child_nodes(statement))
        self.under_type_checking = False
        self.items: list[RawRecord] = []

    def visit_Module(self, node: ast.Module) -> None:
        has_all = False
        all_literal = False
        for index, child in enumerate(node.body):
            if (
                index == 0
                and isinstance(child, ast.Expr)
                and isinstance(child.value, ast.Constant)
                and isinstance(child.value.value, str)
            ):
                continue
            if isinstance(child, ast.Import | ast.ImportFrom):
                continue
            if isinstance(child, ast.Assign | ast.AnnAssign):
                targets = child.targets if isinstance(child, ast.Assign) else (child.target,)
                if (
                    not has_all
                    and len(targets) == 1
                    and isinstance(targets[0], ast.Name)
                    and targets[0].id == "__all__"
                ):
                    has_all = True
                    all_literal = isinstance(child.value, ast.List | ast.Tuple) and all(
                        isinstance(item, ast.Constant) and isinstance(item.value, str)
                        for item in child.value.elts
                    )
                    if all_literal:
                        continue
            break
        else:
            self.module.compatibility_logic_free = has_all and all_literal
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        previous = self.under_type_checking
        if _is_type_checking_test(node.test):
            self.under_type_checking = True
            for child in node.body:
                self.visit(child)
            self.under_type_checking = previous
            for child in node.orelse:
                self.visit(child)
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            binding = alias.asname or alias.name.split(".")[0]
            # ``import a.b`` binds ``a``; ``import a.b as b`` binds the full module.
            binding_target = alias.name if alias.asname else alias.name.split(".")[0]
            self._bind(node, binding, AliasBinding(target=binding_target, kind=ImportKind.MODULE))
            self._record(node, target=alias.name, symbol=None, binding=binding, relative_level=0)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        package = _owning_package(self.module)
        raw = "." * node.level + (node.module or "")
        try:
            anchor = importlib.util.resolve_name(raw, package) if node.level else node.module or ""
        except (ImportError, ValueError) as exc:
            anchor = f"<unresolved:{raw}:{exc.__class__.__name__}>"
        for alias in node.names:
            if alias.name == "*":
                self._record(
                    node, target=anchor, symbol="*", binding="*", relative_level=node.level
                )
                continue
            submodule = f"{anchor}.{alias.name}" if anchor else alias.name
            shadowed = alias.name in self.package_bindings.get(anchor, frozenset())
            target = anchor if shadowed else submodule if submodule in self.module_names else anchor
            symbol = None if target == submodule else alias.name
            binding = alias.asname or alias.name
            binding_target = target if symbol is None else f"{target}.{symbol}"
            self._bind(
                node,
                binding,
                AliasBinding(
                    target=binding_target,
                    kind=ImportKind.MODULE if symbol is None else ImportKind.SYMBOL,
                    imported_name=alias.name,
                ),
            )
            self._record(
                node,
                target=target,
                symbol=symbol,
                binding=binding,
                relative_level=node.level,
            )

    def _bind(self, node: ast.AST, name: str, binding: AliasBinding) -> None:
        # A function or class import cannot change the module's namespace.
        self.module.import_aliases.setdefault(node, {})[name] = binding
        if id(node) in self.module_level_imports:
            self.module.aliases[name] = binding

    def _record(
        self,
        node: ast.AST,
        *,
        target: str,
        symbol: str | None,
        binding: str,
        relative_level: int,
    ) -> None:
        evidence_id = add_evidence(self.evidence, self.module, node)
        target_package = (
            package_for(target) if in_scope(target, self.namespace) else target.split(".")[0]
        )
        line, _, column = location(node)
        item_id = stable_id(
            "IMP",
            self.module.rel_path,
            line,
            column,
            target,
            symbol,
            binding,
        )
        self.items.append(
            classified(
                item_id=item_id,
                evidence_class=EvidenceClass.FACT,
                area="dependencies",
                kind="import",
                title=f"Import {target}{'.' + symbol if symbol else ''}",
                subjects=[self.module.module, target],
                evidence_ids=[evidence_id],
                data={
                    "source_module": self.module.module,
                    "source_package": self.module.package,
                    "target_module": target,
                    "target_package": target_package,
                    "symbol": symbol,
                    "binding": binding,
                    "relative_level": relative_level,
                    "under_type_checking": self.under_type_checking,
                    "ordinary_module": self.module.path.name != "__init__.py",
                    "module_level_import": id(node) in self.module_level_imports,
                    "reexport": self.module.path.name == "__init__.py"
                    or (
                        self.module.all_literal
                        and binding in self.module.all_exports
                        and binding in self.unique_bindings
                    ),
                    "reexport_candidate": (
                        self.module.path.name != "__init__.py"
                        and id(node) in self.module_level_imports
                        and binding in self.module.all_exports
                        and symbol is not None
                        and not (self.module.all_literal and binding in self.unique_bindings)
                    ),
                    # A Python import always names what it binds; a Dart import without `show`
                    # does not, and every rule reading `symbol` must tell the two apart (AD-97).
                    "symbols_known": True,
                },
            )
        )


def collect_imports(
    parsed: Sequence[ParsedModule],
    module_names: set[str],
    evidence: dict[str, RawEvidence],
    *,
    namespace: str,
) -> list[RawRecord]:
    """Run the import collector over every module and return its records sorted by id."""
    package_bindings = collect_package_bindings(parsed)
    imports: list[RawRecord] = []
    for module in parsed:
        module.all_exports = literal_all_exports(module.tree)
        module.all_literal = all_is_one_literal(module.tree)
        collector = ImportCollector(
            module, module_names, evidence, package_bindings, namespace=namespace
        )
        collector.visit(module.tree)
        imports.extend(collector.items)
    imports.sort(key=lambda item: item["id"])
    return imports


def resolve_reexports(
    imports: Sequence[RawRecord],
    exports_by_module: dict[str, set[str]],
    parsed: Sequence[ParsedModule] = (),
) -> tuple[dict[str, frozenset[str]], frozenset[str]]:
    """Follow re-export chains in place so each import records its origin definition."""
    stable_bindings: dict[str, frozenset[str]] = {
        module.module: stable_direct_module_bindings(module) for module in parsed
    }
    origin_bindings = {
        module.module: stable_bindings[module.module] | static_overload_bindings(module)
        for module in parsed
    }
    uncertain_origins = resolve_import_origins(imports, exports_by_module, origin_bindings)
    modules = {module.module: module for module in parsed}
    module_counts = Counter(module.module for module in parsed)
    providers = {
        name: intrinsic_nullable_aliases(module)
        for name, module in modules.items()
        if module_counts[name] == 1
    }
    aliases = {
        name: {binding: (name, binding) for binding in providers.get(name, ())} for name in modules
    }
    for item in imports:
        data = item["data"]
        consumer = modules.get(data["source_module"])
        provider = data["target_module"]
        symbol = data["symbol"]
        binding = data["binding"]
        origin = f"{provider}.{symbol}"
        entry = consumer.aliases.get(binding) if consumer is not None else None
        if (
            consumer is not None
            and module_counts[consumer.module] == 1
            and symbol in providers.get(provider, ())
            and data.get("source_binding_unique") is True
            and data.get("origin_binding_unique") is True
            and data["origin_definition"] == origin
            and data["reexport_chain"] == [origin]
            and not data.get("reexport_candidate")
            and not data.get("reexport_candidates")
            and not data["under_type_checking"]
            and consumer.bound_names.count(binding) == 1
            and entry is not None
            and entry.target == origin
            and any(
                isinstance(node, ast.ImportFrom)
                and any((alias.asname or alias.name) == binding for alias in node.names)
                for node in consumer.tree.body
            )
        ):
            aliases[consumer.module][binding] = (provider, symbol)
    candidates = _type_reference_candidates(imports, modules, aliases)
    escaped_bindings = {module.module: unproven_member_bindings(module) for module in parsed}
    escaped_bindings, unsafe_providers = _converge_member_escapes(
        imports, modules, stable_bindings, escaped_bindings, candidates
    )
    for item in imports:
        data = item["data"]
        source = data["source_module"]
        if source in escaped_bindings:
            data["source_member_binding_static"] = data["binding"] not in escaped_bindings[source]
        origin = data["origin_definition"]
        if isinstance(origin, str):
            origin_module, _, origin_name = origin.rpartition(".")
            if origin_module in escaped_bindings:
                data["origin_member_binding_static"] = (
                    origin_name not in escaped_bindings[origin_module]
                )
    return uncertain_origins, unsafe_providers


def _initial_member_exposures(
    modules: dict[str, ParsedModule],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    exposed_bindings, transferred_bindings = (
        {
            module.module: set(
                unproven_member_bindings(
                    module,
                    owner_exposure_only=True,
                    incoming=frozenset(),
                    unsafe_providers=_unsafe_native_creation_providers(set(), modules),
                    include_creation_uncertainty=include_creation,
                )
            )
            for module in modules.values()
        }
        for include_creation in (True, False)
    )
    return exposed_bindings, transferred_bindings


def _member_escape_pass(
    modules: Mapping[str, ParsedModule],
    exposed_bindings: Mapping[str, AbstractSet[str]],
    transferred_bindings: Mapping[str, AbstractSet[str]],
    unsafe_providers: AbstractSet[str],
    proofs: dict[_MemberProofKey, frozenset[str]],
) -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]], dict[str, frozenset[str]]]:
    escaped: dict[str, frozenset[str]] = {}
    exposed: dict[str, frozenset[str]] = {}
    transferred: dict[str, frozenset[str]] = {}
    unsafe = frozenset(unsafe_providers)
    for result, owner_exposure, creation, bindings, providers in (
        (escaped, False, True, None, unsafe),
        (exposed, True, True, exposed_bindings, unsafe),
        (transferred, True, False, transferred_bindings, unsafe),
    ):
        for name, module in modules.items():
            incoming = None if bindings is None else frozenset(bindings[name])
            key = (
                name,
                owner_exposure,
                creation,
                incoming,
                frozenset(module.incoming_member_escapes),
                providers,
            )
            if key not in proofs:
                proofs[key] = unproven_member_bindings(
                    module,
                    owner_exposure_only=owner_exposure,
                    incoming=incoming,
                    unsafe_providers=providers,
                    include_creation_uncertainty=creation,
                )
            result[name] = proofs[key]
    return escaped, exposed, transferred


def _converge_member_escapes(
    imports: Sequence[RawRecord],
    modules: dict[str, ParsedModule],
    stable_bindings: dict[str, frozenset[str]],
    escaped_bindings: dict[str, frozenset[str]],
    candidates: dict[str, dict[ast.expr, frozenset[tuple[str, str]]]],
) -> tuple[dict[str, frozenset[str]], frozenset[str]]:
    enum_member_proofs: dict[_EnumMemberKey, bool] = {}
    enum_owner_values: dict[_EnumOwnerKey, frozenset[str] | None] = {}
    enum_mutation_proofs: dict[_EnumOwnerKey, bool] = {}
    mutated_enum_owners = _enum_mutation_index(modules)
    for module in modules.values():
        module._non_escaping_enum_values = _non_escaping_enum_value_reads(
            modules,
            module,
            enum_member_proofs,
            enum_owner_values,
            enum_mutation_proofs,
            mutated_enum_owners,
        )
    exposed_bindings, transferred_bindings = _initial_member_exposures(modules)
    proofs: dict[_MemberProofKey, frozenset[str]] = {}
    namespace_bindings = {
        name: set(stable_bindings[name]) | {binding for _, binding in module_scope_bindings(module)}
        for name, module in modules.items()
    }
    while True:
        exposed_before = {name: frozenset(values) for name, values in exposed_bindings.items()}
        transferred_before = {
            name: frozenset(values) for name, values in transferred_bindings.items()
        }
        escaped_origins = _escaped_import_origins(
            imports, modules, escaped_bindings, stable_bindings, exposed_bindings
        )
        exposed_origins = _escaped_import_origins(
            imports, modules, exposed_bindings, stable_bindings, exposed_bindings
        )
        unsafe_providers = _unsafe_native_creation_providers(exposed_origins, modules)
        _saturate_unknown_owner_namespaces(
            modules, namespace_bindings, exposed_bindings, transferred_bindings, unsafe_providers
        )
        _propagate_member_escapes(
            imports, modules, namespace_bindings, escaped_origins, escaped_bindings
        )
        for bindings in (exposed_bindings, transferred_bindings):
            _propagate_member_escapes(
                imports,
                modules,
                namespace_bindings,
                _escaped_import_origins(imports, modules, bindings, stable_bindings, bindings),
                bindings,
                incoming_escapes=bindings,
                unsafe_providers=unsafe_providers,
            )
        protection_changed = _retain_type_reference_protection(
            modules, candidates, escaped_bindings, exposed_bindings, transferred_bindings
        )
        if protection_changed:
            # Revoked type-expression proofs are not captured by the escape-input key.
            proofs.clear()
        escaped, exposed, transferred = _member_escape_pass(
            modules, exposed_bindings, transferred_bindings, unsafe_providers, proofs
        )
        if (
            not protection_changed
            and escaped == escaped_bindings
            and exposed == exposed_before
            and transferred == transferred_before
        ):
            break
        escaped_bindings = escaped
        exposed_bindings = {name: set(values) for name, values in exposed.items()}
        transferred_bindings = {name: set(values) for name, values in transferred.items()}
    for name, module in modules.items():
        module.owner_exposed_bindings = frozenset(
            exposed_bindings[name] | transferred_bindings[name]
        )
    return escaped_bindings, frozenset(unsafe_providers)


def _non_escaping_enum_value_reads(
    modules: Mapping[str, ParsedModule],
    consumer: ParsedModule,
    member_proofs: dict[_EnumMemberKey, bool],
    owner_values: dict[_EnumOwnerKey, frozenset[str] | None],
    mutation_proofs: dict[_EnumOwnerKey, bool],
    mutation_index: _EnumMutationIndex,
) -> frozenset[ast.Attribute]:
    """Keep exact, unchanged source enum string values from exposing their owner."""
    result: set[ast.Attribute] = set()
    scopes = LexicalScopes.for_module(consumer)
    for call in (node for node in consumer.all_nodes if isinstance(node, ast.Call)):
        for argument in (*call.args, *(keyword.value for keyword in call.keywords)):
            for node in ast.walk(argument):
                if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
                    continue
                root = node.value
                alias = consumer.aliases.get(root.id)
                binding = scopes.lookup(root, root.id)
                if (
                    alias is None
                    or alias.kind is not ImportKind.SYMBOL
                    or binding.owner is not scopes.root
                    or binding.uncertain
                    or root.id not in stable_direct_module_bindings(consumer)
                ):
                    continue
                owner_separator = len(alias.target) - 1
                while owner_separator >= 0 and alias.target[owner_separator] != ".":
                    owner_separator -= 1
                if owner_separator <= 0:
                    continue
                owner_module = alias.target[:owner_separator]
                owner_name = alias.target[owner_separator + 1 :]
                provider = modules.get(owner_module)
                owner = (
                    next(
                        (
                            declaration
                            for declaration in provider.tree.body
                            if isinstance(declaration, ast.ClassDef)
                            and declaration.name == owner_name
                        ),
                        None,
                    )
                    if provider is not None
                    else None
                )
                if (
                    provider is None
                    or owner is None
                    or not _static_string_enum(
                        provider,
                        owner,
                        node.attr,
                        member_proofs,
                        owner_values,
                        mutation_proofs,
                        mutation_index,
                    )
                ):
                    continue
                result.add(node)
    return frozenset(result)


def _static_string_enum(
    provider: ParsedModule,
    owner: ast.ClassDef,
    member: str,
    member_proofs: dict[_EnumMemberKey, bool],
    owner_values: dict[_EnumOwnerKey, frozenset[str] | None],
    mutation_proofs: dict[_EnumOwnerKey, bool],
    mutation_index: _EnumMutationIndex,
) -> bool:
    owner_key = (provider.module, owner.name)
    member_key = (*owner_key, member)
    if member_key in member_proofs:
        return member_proofs[member_key]
    if owner_key not in owner_values:
        owner_values[owner_key] = _static_string_enum_values(
            provider, owner, mutation_proofs, mutation_index
        )
    values = owner_values[owner_key]
    result = values is not None and member in values
    member_proofs[member_key] = result
    return result


def _static_string_enum_values(
    provider: ParsedModule,
    owner: ast.ClassDef,
    mutation_proofs: dict[_EnumOwnerKey, bool],
    mutation_index: _EnumMutationIndex,
) -> frozenset[str] | None:
    if (
        owner.name not in stable_direct_module_bindings(provider)
        or owner.name not in unique_direct_module_bindings(provider)
        or not class_header_static(owner)
        or len(owner.bases) != 1
    ):
        return None
    base = owner.bases[0]
    base_name = resolve_static_name(provider, base)
    if base_name not in {"enum.Enum", "enum.StrEnum"} or not _canonical_enum_base(
        provider, base, base_name
    ):
        return None
    if _enum_owner_is_mutated(provider, owner, mutation_proofs, mutation_index):
        return None
    values: set[str] = set()
    for index, child in enumerate(owner.body):
        if (
            index == 0
            and isinstance(child, ast.Expr)
            and isinstance(child.value, ast.Constant)
            and isinstance(child.value.value, str)
        ):
            continue
        target: ast.expr
        value: ast.expr | None
        if isinstance(child, ast.Assign) and len(child.targets) == 1:
            target, value = child.targets[0], child.value
        elif isinstance(child, ast.AnnAssign):
            target, value = child.target, child.value
        else:
            return None
        if (
            not isinstance(target, ast.Name)
            or not isinstance(value, ast.Constant)
            or not isinstance(value.value, str)
        ):
            return None
        values.add(target.id)
    return frozenset(values) if values else None


def _canonical_enum_base(module: ParsedModule, base: ast.expr, expected: str) -> bool:
    parts: list[str] = []
    root = base
    while isinstance(root, ast.Attribute):
        parts.insert(0, root.attr)
        root = root.value
    if not isinstance(root, ast.Name) or root.id not in stable_direct_module_bindings(module):
        return False
    alias = module.aliases.get(root.id)
    if alias is None:
        return False
    resolved = ".".join((alias.target, *parts))
    return resolved == expected


def _enum_mutation_index(
    modules: Mapping[str, ParsedModule],
) -> _EnumMutationIndex:
    """Index only AST nodes that might mutate an enum owner."""
    candidates: list[tuple[ParsedModule, ast.expr]] = []
    for module_name in modules:
        module = modules[module_name]
        for node in module.all_nodes:
            target: ast.expr | None = None
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store | ast.Del):
                target = node.value
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"setattr", "delattr"}
                and node.args
            ):
                target = node.args[0]
            if target is None:
                continue
            candidates.append((module, target))
    return tuple(candidates)


def _enum_owner_is_mutated(
    provider: ParsedModule,
    owner: ast.ClassDef,
    proofs: dict[_EnumOwnerKey, bool],
    mutation_index: _EnumMutationIndex,
) -> bool:
    key = (provider.module, owner.name)
    if key not in proofs:
        qualified = f"{provider.module}.{owner.name}"
        proofs[key] = any(
            (
                f"{module.module}.{target.id}"
                if module is provider and isinstance(target, ast.Name)
                else resolve_static_name(module, target)
            )
            == qualified
            for module, target in mutation_index
        )
    return proofs[key]


def _type_reference_candidates(
    imports: Sequence[RawRecord],
    modules: dict[str, ParsedModule],
    aliases: Mapping[str, dict[str, tuple[str, str]]],
) -> dict[str, dict[ast.expr, frozenset[tuple[str, str]]]]:
    callable_providers = _callable_providers(imports, modules)
    class_value_bindings: dict[tuple[str, str], tuple[str, str]] = {}
    for item in imports:
        data = item["data"]
        origin_value = data["origin_definition"]
        if not isinstance(origin_value, str):
            continue
        origin: str = origin_value
        provider, _, symbol = origin.rpartition(".")
        if (
            provider in modules
            and data.get("source_binding_unique") is True
            and data.get("origin_binding_unique") is True
            and data.get("module_level_import") is True
            and data["under_type_checking"] is False
            and data["reexport_chain"] == [origin]
            and not data.get("reexport_candidate")
            and not data.get("reexport_candidates")
        ):
            class_value_bindings[(data["source_module"], data["binding"])] = (provider, symbol)
    map_candidates = {
        name: proven_map_union_candidates(module, aliases[name]) for name, module in modules.items()
    }
    class_values = proven_class_value_candidates(
        modules,
        class_value_bindings,
        unsafe_providers=explicit_factory_unsafe_providers(imports, tuple(modules.values())),
    )
    candidates = {
        name: {
            **map_candidates[name],
            **proven_callable_candidates(module, callable_providers[name]),
            **class_values[name],
            **proven_constructor_return_candidates(module),
        }
        for name, module in modules.items()
    }
    for name, module in modules.items():
        module._proven_map_union_expressions = frozenset(map_candidates[name])
        carriers = proven_annotation_carrier_candidates(module, frozenset(modules))
        module._proven_annotation_carriers = frozenset(carriers)
        candidates[name] |= carriers
    return candidates


def _callable_providers(
    imports: Sequence[RawRecord], modules: dict[str, ParsedModule]
) -> dict[str, dict[str, frozenset[tuple[str, str]]]]:
    bindings: dict[tuple[str, str], list[RecordData]] = {}
    for item in imports:
        data = item["data"]
        binding_records: list[RecordData] = bindings.setdefault(
            (data["source_module"], data["binding"]), []
        )
        binding_records.append(data)
    providers: dict[str, dict[str, frozenset[tuple[str, str]]]] = {name: {} for name in modules}
    for (source, binding), records in bindings.items():
        module = modules.get(source)
        if module is None or len(records) != 1 or module.bound_names.count(binding) != 1:
            continue
        data = records[0]
        if not _callable_provider_binding(data):
            continue
        origin_value = data.get("origin_definition")
        head = binding
        source_providers: dict[str, frozenset[tuple[str, str]]] = providers[source]
        dependencies: set[tuple[str, str]] = {(source, binding)}
        if data["symbol"] is None:
            origin_value = f"{data['target_module']}.Callable"
            head = f"{binding}.Callable"
            if data["target_module"] == "collections.abc" and binding == "collections":
                continue
        else:
            route = data["reexport_chain"]
            if (
                data.get("origin_binding_unique") is not True
                or not route
                or route[0] != f"{data['target_module']}.{data['symbol']}"
                or route[-1] != origin_value
            ):
                continue
            for index, hop in enumerate(route[:-1]):
                hop_text: str = hop
                owner, _, name = hop_text.rpartition(".")
                records_at_hop = bindings.get((owner, name), ())
                if len(records_at_hop) != 1:
                    break
                peer = records_at_hop[0]
                if (
                    not _callable_provider_binding(peer)
                    or peer.get("reexport") is not True
                    or peer.get("origin_binding_unique") is not True
                    or peer.get("origin_definition") != origin_value
                    or peer["reexport_chain"] != route[index + 1 :]
                ):
                    break
                dependencies.add((owner, name))
            else:
                source_providers[head] = frozenset(dependencies)
            if head not in source_providers:
                continue
        if not isinstance(origin_value, str):
            continue
        origin: str = origin_value
        if origin not in {"typing.Callable", "collections.abc.Callable"} or any(
            origin == name or origin.startswith(name + ".") for name in modules
        ):
            source_providers.pop(head, None)
            continue
        source_providers[head] = frozenset(dependencies)
    return providers


def _callable_provider_binding(data: RecordData) -> bool:
    return (
        data.get("source_binding_unique") is True
        and data.get("module_level_import") is True
        and data.get("under_type_checking") is False
        and (data.get("ordinary_module") is True or data.get("ordinary_module") is False)
        and not data.get("reexport_candidate")
        and not data.get("reexport_candidates")
    )


def _retain_type_reference_protection(
    modules: Mapping[str, ParsedModule],
    candidates: dict[str, dict[ast.expr, frozenset[tuple[str, str]]]],
    escaped_bindings: Mapping[str, AbstractSet[str]],
    exposed_bindings: Mapping[str, AbstractSet[str]],
    transferred_bindings: Mapping[str, AbstractSet[str]],
) -> bool:
    protection_changed = False
    for name, module in modules.items():
        current_candidates = candidates[name]
        retained = {
            expression: dependencies
            for expression, dependencies in current_candidates.items()
            if not any(
                binding in escaped_bindings[provider]
                or binding in exposed_bindings[provider]
                or binding in transferred_bindings[provider]
                or binding in modules[provider].incoming_member_escapes
                for provider, binding in dependencies
            )
        }
        protection = frozenset(retained)
        protection_changed |= protection != frozenset(current_candidates)
        candidates[name] = retained
        module._proven_map_union_expressions &= protection
        module._proven_annotation_carriers &= protection
        module._proven_callable_expressions &= protection
        module._proven_class_values &= protection
        module._proven_constructor_returns &= protection
    return protection_changed


def _saturate_unknown_owner_namespaces(
    modules: Mapping[str, ParsedModule],
    namespace_bindings: Mapping[str, AbstractSet[str]],
    exposed_bindings: dict[str, set[str]],
    transferred_bindings: dict[str, set[str]],
    unsafe_providers: AbstractSet[str],
) -> None:
    for name, module in modules.items():
        if any(
            isinstance(owner, ast.ClassDef)
            and (
                owner.name in transferred_bindings[name]
                or owner.name in exposed_bindings[name]
                and not class_creation_static(
                    module, owner, owner_exposure_only=True, unsafe_providers=unsafe_providers
                )
            )
            for owner in module.tree.body
        ):
            # A transferred class or opaque creation hook exposes its own module namespace.
            module.incoming_member_escapes |= namespace_bindings[name]
            exposed_bindings[name] |= namespace_bindings[name]
            transferred_bindings[name] |= namespace_bindings[name]
    if any(
        isinstance(owner, ast.ClassDef)
        and owner.name in transferred_bindings[name]
        and not class_namespace_static(module, owner)
        for name, module in modules.items()
        for owner in module.tree.body
    ):
        # An unproven destination can expose any namespace already in the scanned closure.
        for name, bindings in namespace_bindings.items():
            modules[name].incoming_member_escapes |= bindings
            exposed_bindings[name] |= bindings
            transferred_bindings[name] |= bindings


def explicit_factory_unsafe_providers(
    imports: Sequence[RawRecord], parsed: Sequence[ParsedModule]
) -> frozenset[str]:
    modules = {module.module: module for module in parsed}
    explicit_escapes = {name: explicit_provider_escapes(module) for name, module in modules.items()}
    factories = {NATIVE_DATACLASS_DECORATOR, *NATIVE_TYPED_DICT_BASES}
    providers: set[str] = set()
    for factory in factories:
        origin: str = factory
        providers.add(origin.rpartition(".")[0])
    # Other provider objects do not prove a mutation of a named header factory.
    provider_imports = [
        item
        for item in imports
        if item["data"]["target_module"] in providers
        and item["data"]["symbol"] in {None, "*"}
        or any(
            origin in factories | providers
            for origin in (
                item["data"]["origin_definition"],
                *(
                    item["data"]["reexport_candidates"]
                    if "reexport_candidates" in item["data"]
                    else ()
                ),
            )
        )
    ]
    origins = _escaped_import_origins(
        provider_imports,
        modules,
        explicit_escapes,
        {name: stable_direct_module_bindings(module) for name, module in modules.items()},
        explicit_escapes,
    )
    return frozenset(
        provider
        for provider in providers
        if provider in modules
        or any(in_scope(origin, provider) for origin in origins)
        or any(
            item["data"]["symbol"] == "*" and item["data"]["target_module"] == provider
            for item in imports
        )
    )


def _unsafe_native_creation_providers(
    exposed_origins: AbstractSet[str], modules: Mapping[str, ParsedModule]
) -> set[str]:
    providers: set[str] = set()
    for native_origin in (NATIVE_DATACLASS_DECORATOR, *NATIVE_TYPED_DICT_BASES):
        origin: str = native_origin
        providers.add(origin.rpartition(".")[0])
    if any(not any(in_scope(origin, name) for name in modules) for origin in exposed_origins):
        return providers
    return providers & set(modules)


def _escaped_import_origins(
    imports: Sequence[RawRecord],
    modules: Mapping[str, ParsedModule],
    escaped_bindings: Mapping[str, AbstractSet[str]],
    stable_bindings: Mapping[str, AbstractSet[str]],
    exposed_bindings: Mapping[str, AbstractSet[str]],
) -> set[str]:
    escaped_origins: set[str] = set()
    for item in imports:
        data = item["data"]
        source, binding = data["source_module"], data["binding"]
        if binding not in escaped_bindings.get(source, ()):
            continue
        origins = (
            {data["target_module"]}
            if data["symbol"] in {None, "*"}
            else {data["origin_definition"], *data.get("reexport_candidates", ())}
        )
        for origin in origins:
            if not isinstance(origin, str):
                continue
            qualified_origin: str = origin
            provider, _, _ = qualified_origin.rpartition(".")
            # A stable name can still expose its native owner to a mutator.
            escaped_origins.add(
                provider
                if provider
                and provider not in modules
                and (
                    binding not in stable_bindings.get(source, ())
                    or binding in exposed_bindings.get(source, ())
                )
                else origin
            )
    return escaped_origins


def _propagate_member_escapes(
    imports: Sequence[RawRecord],
    modules: dict[str, ParsedModule],
    namespace_bindings: dict[str, set[str]],
    escaped_origins: set[str],
    escaped_bindings: Mapping[str, AbstractSet[str]],
    *,
    incoming_escapes: dict[str, set[str]] | None = None,
    unsafe_providers: AbstractSet[str] = frozenset(),
) -> None:
    incoming = (
        incoming_escapes
        if incoming_escapes is not None
        else {name: module.incoming_member_escapes for name, module in modules.items()}
    )
    # Escape origins and namespace inventory stay fixed; incoming binding sets do not.
    escaped_namespaces = {
        escaped[:end]
        for escaped in escaped_origins
        for end, char in enumerate(escaped)
        if char == "."
    }
    namespace_targets: dict[str, set[tuple[str, str]]] = {}
    for item in imports:
        data = item["data"]
        targets: set[tuple[str, str]] = set()
        if data["symbol"] is None:
            target: str = data["target_module"]
            origins = {target}
            if target not in namespace_targets:
                namespace_targets[target] = {
                    (name, binding)
                    for name, bindings in namespace_bindings.items()
                    if in_scope(name, target)
                    for binding in bindings
                }
            targets = namespace_targets[target]
        else:
            origins = {data["origin_definition"], *data.get("reexport_candidates", ())}
            for origin in origins:
                if not isinstance(origin, str):
                    continue
                qualified_origin: str = origin
                name, _, binding = qualified_origin.rpartition(".")
                if name in modules:
                    targets |= {(name, binding)}
        source = data["source_module"]
        if source in modules and any(
            isinstance(origin, str)
            and (
                origin in escaped_origins
                or any(
                    origin[:end] in escaped_origins
                    for end, char in enumerate(origin)
                    if char == "."
                )
                or (data["symbol"] is None and origin in escaped_namespaces)
            )
            for origin in origins
        ):
            incoming[source] |= {data["binding"]}
        if source in modules and not targets:
            incoming[source] |= _opaque_import_member_escapes(
                data,
                modules[source],
                owner_exposure_only=incoming_escapes is not None,
                unsafe_providers=unsafe_providers,
            )
        if source in modules and any(
            binding in escaped_bindings[name] for name, binding in targets
        ):
            incoming[source] |= {data["binding"]}
        if data["binding"] in escaped_bindings.get(source, ()):
            for name, binding in targets:
                incoming[name] |= {binding}


def _opaque_import_member_escapes(
    data: RecordData,
    module: ParsedModule,
    *,
    owner_exposure_only: bool,
    unsafe_providers: AbstractSet[str],
) -> set[str]:
    # An opaque callable import does not transfer owners; an unknown base receives its subclass.
    escaped: set[str] = set()
    framework = (
        data["source_binding_unique"] is True
        and data.get("origin_binding_unique") is True
        and data["origin_definition"] in FRAMEWORK_BASES
        and not data.get("reexport_candidate")
    )
    if owner_exposure_only and framework:
        return escaped
    carrier = (
        data["source_binding_unique"] is True
        and data.get("origin_binding_unique") is True
        and data["reexport_chain"] == [data["origin_definition"]]
        and not data.get("reexport_candidate")
        and not data.get("reexport_candidates")
        and any(
            isinstance(expression, ast.Subscript)
            and resolve_static_name(module, expression.value) == data["origin_definition"]
            and any(
                isinstance(node, ast.Name) and node.id == data["binding"]
                for node in ast.walk(expression.value)
            )
            for expression in module._proven_annotation_carriers
        )
    )
    native_typed_dict = native_typed_dict_provider_static(module, data["binding"], unsafe_providers)
    if (
        not owner_exposure_only
        and data["symbol"] is not None
        and not (
            framework
            or carrier
            or native_typed_dict
            or data["binding"] in module._proven_callable_providers
        )
    ):
        escaped |= {data["binding"]}
    if data["symbol"] is not None and not owner_exposure_only:
        return escaped
    owners = [node for node in module.all_nodes if isinstance(node, ast.ClassDef) and node.bases]
    if not owners:
        return escaped
    base_bindings = (
        member_binding_closure(
            module.all_nodes,
            {data["binding"]},
            member_surface=True,
            local_references=setter_local_references(module),
        )
        if owner_exposure_only
        else {data["binding"]}
    )
    for owner in owners:
        if (
            owner_exposure_only
            or native_typed_dict
            and len(owner.bases) == 1
            and resolve_static_name(module, owner.bases[0]) in NATIVE_TYPED_DICT_BASES
        ) and native_owner_creation_static(module, owner, unsafe_providers):
            continue
        for base in owner.bases:
            head = base.value if isinstance(base, ast.Subscript) else base
            if any(
                isinstance(node, ast.Name) and node.id in base_bindings for node in ast.walk(head)
            ) and not (
                data["source_binding_unique"] is True
                and resolve_static_name(module, head) in FRAMEWORK_BASES
            ):
                escaped |= {owner.name}
    return escaped


def all_is_one_literal(tree: ast.Module) -> bool:
    """True when `__all__` is bound once, at top level, to a literal of strings, and no other
    statement anywhere in the module names or imports it (AD-99).

    `literal_all_exports` reads every literal it finds and skips `+=`, `.append`, `.extend` and
    starred elements, so only this proves its answer is the module's whole `__all__`. A string
    such as `globals()["__all__"]` stays out of reach, as every dynamic binding does.
    """
    references = [
        node for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == "__all__"
    ]
    if any(
        "__all__" in (alias.asname, alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    ):
        return False
    values: list[ast.expr | None] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets == references:
            values.append(node.value)
        elif isinstance(node, ast.AnnAssign) and [node.target] == references:
            values.append(node.value)
    value = values[0] if len(values) == 1 else None
    return isinstance(value, ast.List | ast.Tuple) and all(
        isinstance(item, ast.Constant) and isinstance(item.value, str) for item in value.elts
    )


def literal_all_exports(tree: ast.Module) -> set[str]:
    exports: set[str] = set()
    for node in tree.body:
        value: ast.AST | None = None
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
            )
            or isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
        ):
            value = node.value
        if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            continue
        for element in value.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                exports.add(element.value)
    return exports


_LOADERS = frozenset({"importlib.import_module", "builtins.__import__"})


def _argument(node: ast.Call, position: int, keyword: str) -> ast.expr | None:
    for keyword_argument in node.keywords:
        if keyword_argument.arg is None:
            return None
    for argument in node.args:
        if isinstance(argument, ast.Starred):
            return None
    values = [item.value for item in node.keywords if item.arg == keyword]
    if len(node.args) > position:
        values.append(node.args[position])
    return values[0] if len(values) == 1 else None


def _literal(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _binding_may_be_absent(scopes: LexicalScopes, binding: NameBinding, node: ast.Name) -> bool:
    owner = binding.owner
    if owner is None or binding.uncertain:
        return True
    for site in owner.bindings.get(node.id, ()):
        if scopes.by_node[site] is not owner:
            continue
        statement = site
        while not isinstance(statement, ast.stmt) and statement in scopes.parents:
            statement = scopes.parents[statement]
        # Assignment targets become visible only after the complete RHS has run.
        if (
            isinstance(statement, ast.stmt)
            and statement.end_lineno is not None
            and statement.end_col_offset is not None
            and not (isinstance(statement, ast.AnnAssign) and statement.value is None)
            and not (isinstance(site, ast.Name) and isinstance(site.ctx, ast.Del))
            and (statement.end_lineno, statement.end_col_offset) <= (node.lineno, node.col_offset)
        ):
            return False
    return True


def _import_targets(scopes: LexicalScopes, node: ast.expr) -> frozenset[str]:
    targets: set[str] = set()
    pending: list[tuple[ast.expr, str, frozenset[tuple[ast.AST, str]]]] = [(node, "", frozenset())]
    while pending:
        expression, suffix, seen = pending.pop()
        dotted = dotted_expression(expression)
        root = expression
        while isinstance(root, ast.Attribute):
            root = root.value
        if dotted is None or not isinstance(root, ast.Name):
            continue
        bindings = [scopes.lookup(root, root.id)]
        owner = bindings[0].owner
        if (
            root.id == "__import__"
            and owner is not None
            and isinstance(owner.node, ast.ClassDef)
            and _binding_may_be_absent(scopes, bindings[0], root)
        ):
            # A missing class-local value checks globals before builtins.
            bindings.append(scopes.lookup(scopes.root.node, root.id))
        tail = dotted[len(root.id) :] + suffix
        for binding in bindings:
            owner = binding.owner
            if owner is None or (owner.node, root.id) in seen:
                continue
            targets.update(target + tail for target in binding.targets)
            if root.id == "__import__" and (
                binding.kind is BindingKind.UNBOUND
                # Unbound module globals fall through to builtins; function locals do not.
                or owner is scopes.root
                and _binding_may_be_absent(scopes, binding, root)
            ):
                targets.add("builtins.__import__" + tail)
            for site in owner.bindings.get(root.id, ()):
                parent = scopes.parents.get(site)
                if (
                    isinstance(site, ast.Name)
                    and isinstance(parent, ast.Assign | ast.AnnAssign)
                    and parent.value is not None
                ):
                    pending.append((parent.value, tail, seen | {(owner.node, root.id)}))
    return frozenset(targets)


def _import_origins(target: str, routes: Mapping[str, frozenset[str]]) -> frozenset[str]:
    origins: set[str] = set()
    pending: list[tuple[str, frozenset[str]]] = [(target, frozenset())]
    while pending:
        current, seen = pending.pop()
        prefix = current
        while prefix and prefix not in routes:
            name: str = prefix
            prefix = name.rpartition(".")[0]
        if not prefix:
            origins.add(current)
        elif prefix not in seen:
            pending.extend(
                (origin + current[len(prefix) :], seen | {prefix})
                for origin in routes[prefix]
                if origin != prefix
            )
    return frozenset(origins)


def _loader_mutations(
    parsed: Sequence[ParsedModule], routes: Mapping[str, frozenset[str]]
) -> tuple[frozenset[str], Mapping[str, frozenset[str]]]:
    """The loaders a visible mutation changes in every module, and those a module's own namespace
    exposure (`globals()`, `eval`, `exec`) changes in that module only (AD-273)."""
    changed: set[str] = set()
    exposed: dict[str, frozenset[str]] = {}
    for module in parsed:
        if module.module in {"importlib", "builtins"}:
            changed.update(_LOADERS)
        elif any(
            exposes_dynamic_namespace(
                module, node, member_surface=True, include_import_effects=False
            )
            for node in module.all_nodes
        ):
            exposed[module.module] = _LOADERS
        # Every module shares the builtins dict, so a use of `__builtins__` can change `__import__`
        # for all of them; it is a visible escape, not a namespace exposure of this module.
        if any(
            isinstance(node, ast.Name) and node.id == "__builtins__" for node in module.all_nodes
        ):
            changed.add("builtins.__import__")
        scopes = LexicalScopes.for_module(module)
        for node in member_escape_references(
            module, module.all_nodes, member_surface=True, owner_exposure_only=True
        ):
            for target in _import_targets(scopes, node):
                changed.update(_import_origins(target, routes))
    return (
        frozenset(
            loader for loader in _LOADERS if any(in_scope(loader, target) for target in changed)
        ),
        exposed,
    )


def _dynamic_target(
    node: ast.Call, targets: AbstractSet[str], proven: bool
) -> tuple[str | None, bool]:
    target = _literal(_argument(node, 0, "name")) if proven else None
    module_name: str = target or ""
    incomplete = not target
    if "builtins.__import__" in targets:
        fromlist = _argument(node, 3, "fromlist")
        supplied = len(node.args) > 3 or any(k.arg == "fromlist" for k in node.keywords)
        incomplete |= supplied and not (
            isinstance(fromlist, ast.Tuple | ast.List)
            and not fromlist.elts
            or isinstance(fromlist, ast.Constant)
            and fromlist.value is None
        )
        level = _argument(node, 4, "level")
        if level is not None and not (
            isinstance(level, ast.Constant) and type(level.value) is int and level.value == 0
        ):
            target = None
    elif module_name.startswith("."):
        package = _literal(_argument(node, 1, "package"))
        try:
            target = importlib.util.resolve_name(module_name, package) if package else None
        except (ImportError, ValueError):
            target = None
    return target, incomplete


class _DynamicImports(ImportCollector):
    def __init__(
        self,
        module: ParsedModule,
        evidence: dict[str, RawEvidence],
        namespace: str,
        calls: dict[str, RawRecord],
        mutations: frozenset[str],
        routes: Mapping[str, frozenset[str]],
    ) -> None:
        ImportCollector.__init__(self, module, set(), evidence, {}, namespace=namespace)
        self.calls = calls
        self.mutations = mutations
        self.routes = routes
        self.scopes = LexicalScopes.for_module(module)
        self.stable_bindings = stable_direct_module_bindings(module, include_import_effects=False)
        self.unknowns: list[RawRecord] = []

    def visit_Import(self, node: ast.Import) -> None:
        pass

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        pass

    def visit_Call(self, node: ast.Call) -> None:
        evidence_id = add_evidence(self.evidence, self.module, node)
        item_id = call_id(self.module, node, annotation_text(node.func) or "<unparseable>")
        call = self.calls.get(item_id)
        direct = call["data"]["targets"] if call else []
        targets = {
            origin
            for target in {*direct, *_import_targets(self.scopes, node.func)}
            for origin in _import_origins(target, self.routes)
        }
        if targets & _LOADERS:
            callee: str = dotted_expression(node.func) or ""
            binding = self.scopes.lookup(node.func, callee.split(".")[0]) if callee else None
            binding_static = bool(
                callee
                and binding
                and binding.owner is not None
                and not binding.uncertain
                and (
                    binding.kind is BindingKind.UNBOUND
                    or binding.owner is not self.scopes.root
                    or callee.split(".")[0] in self.stable_bindings
                )
            )
            proven = (
                len(direct) == 1
                and direct[0] in _LOADERS
                and call is not None
                and binding_static
                and not self.mutations.intersection(targets)
            )
            target, incomplete = _dynamic_target(node, targets, proven)
            module_name: str = target or ""
            if module_name and all(part.isidentifier() for part in module_name.split(".")):
                self._record(node, target=module_name, symbol=None, binding="", relative_level=0)
                # Loading a module proves a dependency, not a statically bound public symbol.
                record: RawRecord = self.items[-1]
                record["data"]["binding"] = None
                record["data"]["symbols_known"] = False
                record["data"]["reexport"] = False
                record["data"]["reexport_candidate"] = False
                record["fact_ids"] = [call["id"]] if call else []
            else:
                incomplete = True
            if incomplete:
                self.unknowns.append(
                    classified(
                        item_id=stable_id("UNKNOWN-DYNAMIC-IMPORT", item_id),
                        evidence_class=EvidenceClass.UNKNOWN,
                        area="dependencies",
                        kind="dynamic_import_limit",
                        title="Dynamic loading has an unproven binding, target or fromlist",
                        subjects=[self.module.module],
                        evidence_ids=[evidence_id],
                        fact_ids=[call["id"]] if call else [],
                        data={
                            "source_module": self.module.module,
                            "under_type_checking": self.under_type_checking,
                        },
                    )
                )
        self.generic_visit(node)


def collect_dynamic_imports(
    parsed: Sequence[ParsedModule],
    calls: Sequence[RawRecord],
    static_imports: Sequence[RawRecord],
    evidence: dict[str, RawEvidence],
    *,
    namespace: str,
) -> tuple[list[RawRecord], list[RawRecord]]:
    by_id = {call["id"]: call for call in calls}
    routes: dict[str, set[str]] = {}
    for item in static_imports:
        data = item["data"]
        if data.get("module_level_import") is not True or not data.get("binding"):
            continue
        alias = f"{data['source_module']}.{data['binding']}"
        target = data["target_module"] + (f".{data['symbol']}" if data["symbol"] else "")
        route: set[str] = routes.setdefault(alias, set())
        route.update(
            {target, data.get("origin_definition") or target, *data.get("reexport_candidates", ())}
        )
    imported_origins = {name: frozenset(values) for name, values in routes.items()}
    mutations, exposed = _loader_mutations(parsed, imported_origins)
    imports: list[RawRecord] = []
    unknowns: list[RawRecord] = []
    for module in parsed:
        changed = mutations | exposed.get(module.module, frozenset())
        collector = _DynamicImports(module, evidence, namespace, by_id, changed, imported_origins)
        collector.visit(module.tree)
        imports.extend(collector.items)
        unknowns.extend(collector.unknowns)
    return imports, unknowns
