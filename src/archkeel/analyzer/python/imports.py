# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Import statement collection for the Python architecture scanner."""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet

from archkeel.ir.facts import EvidenceClass, in_scope, stable_id
from archkeel.ir.facts_codec import RawData as RecordData
from archkeel.ir.facts_codec import RawEvidence, RawRecord, classified
from archkeel.ir.reexports import resolve_reexports as resolve_import_origins

from .source import (
    FRAMEWORK_BASES,
    NATIVE_DATACLASS_DECORATOR,
    NATIVE_TYPED_DICT_BASE,
    AliasBinding,
    ParsedModule,
    add_evidence,
    class_namespace_static,
    location,
    member_binding_closure,
    module_scope_bindings,
    native_owner_creation_static,
    package_for,
    resolve_static_name,
    stable_direct_module_bindings,
    unique_direct_module_bindings,
    unproven_member_bindings,
)


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
            self.module.aliases[binding] = AliasBinding(target=binding_target, kind="module")
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
            self.module.aliases[binding] = AliasBinding(
                target=binding_target,
                kind="module" if symbol is None else "symbol",
                imported_name=alias.name,
            )
            self._record(
                node,
                target=target,
                symbol=symbol,
                binding=binding,
                relative_level=node.level,
            )

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
) -> dict[str, frozenset[str]]:
    """Follow re-export chains in place so each import records its origin definition."""
    stable_bindings: dict[str, frozenset[str]] = {
        module.module: stable_direct_module_bindings(module) for module in parsed
    }
    escaped_bindings = {module.module: unproven_member_bindings(module) for module in parsed}
    uncertain_origins = resolve_import_origins(imports, exports_by_module, stable_bindings)
    modules = {module.module: module for module in parsed}
    escaped_bindings = _converge_member_escapes(imports, modules, stable_bindings, escaped_bindings)
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
    return uncertain_origins


def _converge_member_escapes(
    imports: Sequence[RawRecord],
    modules: dict[str, ParsedModule],
    stable_bindings: dict[str, frozenset[str]],
    escaped_bindings: dict[str, frozenset[str]],
) -> dict[str, frozenset[str]]:
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
    namespace_bindings = {
        name: set(stable_bindings[name]) | {binding for _, binding in module_scope_bindings(module)}
        for name, module in modules.items()
    }
    while True:
        _saturate_unknown_owner_namespaces(
            modules, namespace_bindings, exposed_bindings, transferred_bindings
        )
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
        escaped = {module.module: unproven_member_bindings(module) for module in modules.values()}
        exposed, transferred = (
            {
                module.module: unproven_member_bindings(
                    module,
                    owner_exposure_only=True,
                    incoming=bindings[module.module],
                    unsafe_providers=unsafe_providers,
                    include_creation_uncertainty=include_creation,
                )
                for module in modules.values()
            }
            for include_creation, bindings in (
                (True, exposed_bindings),
                (False, transferred_bindings),
            )
        )
        if (
            escaped == escaped_bindings
            and exposed == exposed_before
            and transferred == transferred_before
        ):
            break
        escaped_bindings = escaped
        exposed_bindings = {name: set(values) for name, values in exposed.items()}
        transferred_bindings = {name: set(values) for name, values in transferred.items()}
    return escaped_bindings


def _saturate_unknown_owner_namespaces(
    modules: Mapping[str, ParsedModule],
    namespace_bindings: Mapping[str, AbstractSet[str]],
    exposed_bindings: dict[str, set[str]],
    transferred_bindings: dict[str, set[str]],
) -> None:
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


def _unsafe_native_creation_providers(
    exposed_origins: AbstractSet[str], modules: Mapping[str, ParsedModule]
) -> set[str]:
    providers: set[str] = set()
    for native_origin in (NATIVE_DATACLASS_DECORATOR, NATIVE_TYPED_DICT_BASE):
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
    for item in imports:
        data = item["data"]
        targets: set[tuple[str, str]] = set()
        if data["symbol"] is None:
            origins = {data["target_module"]}
            for name, bindings in namespace_bindings.items():
                if in_scope(name, data["target_module"]):
                    targets |= {(name, binding) for binding in bindings}
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
                in_scope(origin, escaped) or (data["symbol"] is None and in_scope(escaped, origin))
            )
            for origin in origins
            for escaped in escaped_origins
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
    if not owner_exposure_only and data["symbol"] is not None and not framework:
        escaped |= {data["binding"]}
    if data["symbol"] is None or owner_exposure_only:
        base_bindings = (
            member_binding_closure(module.all_nodes, {data["binding"]}, member_surface=True)
            if owner_exposure_only
            else {data["binding"]}
        )
        for owner in module.all_nodes:
            if not isinstance(owner, ast.ClassDef) or (
                owner_exposure_only
                and native_owner_creation_static(module, owner, unsafe_providers)
            ):
                continue
            for base in owner.bases:
                head = base.value if isinstance(base, ast.Subscript) else base
                if any(
                    isinstance(node, ast.Name) and node.id in base_bindings
                    for node in ast.walk(head)
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
