# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Parsed-module primitives shared by the scanner and its context collector."""

from __future__ import annotations

import ast
import hashlib
import re
import sys
import sysconfig
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.machinery import BuiltinImporter, FrozenImporter
from pathlib import Path
from types import CodeType
from typing import Final, Literal, NamedTuple, Protocol, TypedDict

from archkeel.ir.facts import (
    DefinitionBranchKind,
    DefinitionContextKind,
    EvidenceClass,
    MethodDescriptor,
    MethodKind,
    PropertyBinding,
    PropertyOperation,
    PropertyOrigin,
    stable_id,
)
from archkeel.ir.facts_codec import RawData as RecordData
from archkeel.ir.facts_codec import (
    RawEvidence,
    RawRecord,
    classified,
    method_descriptor_data,
)
from archkeel.ir.facts_codec import (
    file_evidence as file_evidence,
)
from archkeel.ir.facts_codec import (
    record_evidence as record_evidence,
)
from archkeel.ir.protocol import PythonProviderSource
from archkeel.ir.source_records import FRAMEWORK_BASES as FRAMEWORK_BASES
from archkeel.ir.source_records import is_public_method_name as is_public_method_name

from .binding_types import AliasBinding as AliasBinding
from .binding_types import ImportKind


class _PropertyBinding(TypedDict):
    """One ordered operation on a statically named standard property binding."""

    operation: Literal["create", "getter", "setter"]
    source: Literal["new", "local", "base"]
    line: int
    source_line: int


FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
DefinitionNode = ast.ClassDef | FunctionNode


class DefinitionFrame(NamedTuple):
    """One AST context; Graph owns its separate evidence-bearing representation."""

    node: ast.AST
    kind: DefinitionContextKind
    branch: DefinitionBranchKind


DefinitionContexts = tuple[DefinitionFrame, ...]


class _DefinitionField(StrEnum):
    BODY = "body"
    ELSE = "orelse"
    HANDLER = "handlers"
    FINALLY = "finalbody"
    CASE = "cases"


_DEFINITION_FIELDS = {str(item): item for item in _DefinitionField}
_CONTROL_FLOW_KINDS = {
    ast.If: DefinitionContextKind.IF,
    ast.For: DefinitionContextKind.FOR,
    ast.AsyncFor: DefinitionContextKind.ASYNC_FOR,
    ast.While: DefinitionContextKind.WHILE,
    ast.Try: DefinitionContextKind.TRY,
    ast.TryStar: DefinitionContextKind.TRY_STAR,
    ast.With: DefinitionContextKind.WITH,
    ast.AsyncWith: DefinitionContextKind.ASYNC_WITH,
    ast.Match: DefinitionContextKind.MATCH,
}
_DEFINITION_BRANCHES = {
    _DefinitionField.BODY: DefinitionBranchKind.BODY,
    _DefinitionField.ELSE: DefinitionBranchKind.ELSE,
    _DefinitionField.HANDLER: DefinitionBranchKind.HANDLER,
    _DefinitionField.FINALLY: DefinitionBranchKind.FINALLY,
    _DefinitionField.CASE: DefinitionBranchKind.CASE,
}

NATIVE_DATACLASS_DECORATOR: Final = "dataclasses.dataclass"
NATIVE_TYPED_DICT_BASE: Final = "typing.TypedDict"
NATIVE_TYPED_DICT_BASES: Final = frozenset({NATIVE_TYPED_DICT_BASE, "typing_extensions.TypedDict"})
DATACLASS_DECORATORS: Final = frozenset(
    {NATIVE_DATACLASS_DECORATOR, "pydantic.dataclasses.dataclass"}
)
DATACLASS_OPTIONS: Final = frozenset(
    {
        "init",
        "repr",
        "eq",
        "order",
        "unsafe_hash",
        "frozen",
        "match_args",
        "kw_only",
        "slots",
        "weakref_slot",
    }
)


def location(node: ast.AST) -> tuple[int, int, int]:
    if not isinstance(
        node, ast.stmt | ast.expr | ast.excepthandler | ast.arg | ast.keyword | ast.pattern
    ):
        return 1, 1, 0
    line = max(node.lineno, 1)
    return line, node.end_lineno or line, node.col_offset


def definition_id(module: ParsedModule, node: ast.AST, qualified_name: str) -> str:
    """Collectors must agree on a definition site, even when its name is reused."""
    line, _, column = location(node)
    return stable_id("SYM", qualified_name, module.rel_path, line, column)


def call_id(module: ParsedModule, node: ast.Call, expression: str) -> str:
    """Nested calls may share evidence spans but must keep distinct identities."""
    line, _, column = location(node)
    return stable_id("CALL", module.rel_path, line, column, expression)


def definition_sites(
    node: ast.AST,
    parent: DefinitionNode | None = None,
    contexts: tuple[tuple[ast.AST, str, str], ...] = (),
) -> Iterator[tuple[DefinitionNode, DefinitionNode | None, DefinitionContexts]]:
    """Normalize the public legacy triple protocol once, before typed recursion."""
    normalized = tuple(
        DefinitionFrame(site, DefinitionContextKind(kind), DefinitionBranchKind(branch))
        for site, kind, branch in contexts
    )
    yield from _definition_sites(node, parent, normalized)


def _definition_sites(
    node: ast.AST,
    parent: DefinitionNode | None,
    contexts: DefinitionContexts,
) -> Iterator[tuple[DefinitionNode, DefinitionNode | None, DefinitionContexts]]:
    if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        yield node, parent, contexts
        parent = node
    for field_name, children in ast.iter_fields(node):
        field = _DEFINITION_FIELDS.get(field_name)
        if field is None or not isinstance(children, list):
            continue
        for child in children:
            if isinstance(child, ast.AST):
                nested = contexts
                if type(node) in _CONTROL_FLOW_KINDS:
                    nested = (*contexts, _branch_context(node, child, field))
                yield from _definition_sites(child, parent, nested)


def _branch_context(node: ast.AST, child: ast.AST, field_name: _DefinitionField) -> DefinitionFrame:
    site = (
        child
        if isinstance(child, ast.ExceptHandler)
        else child.pattern
        if isinstance(child, ast.match_case)
        else node
    )
    return DefinitionFrame(site, _CONTROL_FLOW_KINDS[type(node)], _DEFINITION_BRANCHES[field_name])


def control_flow_contexts(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> DefinitionContexts:
    contexts: list[DefinitionFrame] = []
    while node in parents:
        parent = parents[node]
        if type(parent) in _CONTROL_FLOW_KINDS:
            for field_name, children in ast.iter_fields(parent):
                field = _DEFINITION_FIELDS.get(field_name)
                if field is not None and isinstance(children, list) and node in children:
                    contexts.append(_branch_context(parent, node, field))
                    break
        node = parent
    return tuple(reversed(contexts))


def lexical_binding_names(node: DefinitionNode) -> frozenset[str]:
    """Visible binders invalidate a module lookup; this does not prove local values."""
    names = set(_bound_names(own_scope(node)))
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        args = node.args
        names.update(arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs))
        if args.vararg:
            names.add(args.vararg.arg)
        if args.kwarg:
            names.add(args.kwarg.arg)
    return frozenset(names)


def attribute_path(node: ast.Attribute) -> tuple[str, list[str]] | None:
    """Return a name-rooted attribute path used by state and private-attribute collectors."""
    attributes: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        attributes.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    return current.id, list(reversed(attributes))


def function_class_owners(tree: ast.Module, module_name: str) -> dict[int, str]:
    """Map each function node to its enclosing class, when it has one."""
    owners: dict[int, str] = {}

    class OwnerVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            qualified = (
                f"{self.stack[-1]}.{node.name}" if self.stack else f"{module_name}.{node.name}"
            )
            self.stack.append(qualified)
            self.generic_visit(node)
            self.stack.pop()

        def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            if self.stack:
                owners[id(node)] = self.stack[-1]
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_function(node)

    OwnerVisitor().visit(tree)
    return owners


def own_scope(node: DefinitionNode) -> Iterator[ast.AST]:
    """Walk a function's body, stopping at a nested function, lambda or class of its own.

    The unused-binding collector and the call collector both need this exact boundary: a
    name a nested scope binds or reads is not a fact about the outer function's own body,
    so both read it from here instead of each running its own version of the same walk.
    Nodes come in source order, so a receiver typed from an earlier binding is known by the
    time a later call result is typed from it (AD-40).
    """
    stack: list[ast.AST] = list(reversed(node.body))
    while stack:
        current = stack.pop()
        yield current
        if isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(current))))


class ScannedModule(Protocol):
    """The plain facts the shared package and module records read of any scanned module.

    Narrower than `ParsedModule` on purpose: a profile without a Python AST (AD-97) builds the
    same records from these six fields instead of fabricating a tree it does not have.
    """

    @property
    def rel_path(self) -> str: ...

    @property
    def module(self) -> str: ...

    @property
    def package(self) -> str: ...

    @property
    def all_exports(self) -> AbstractSet[str]: ...

    @property
    def all_literal(self) -> bool: ...

    @property
    def compatibility_logic_free(self) -> bool: ...


@dataclass
class ParsedModule:
    """The AST stays fixed for one snapshot; import and escape state can still change."""

    path: Path
    rel_path: str
    module: str
    package: str
    source: str
    source_bytes: bytes
    lines: list[str]
    tree: ast.Module
    aliases: dict[str, AliasBinding] = field(default_factory=dict)
    import_aliases: dict[ast.AST, dict[str, AliasBinding]] = field(default_factory=dict)
    all_exports: set[str] = field(default_factory=set)
    # AD-99: `all_exports` is the module's whole `__all__`, bound once to a literal.
    all_literal: bool = False
    compatibility_logic_free: bool = False
    incoming_member_escapes: set[str] = field(default_factory=set)
    owner_exposed_bindings: frozenset[str] | None = field(default=None, init=False, repr=False)
    _proven_map_union_expressions: frozenset[ast.expr] = field(
        default_factory=frozenset, init=False, repr=False
    )
    _proven_annotation_carriers: frozenset[ast.expr] = field(
        default_factory=frozenset, init=False, repr=False
    )
    _proven_callable_expressions: frozenset[ast.expr] = field(
        default_factory=frozenset, init=False, repr=False
    )
    _proven_callable_providers: frozenset[str] = field(
        default_factory=frozenset, init=False, repr=False
    )
    _proven_class_values: frozenset[ast.expr] = field(
        default_factory=frozenset, init=False, repr=False
    )
    _proven_constructor_returns: frozenset[ast.expr] = field(
        default_factory=frozenset, init=False, repr=False
    )
    _non_escaping_enum_values: frozenset[ast.Attribute] = field(
        default_factory=frozenset, init=False, repr=False
    )
    all_nodes: tuple[ast.AST, ...] = field(init=False, repr=False)
    scope_nodes: tuple[ast.AST, ...] = field(init=False, repr=False)
    bound_names: tuple[str, ...] = field(init=False, repr=False)
    binding_names: frozenset[str] | None = field(init=False, repr=False)
    global_names: frozenset[str] = field(init=False, repr=False)
    scope_bound_names: tuple[str, ...] = field(init=False, repr=False)
    unique_bindings: frozenset[str] = field(init=False, repr=False)
    _contained_owners: tuple[tuple[str, ast.AST], ...] = field(init=False, repr=False)
    _static_containment: frozenset[tuple[str, str]] = field(init=False, repr=False)
    stable_binding_cache: tuple[dict[str, AliasBinding], frozenset[str]] | None = field(
        default=None, init=False, repr=False
    )
    _dynamic_namespace_cache: tuple[dict[str, AliasBinding], bool] | None = field(
        default=None, init=False, repr=False
    )
    registry_cache: ModuleRegistry | None = field(default=None, init=False, repr=False)

    _lexical_scopes: tuple[ast.Module, str, str, str, ast.NodeVisitor] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        self.all_nodes = tuple(ast.walk(self.tree))
        self.scope_nodes = tuple(_module_scope_nodes(self.tree))
        self.bound_names = tuple(_bound_names(self.all_nodes))
        self.binding_names = (
            None
            if any(
                isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
                for node in self.all_nodes
            )
            else frozenset(self.bound_names)
        )
        self.global_names = frozenset(
            name for node in self.all_nodes if isinstance(node, ast.Global) for name in node.names
        )
        self.scope_bound_names = tuple(_bound_names(self.scope_nodes))
        self.unique_bindings = _unique_direct_module_bindings(self)
        self._contained_owners = tuple(_contained_member_owners(self, self.all_nodes))
        self._static_containment = _static_member_containment(
            self._contained_owners, self.all_nodes
        )


def unique_direct_module_bindings(module: ParsedModule) -> frozenset[str]:
    """Names with one direct definition or import and no competing binder in the module."""
    return module.unique_bindings


def _unique_direct_module_bindings(module: ParsedModule) -> frozenset[str]:
    nodes = module.all_nodes
    imports = [
        (name, node in module.tree.body)
        for node in nodes
        if isinstance(node, ast.Import | ast.ImportFrom)
        for name in _import_bindings(node)
    ]
    type_parameters = [
        value
        for node in nodes
        for field_name, value in ast.iter_fields(node)
        if field_name == "type_params" and value
    ]
    if (
        any(
            isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
            for node in nodes
        )
        or type_parameters
    ):
        return frozenset()
    direct = [
        node.name
        for node in nodes
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node in module.tree.body
    ] + [name for name, is_direct in imports if is_direct]
    counts = Counter(module.bound_names)
    return frozenset(name for name in direct if counts[name] == 1)


def stable_direct_module_bindings(
    module: ParsedModule, *, include_import_effects: bool = True
) -> frozenset[str]:
    """Names bound once at module level without a conditional or explicit global rebind."""
    if not include_import_effects:
        return _stable_direct_module_bindings(module, include_import_effects=False)
    cache = module.stable_binding_cache
    if cache is None or cache[0] != module.aliases:
        cache = (dict(module.aliases), _stable_direct_module_bindings(module))
        module.stable_binding_cache = cache
    return cache[1]


def static_overload_bindings(module: ParsedModule) -> frozenset[str]:
    """Complete native overload groups eligible for import-origin proof."""
    groups: dict[str, list[tuple[int, FunctionNode]]] = {}
    for index, statement in enumerate(module.tree.body):
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            group_sites: list[tuple[int, FunctionNode]] = groups.setdefault(statement.name, [])
            group_sites.append((index, statement))
    if not any(len(sites) >= 3 for sites in groups.values()):
        return frozenset()
    if (
        module.binding_names is None
        or any(
            value
            for node in module.all_nodes
            for field, value in ast.iter_fields(node)
            if field == "type_params"
        )
        or _namespace_may_rebind(module)
    ):
        return frozenset()
    counts = Counter(module.scope_bound_names)
    escaped = module.global_names | explicit_provider_escapes(module)
    generic_names = {
        name
        for node, name in module_scope_bindings(module)
        if isinstance(node, ast.Assign | ast.AnnAssign)
        and isinstance(node.value, ast.Call)
        and resolve_static_name(module, node.value.func)
        in {
            "typing.TypeVar",
            "typing_extensions.TypeVar",
            "typing.ParamSpec",
            "typing_extensions.ParamSpec",
            "typing.TypeVarTuple",
            "typing_extensions.TypeVarTuple",
        }
    }
    proven: set[str] = set()
    for name, sites in groups.items():
        if (
            len(sites) < 3
            or name in escaped
            or counts[name] != len(sites)
            or sites[-1][0] - sites[0][0] + 1 != len(sites)
        ):
            continue
        group = [node for _, node in sites]
        if _static_overload_group(module, group, generic_names):
            proven.add(name)
    return frozenset(proven)


def _static_overload_group(
    module: ParsedModule, group: Sequence[FunctionNode], generic_names: AbstractSet[str]
) -> bool:
    if (
        group[-1].decorator_list
        or any(type(node) is not type(group[-1]) for node in group)
        or any(
            isinstance(child, ast.Name) and child.id in generic_names
            for node in group
            for expression in _protected_type_expressions(list(ast.walk(node)))
            for child in ast.walk(expression)
        )
    ):
        return False
    return all(
        len(node.decorator_list) == 1
        and not isinstance(node.decorator_list[0], ast.Call)
        and is_proven_decorator(
            module,
            node.decorator_list[0],
            node,
            None,
            frozenset({"typing.overload", "typing_extensions.overload"}),
        )
        and all(
            isinstance(statement, ast.Pass)
            or isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and statement.value.value is Ellipsis
            for statement in node.body
        )
        for node in group[:-1]
    )


def _stable_direct_module_bindings(
    module: ParsedModule, *, include_import_effects: bool = True
) -> frozenset[str]:
    direct: dict[str, int] = {}
    for statement in module.tree.body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            direct[statement.name] = direct.get(statement.name, 0) + 1
        elif (
            sys.version_info >= (3, 12)
            and isinstance(statement, ast.TypeAlias)
            and not statement.type_params
        ):
            direct[statement.name.id] = direct.get(statement.name.id, 0) + 1
        elif isinstance(statement, ast.Import | ast.ImportFrom):
            for name in _import_bindings(statement):
                direct[name] = direct.get(name, 0) + 1
        elif isinstance(statement, ast.Assign | ast.AnnAssign):
            targets = (
                statement.targets if isinstance(statement, ast.Assign) else (statement.target,)
            )
            for target in targets:
                for name in _bound_names(ast.walk(target)):
                    direct[name] = direct.get(name, 0) + 1
    nodes = module.scope_nodes
    if any(
        isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
        for node in nodes
    ):
        return frozenset()
    counts = Counter(module.scope_bound_names)
    # ponytail: visible writes invalidate shared imports; prove scopes if false UNKNOWNs grow.
    if _namespace_may_rebind(module, include_import_effects=include_import_effects):
        return frozenset()
    changed_members = _member_binding_roots(module, module.all_nodes, member_surface=False)
    return frozenset(
        name
        for name, count in direct.items()
        if count == 1 and counts[name] == 1 and name not in module.global_names | changed_members
    )


def _namespace_may_rebind(module: ParsedModule, *, include_import_effects: bool = True) -> bool:
    """Whether a visible namespace exposure can rebind a module-level name.

    A `globals()` that only reads names cannot (AD-275). `locals()` and `vars()` stay exposures.
    """
    exposures = [
        node
        for node in module.all_nodes
        if exposes_dynamic_namespace(module, node, include_import_effects=include_import_effects)
    ] + [
        node
        for node in module.scope_nodes
        if exposes_dynamic_namespace(
            module, node, local_namespace=True, include_import_effects=include_import_effects
        )
    ]
    if not exposures:
        return False
    parents = {
        child: parent for parent in ast.walk(module.tree) for child in ast.iter_child_nodes(parent)
    }
    for node in exposures:
        call = parents.get(node)
        # The callee `globals` is judged with its call; `vars(x)` has only its callee to judge.
        read = call if isinstance(call, ast.Call) and call.func is node else node
        if not reads_only_namespace_names(module, read, parents):
            return True
    return False


def binding_may_exist_before(
    module: ParsedModule, statements: Sequence[ast.stmt], stop: ast.AST | None, name: str
) -> bool:
    if module.binding_names is not None and name not in module.binding_names:
        return False
    for statement in statements:
        if statement is stop:
            return False
        pending: list[ast.AST] = [statement]
        while pending:
            current = pending.pop()
            if isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef):
                if current.name == name:
                    return True
                pending.extend(current.decorator_list)
                pending.extend(current.args.defaults)
                pending.extend(value for value in current.args.kw_defaults if value is not None)
                pending.extend(
                    argument.annotation
                    for argument in [
                        *current.args.posonlyargs,
                        *current.args.args,
                        *current.args.kwonlyargs,
                    ]
                    if argument.annotation is not None
                )
                if current.args.vararg and current.args.vararg.annotation:
                    pending.append(current.args.vararg.annotation)
                if current.args.kwarg and current.args.kwarg.annotation:
                    pending.append(current.args.kwarg.annotation)
                if current.returns:
                    pending.append(current.returns)
                continue
            if isinstance(current, ast.ClassDef):
                if current.name == name:
                    return True
                if name in module.global_names and any(
                    isinstance(child, ast.Global) and name in child.names
                    for child in ast.walk(current)
                ):
                    return True
                pending.extend(current.decorator_list)
                pending.extend(current.bases)
                pending.extend(keyword.value for keyword in current.keywords)
                continue
            elif isinstance(current, ast.Lambda):
                pending.extend(current.args.defaults)
                pending.extend(value for value in current.args.kw_defaults if value is not None)
                continue
            if (
                isinstance(current, ast.Name)
                and current.id == name
                and isinstance(current.ctx, ast.Store | ast.Del)
            ):
                return True
            if isinstance(current, ast.Import) and any(
                (alias.asname or alias.name.split(".")[0]) == name for alias in current.names
            ):
                return True
            if isinstance(current, ast.ImportFrom) and any(
                alias.name != "*" and (alias.asname or alias.name) == name
                for alias in current.names
            ):
                return True
            if isinstance(current, ast.ImportFrom) and any(
                alias.name == "*" for alias in current.names
            ):
                return True
            if isinstance(current, ast.ExceptHandler) and current.name == name:
                return True
            if isinstance(current, ast.MatchAs) and current.name == name:
                return True
            if isinstance(current, ast.MatchStar) and current.name == name:
                return True
            if isinstance(current, ast.MatchMapping) and current.rest == name:
                return True
            pending.extend(ast.iter_child_nodes(current))
    return False


def is_proven_decorator(
    module: ParsedModule,
    decorator: ast.expr,
    method: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    parent: ast.ClassDef | None,
    targets: frozenset[str],
) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    resolved = resolve_static_name(module, target)
    if resolved not in targets:
        return False
    root = (
        target.id
        if isinstance(target, ast.Name)
        else (
            target.value.id
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
            else None
        )
    )
    if root is not None and root not in module.aliases:
        return (
            isinstance(decorator, ast.Name)
            and resolved in {"staticmethod", "classmethod", "property"}
            and not binding_may_exist_before(module, module.tree.body, None, root)
            and (parent is None or not binding_may_exist_before(module, parent.body, method, root))
        )
    if (
        root is None
        or root not in module.aliases
        or root not in stable_direct_module_bindings(module)
        or not binding_may_exist_before(module, module.tree.body, parent or method, root)
    ):
        return False
    return parent is None or not binding_may_exist_before(module, parent.body, method, root)


def class_definition_expressions(node: ast.ClassDef) -> list[ast.expr]:
    expressions = [*node.decorator_list, *node.bases, *(kw.value for kw in node.keywords)]
    for child in node.body:
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            expressions.extend(child.decorator_list)
            expressions.extend(child.args.defaults)
            expressions.extend(value for value in child.args.kw_defaults if value is not None)
            expressions.extend(
                arg.annotation
                for arg in [*child.args.posonlyargs, *child.args.args, *child.args.kwonlyargs]
                if arg.annotation is not None
            )
            if child.args.vararg and child.args.vararg.annotation:
                expressions.append(child.args.vararg.annotation)
            if child.args.kwarg and child.args.kwarg.annotation:
                expressions.append(child.args.kwarg.annotation)
            if child.returns:
                expressions.append(child.returns)
        elif isinstance(child, ast.ClassDef):
            expressions.extend(child.decorator_list)
            expressions.extend(child.bases)
            expressions.extend(kw.value for kw in child.keywords)
        elif isinstance(child, ast.AnnAssign):
            expressions.append(child.annotation)
            expressions.append(child.target)
            if child.value is not None:
                expressions.append(child.value)
        elif isinstance(child, ast.Assign):
            expressions.extend(child.targets)
            expressions.append(child.value)
        elif isinstance(child, ast.Expr):
            expressions.append(child.value)
        elif isinstance(child, ast.Delete):
            expressions.extend(child.targets)
    return expressions


def _class_statement_bindings(
    child: ast.stmt | ast.NamedExpr,
    *,
    inert_values: bool = False,
    member_surface: bool = True,
    proven_values: AbstractSet[ast.expr] = frozenset(),
) -> tuple[list[str], bool, bool] | None:
    if (
        isinstance(child, ast.Assign | ast.AnnAssign | ast.NamedExpr)
        and child.value is not None
        and not isinstance(child.value, ast.Constant | ast.List | ast.Tuple | ast.Set | ast.Dict)
        and not (inert_values and _inert_creation_operand(child.value))
        and child.value not in proven_values
        and (
            not isinstance(child.value, ast.Lambda)
            or member_surface
            and any(
                is_public_method_name(name.id)
                for target in (child.targets if isinstance(child, ast.Assign) else (child.target,))
                for name in ast.walk(target)
                if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store)
            )
        )
    ):
        return None
    if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        is_function = isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
        return [child.name], is_function, is_function and "overload" in decorator_names(child)
    if isinstance(child, ast.AnnAssign):
        names = (
            [name.id for name in ast.walk(child.target) if isinstance(name, ast.Name)]
            if child.value is not None
            else []
        )
        return names, False, False
    if isinstance(child, ast.Assign | ast.NamedExpr):
        names = [
            name.id
            for target in (child.targets if isinstance(child, ast.Assign) else (child.target,))
            for name in ast.walk(target)
            if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store)
        ]
        return names, False, False
    if isinstance(child, ast.Import):
        if any(alias.asname is None and "." in alias.name for alias in child.names):
            return None
        return [alias.asname or alias.name for alias in child.names], False, False
    if isinstance(child, ast.ImportFrom):
        if any(alias.name == "*" for alias in child.names):
            return None
        return [alias.asname or alias.name for alias in child.names], False, False
    if isinstance(child, ast.Delete) or _bound_names(ast.walk(child)):
        return None
    return [], False, False


def _unproven_class_expressions(
    module: ParsedModule, node: ast.ClassDef, *, inert_values: bool
) -> bool:
    return any(
        isinstance(item, ast.NamedExpr)
        and not (inert_values and _inert_creation_operand(item))
        or exposes_dynamic_namespace(module, item, local_namespace=True)
        for expr in class_definition_expressions(node)
        for item in ast.walk(expr)
    )


def unproven_class_body(
    module: ParsedModule, node: ast.ClassDef, *, inert_values: bool = False
) -> bool:
    """Keep member binding and class-creation transformations conservative."""
    if _unproven_class_expressions(module, node, inert_values=inert_values):
        return True
    if any(
        isinstance(
            child,
            ast.If
            | ast.For
            | ast.AsyncFor
            | ast.While
            | ast.With
            | ast.AsyncWith
            | ast.Try
            | ast.TryStar
            | ast.Match,
        )
        for child in node.body
    ):
        return True
    properties = property_bindings(module, node)
    bindings: dict[str, tuple[int, int, int, bool, bool]] = {}
    for child in node.body:
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) and (
            child.name in {"__init_subclass__", "__class_getitem__"}
            or (child not in properties and _method_signature(module, child, node)[1] is not True)
        ):
            return True
        if (
            isinstance(child, ast.Assign | ast.AnnAssign)
            and child.value is not None
            and any(
                isinstance(item, ast.NamedExpr)
                and not (inert_values and _inert_creation_operand(item))
                for item in ast.walk(child.value)
            )
        ):
            return True
        statement_bindings = _class_statement_bindings(
            child, inert_values=inert_values, proven_values=module._proven_class_values
        )
        if statement_bindings is None:
            return True
        names, is_function, overloaded = statement_bindings
        if "__slots__" in names:
            return True
        for name in names:
            count, overload_count, implementation_count, _, all_functions = (
                bindings[name] if name in bindings else (0, 0, 0, False, True)
            )
            bindings[name] = (
                count + 1,
                overload_count + int(overloaded),
                implementation_count + int(not overloaded),
                overloaded,
                all_functions and is_function,
            )
    return any(
        count > 1
        and sum(method.name == name for method in properties) != count
        and not (
            all_functions
            and overload_count == count - 1
            and implementation_count == 1
            and not last_overload
        )
        for name, (
            count,
            overload_count,
            implementation_count,
            last_overload,
            all_functions,
        ) in bindings.items()
    )


def property_bindings(
    module: ParsedModule, parent: ast.ClassDef
) -> dict[FunctionNode, PropertyBinding]:
    if parent not in module.tree.body:
        return {}
    bindings: dict[FunctionNode, PropertyBinding] = {}
    previous: dict[str, FunctionNode] = {}
    for child in parent.body:
        names = _class_statement_bindings(child)
        if not isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            for name in names[0] if names is not None else tuple(previous):
                previous.pop(name, None)
            continue
        binding = _property_operation(module, child, parent, previous, bindings)
        if binding is not None:
            bindings[child] = binding
        previous[child.name] = child
    return bindings


def _property_operation(
    module: ParsedModule,
    node: FunctionNode,
    parent: ast.ClassDef,
    previous: dict[str, FunctionNode],
    bindings: dict[FunctionNode, PropertyBinding],
) -> PropertyBinding | None:
    if len(node.decorator_list) != 1 or isinstance(node, ast.AsyncFunctionDef):
        return None
    decorator = node.decorator_list[0]
    if is_proven_decorator(
        module, decorator, node, parent, frozenset({"property", "builtins.property"})
    ) and not isinstance(decorator, ast.Call):
        return PropertyBinding(PropertyOperation.CREATE, PropertyOrigin.NEW, node.lineno, 0)
    if not isinstance(decorator, ast.Attribute):
        return None
    try:
        operation = PropertyOperation(decorator.attr)
    except ValueError:
        return None
    if operation is PropertyOperation.CREATE:
        return None
    descriptor = decorator.value
    if isinstance(descriptor, ast.Name) and descriptor.id == node.name:
        origin = previous.get(node.name)
        if origin is not None and origin in bindings:
            return PropertyBinding(operation, PropertyOrigin.LOCAL, node.lineno, origin.lineno)
    if (
        isinstance(descriptor, ast.Attribute)
        and descriptor.attr == node.name
        and len(parent.bases) == 1
        and ast.dump(descriptor.value) == ast.dump(parent.bases[0])
    ):
        root = descriptor.value
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name) and not binding_may_exist_before(
            module, parent.body, node, root.id
        ):
            return PropertyBinding(operation, PropertyOrigin.BASE, node.lineno, 0)
    return None


def setter_local_references(module: ParsedModule) -> frozenset[ast.AST]:
    references: set[ast.AST] = set()
    for owner in module.tree.body:
        if not isinstance(owner, ast.ClassDef):
            continue
        bindings = property_bindings(module, owner)
        for method, binding in bindings.items():
            positional = (*method.args.posonlyargs, *method.args.args)
            parameters = (*positional[1:], *method.args.kwonlyargs)
            if binding.operation is not PropertyOperation.SETTER or method.name not in {
                argument.arg for argument in parameters
            }:
                continue
            nodes = tuple(own_scope(method))
            if any(
                isinstance(node, ast.Global | ast.Nonlocal) and method.name in node.names
                for node in nodes
            ):
                continue
            nested = {
                child
                for node in nodes
                if isinstance(node, ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp)
                for child in ast.walk(node)
            }
            references.update(
                node
                for node in nodes
                if isinstance(node, ast.Name) and node.id == method.name and node not in nested
            )
    return frozenset(references)


_METHOD_DECORATORS: Final[dict[str, MethodKind | None]] = {
    "staticmethod": MethodKind.STATIC,
    "builtins.staticmethod": MethodKind.STATIC,
    "classmethod": MethodKind.CLASS,
    "builtins.classmethod": MethodKind.CLASS,
    "property": MethodKind.INSTANCE,
    "builtins.property": MethodKind.INSTANCE,
    "typing.overload": None,
    "typing_extensions.overload": None,
    "abc.abstractmethod": None,
}


def _method_signature(
    module: ParsedModule,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parent: ast.ClassDef | None,
) -> tuple[MethodKind, bool]:
    method_kind = MethodKind.INSTANCE
    signature_proven = True
    descriptor_count = 0
    targets = frozenset(_METHOD_DECORATORS)
    for decorator in node.decorator_list:
        proven = not isinstance(decorator, ast.Call) and is_proven_decorator(
            module, decorator, node, parent, targets
        )
        signature_proven = signature_proven and proven
        if proven:
            effect = _METHOD_DECORATORS[resolve_static_name(module, decorator)]
            if effect is not None:
                descriptor_count += 1
                if effect in (MethodKind.STATIC, MethodKind.CLASS):
                    method_kind = effect
    return method_kind, signature_proven and descriptor_count <= 1


def method_descriptor(
    module: ParsedModule,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parent: ast.ClassDef | None,
) -> MethodDescriptor:
    method_kind, signature_proven = _method_signature(module, node, parent)
    properties = property_bindings(module, parent) if parent is not None else {}
    binding = properties.get(node)
    if (
        binding is not None
        and parent is not None
        and parent.name not in stable_direct_module_bindings(module)
    ):
        binding = None
    return MethodDescriptor(
        method_kind,
        signature_proven,
        not node.decorator_list
        and parent is not None
        and parent in module.tree.body
        and parent.name in stable_direct_module_bindings(module)
        and not binding_may_exist_before(module, tuple(reversed(parent.body)), node, node.name),
        binding,
    )


def method_decorator_data(
    module: ParsedModule,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parent: ast.ClassDef | None,
) -> RecordData:
    """Retain the raw dict port for callers assembling source wire records."""
    return method_descriptor_data(method_descriptor(module, node, parent))


def explicit_provider_escapes(module: ParsedModule) -> frozenset[str]:
    # Header identity does not assert future owner-namespace or member immutability.
    return frozenset(
        member_binding_closure(
            module.all_nodes,
            _unproven_member_roots(
                module,
                module.all_nodes,
                member_surface=True,
                owner_exposure_only=True,
                unsafe_providers=frozenset(),
                include_creation_uncertainty=False,
            ),
            member_surface=True,
            local_references=setter_local_references(module),
        )
    )


def typed_dict_header_static(
    module: ParsedModule, node: ast.ClassDef, unsafe_providers: AbstractSet[str]
) -> bool:
    if (
        node not in module.tree.body
        or node.name not in unique_direct_module_bindings(module)
        or node.name not in stable_direct_module_bindings(module)
        or node.decorator_list
        or len(node.bases) != 1
        or not (
            not node.keywords
            and resolve_static_name(module, node.bases[0]) in NATIVE_TYPED_DICT_BASES
            or len(node.keywords) == 1
            and node.keywords[0].arg == "total"
            and isinstance(node.keywords[0].value, ast.Constant)
            and isinstance(node.keywords[0].value.value, bool)
        )
    ):
        return False
    base = node.bases[0]
    root = base.value if isinstance(base, ast.Attribute) else base
    origin: str = resolve_static_name(module, base)
    return (
        isinstance(root, ast.Name)
        and root.id in unique_direct_module_bindings(module)
        and origin in NATIVE_TYPED_DICT_BASES
        and origin.rpartition(".")[0] not in unsafe_providers
        and root.id not in explicit_provider_escapes(module)
        and is_proven_decorator(module, base, node, None, frozenset({origin}))
    )


def class_header_static(node: ast.ClassDef) -> bool:
    return not node.decorator_list and not node.keywords


def _class_members_receive_owner(module: ParsedModule, owner: ast.ClassDef) -> bool:
    for node in _module_scope_nodes(ast.Module(body=owner.body, type_ignores=[])):
        if exposes_dynamic_namespace(module, node, local_namespace=True):
            return True
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            _, signature_proven = _method_signature(module, node, owner)
            if signature_proven is not True and node not in property_bindings(module, owner):
                return True
        elif isinstance(node, ast.ClassDef):
            if not class_header_static(node) or node.bases:
                return True
        elif isinstance(node, ast.Import | ast.ImportFrom):
            return True
        elif (
            isinstance(node, ast.Assign | ast.AnnAssign | ast.NamedExpr) and node.value is not None
        ):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            if not all(isinstance(target, ast.Name) for target in targets):
                if not _inert_creation_operand(node.value):
                    return True
            elif (
                _class_statement_bindings(
                    node,
                    inert_values=True,
                    member_surface=False,
                    proven_values=module._proven_class_values,
                )
                is None
            ):
                return True
        elif isinstance(node, ast.stmt) and _class_statement_bindings(node) is None:
            return True
    return False


def class_namespace_static(module: ParsedModule, owner: ast.ClassDef) -> bool:
    if _class_members_receive_owner(module, owner):
        return False
    nodes = list(_module_scope_nodes(ast.Module(body=owner.body, type_ignores=[])))
    annotation_targets = {
        node.target
        for node in nodes
        if isinstance(node, ast.AnnAssign)
        and node.value is None
        and isinstance(node.target, ast.Name)
    }
    return "__module__" not in _bound_names(
        node for node in nodes if node not in annotation_targets
    )


def _class_base_operands_static(module: ParsedModule, node: ast.ClassDef) -> bool:
    bound = frozenset(module.bound_names)
    stable = stable_direct_module_bindings(module) & unique_direct_module_bindings(module)
    custom = 0
    for base in node.bases:
        head = base.value if isinstance(base, ast.Subscript) else base
        root = head
        while isinstance(root, ast.Attribute):
            root = root.value
        if not (
            resolve_static_name(module, head) in FRAMEWORK_BASES
            and isinstance(root, ast.Name)
            and (root.id not in bound or (root.id in module.aliases and root.id in stable))
        ):
            custom += 1
    return custom <= 1


def class_creation_static(
    module: ParsedModule,
    node: ast.ClassDef,
    *,
    owner_exposure_only: bool,
    unsafe_providers: AbstractSet[str],
) -> bool:
    if (
        len(node.bases) == 1
        and resolve_static_name(module, node.bases[0]) in NATIVE_TYPED_DICT_BASES
    ):
        return native_owner_creation_static(module, node, unsafe_providers)
    return (
        class_header_static(node)
        and not unproven_class_body(module, node)
        and _class_base_operands_static(module, node)
    ) or (owner_exposure_only and native_owner_creation_static(module, node, unsafe_providers))


def _inert_creation_operand(node: ast.expr) -> bool:
    if isinstance(node, ast.Lambda):
        return all(
            _inert_creation_operand(value)
            for value in (*node.args.defaults, *node.args.kw_defaults)
            if value is not None
        )
    if isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
        node = node.value
    if any(isinstance(item, ast.Call) for item in ast.walk(node)):
        return False
    try:
        ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, RecursionError):
        return False
    return True


def _deferred_creation_annotation(module: ParsedModule, node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        or any(
            isinstance(statement, ast.ImportFrom)
            and statement.module == "__future__"
            and any(alias.name == "annotations" for alias in statement.names)
            for statement in module.tree.body
        )
    )


def _native_method_header_static(module: ParsedModule, node: FunctionNode) -> bool:
    arguments = [
        *node.args.posonlyargs,
        *node.args.args,
        *node.args.kwonlyargs,
        *(item for item in (node.args.vararg, node.args.kwarg) if item is not None),
    ]
    return (
        method_descriptor(module, node, None).signature_decorators_proven is True
        and all(
            _inert_creation_operand(value)
            for value in [
                *node.args.defaults,
                *(item for item in node.args.kw_defaults if item is not None),
            ]
        )
        and all(
            _deferred_creation_annotation(module, value) or _inert_creation_operand(value)
            for value in _protected_type_expressions([node, *arguments])
        )
    )


def _native_class_body_static(module: ParsedModule, node: ast.ClassDef) -> bool:
    if unproven_class_body(module, node, inert_values=True):
        return False
    for child in node.body:
        if isinstance(child, ast.Pass) or (
            isinstance(child, ast.Expr)
            and isinstance(child.value, ast.Constant)
            and isinstance(child.value.value, str)
        ):
            continue
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            if not _native_method_header_static(module, child):
                return False
        elif isinstance(child, ast.Assign):
            if not all(isinstance(target, ast.Name) for target in child.targets) or not (
                _inert_creation_operand(child.value) or child.value in module._proven_class_values
            ):
                return False
        elif isinstance(child, ast.AnnAssign):
            if (
                not isinstance(child.target, ast.Name)
                or not (
                    _deferred_creation_annotation(module, child.annotation)
                    or _inert_creation_operand(child.annotation)
                )
                or (
                    child.value is not None
                    and not _inert_creation_operand(child.value)
                    and child.value not in module._proven_class_values
                )
            ):
                return False
        else:
            return False
    return True


def native_dataclass_header_static(
    module: ParsedModule, node: ast.ClassDef, unsafe_providers: AbstractSet[str]
) -> bool:
    if node not in module.tree.body or node.bases or node.keywords or len(node.decorator_list) != 1:
        return False
    decorator = node.decorator_list[0]
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if "dataclasses" in unsafe_providers or not _native_factory_binding_static(
        module, node, decorator, target, NATIVE_DATACLASS_DECORATOR
    ):
        return False
    return not (
        isinstance(decorator, ast.Call)
        and (
            decorator.args
            or any(
                keyword.arg not in DATACLASS_OPTIONS
                or not isinstance(keyword.value, ast.Constant)
                or not isinstance(keyword.value.value, bool)
                for keyword in decorator.keywords
            )
        )
    )


def native_owner_creation_static(
    module: ParsedModule, node: ast.ClassDef, unsafe_providers: AbstractSet[str]
) -> bool:
    if node not in module.tree.body:
        return False
    if native_dataclass_header_static(module, node, unsafe_providers):
        return _native_class_body_static(module, node)
    if (
        len(node.bases) == 1
        and resolve_static_name(module, node.bases[0]) in NATIVE_TYPED_DICT_BASES
    ):
        return typed_dict_header_static(module, node, unsafe_providers) and all(
            isinstance(child, ast.Pass)
            or (
                isinstance(child, ast.Expr)
                and isinstance(child.value, ast.Constant)
                and isinstance(child.value.value, str)
            )
            or (
                isinstance(child, ast.AnnAssign)
                and isinstance(child.target, ast.Name)
                and child.value is None
                and (
                    _deferred_creation_annotation(module, child.annotation)
                    or _bare_builtin(
                        module, child.annotation, {"str", "int", "float", "bool", "bytes", "object"}
                    )
                )
            )
            for child in node.body
        )
    return False


def _native_factory_binding_static(
    module: ParsedModule,
    owner: ast.ClassDef,
    expression: ast.expr,
    target: ast.expr,
    origin: str,
) -> bool:
    return (
        isinstance(target, ast.Name)
        and target.id in unique_direct_module_bindings(module)
        and is_proven_decorator(module, expression, owner, None, frozenset({origin}))
    )


def native_typed_dict_provider_static(
    module: ParsedModule, binding: str, unsafe_providers: AbstractSet[str]
) -> bool:
    return any(
        isinstance(owner, ast.ClassDef)
        and len(owner.bases) == 1
        and resolve_static_name(module, owner.bases[0]) in NATIVE_TYPED_DICT_BASES
        and any(
            isinstance(node, ast.Name) and node.id == binding for node in ast.walk(owner.bases[0])
        )
        and native_owner_creation_static(module, owner, unsafe_providers)
        for owner in module.tree.body
    )


def _protected_type_expressions(nodes: Sequence[ast.AST]) -> list[ast.expr]:
    expressions = [
        node.annotation
        for node in nodes
        if isinstance(node, ast.arg | ast.AnnAssign) and node.annotation is not None
    ] + [
        node.returns
        for node in nodes
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.returns is not None
    ]
    if sys.version_info >= (3, 12):
        expressions += [node.value for node in nodes if isinstance(node, ast.TypeAlias)]
    return expressions


def _contained_member_owners(
    module: ParsedModule, nodes: Sequence[ast.AST]
) -> list[tuple[str, ast.AST]]:
    owners: list[tuple[str, ast.AST]] = [
        (node.name, node)
        for node in nodes
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    module_nodes = frozenset(module.scope_nodes)
    owners += [
        (target.id, node.value)
        for node in nodes
        if isinstance(node, ast.Assign | ast.AnnAssign | ast.NamedExpr)
        and node.value is not None
        and any(isinstance(value, ast.Lambda) for value in ast.walk(node.value))
        for expression in (node.targets if isinstance(node, ast.Assign) else (node.target,))
        for target in ast.walk(expression)
        if isinstance(target, ast.Name)
        and (isinstance(target.ctx, ast.Store) or node in module_nodes)
    ]
    if sys.version_info >= (3, 12):
        owners += [(node.name.id, node) for node in nodes if isinstance(node, ast.TypeAlias)]
    return owners


def _static_member_containment(
    owners: Sequence[tuple[str, ast.AST]],
    nodes: Sequence[ast.AST],
) -> frozenset[tuple[str, str]]:
    contained = {
        (name, target.id)
        for name, owner in owners
        for expression in [
            *_protected_type_expressions(list(ast.walk(owner))),
            *(owner.bases if isinstance(owner, ast.ClassDef) else ()),
        ]
        for target in ast.walk(expression)
        if isinstance(target, ast.Name) and isinstance(target.ctx, ast.Load)
    }
    contained |= {
        (target.id, owner.name)
        for owner in nodes
        if isinstance(owner, ast.ClassDef)
        for base in owner.bases
        for target in ast.walk(base.value if isinstance(base, ast.Subscript) else base)
        if isinstance(target, ast.Name) and isinstance(target.ctx, ast.Load)
    }
    return frozenset(contained)


def _contained_member_roots(
    module: ParsedModule,
    nodes: Sequence[ast.AST],
    *,
    owner_exposure_only: bool = False,
    unsafe_providers: AbstractSet[str] = frozenset(),
) -> tuple[set[tuple[str, str]], set[str]]:
    if nodes is module.all_nodes:
        owners = module._contained_owners
        contained = set(module._static_containment)
    else:
        owners = tuple(_contained_member_owners(module, nodes))
        contained = set(_static_member_containment(owners, nodes))
    contained |= {
        (name, target.id)
        for node, name in module_scope_bindings(module)
        if (value := admitted_type_alias_value(module, node)) is not None
        and value
        in module._proven_map_union_expressions
        | module._proven_callable_expressions
        | module._proven_class_values
        for target in ast.walk(value)
        if isinstance(target, ast.Name) and isinstance(target.ctx, ast.Load)
    }
    # Native functions expose their defining namespace, including through a class's methods.
    uncertain_bases = member_binding_closure(
        nodes,
        module.incoming_member_escapes,
        member_surface=True,
        local_references=setter_local_references(module),
    )
    namespace_owners = {
        name
        for name, owner in owners
        if (
            owner_exposure_only
            and isinstance(owner, ast.ClassDef)
            and (
                not class_creation_static(
                    module, owner, owner_exposure_only=False, unsafe_providers=unsafe_providers
                )
                or any(
                    isinstance(target, ast.Name) and target.id in uncertain_bases
                    for base in owner.bases
                    for target in ast.walk(base.value if isinstance(base, ast.Subscript) else base)
                )
            )
        )
        or any(
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda)
            for node in ast.walk(owner)
        )
    }
    return contained, namespace_owners


def unproven_member_bindings(
    module: ParsedModule,
    *,
    owner_exposure_only: bool = False,
    incoming: AbstractSet[str] | None = None,
    unsafe_providers: AbstractSet[str] = frozenset(),
    include_creation_uncertainty: bool = True,
) -> frozenset[str]:
    """Visible member escapes, independent of whether an import binds unconditionally."""
    nodes = module.all_nodes
    cached = module._dynamic_namespace_cache
    if cached is None or cached[0] != module.aliases:
        # Syntax is fixed; aliases can still change while imports converge.
        cached = (
            dict(module.aliases),
            any(exposes_dynamic_namespace(module, node, member_surface=True) for node in nodes)
            or any(
                exposes_dynamic_namespace(module, node, local_namespace=True)
                for node in module.scope_nodes
            ),
        )
        module._dynamic_namespace_cache = cached
    if cached[1]:
        return frozenset(module.bound_names)
    return frozenset(
        _member_binding_roots(
            module,
            nodes,
            member_surface=True,
            owner_exposure_only=owner_exposure_only,
            incoming=incoming,
            unsafe_providers=unsafe_providers,
            include_creation_uncertainty=include_creation_uncertainty,
        )
    )


def _member_binding_roots(
    module: ParsedModule,
    nodes: Sequence[ast.AST],
    *,
    member_surface: bool,
    owner_exposure_only: bool = False,
    incoming: AbstractSet[str] | None = None,
    unsafe_providers: AbstractSet[str] = frozenset(),
    include_creation_uncertainty: bool = True,
) -> set[str]:
    changed_members = _unproven_member_roots(
        module,
        nodes,
        member_surface=member_surface,
        owner_exposure_only=owner_exposure_only,
        unsafe_providers=unsafe_providers,
        include_creation_uncertainty=include_creation_uncertainty,
    )
    contained, namespace_owners = (
        _contained_member_roots(
            module,
            nodes,
            owner_exposure_only=owner_exposure_only,
            unsafe_providers=unsafe_providers,
        )
        if member_surface
        else (set(), set())
    )
    if member_surface:
        changed_members |= module.incoming_member_escapes if incoming is None else incoming
    changed_members = member_binding_closure(
        nodes,
        changed_members,
        member_surface=member_surface,
        contained=contained,
        local_references=setter_local_references(module) if member_surface else frozenset(),
        namespace_owners=namespace_owners,
        namespace_bindings=frozenset(module.scope_bound_names) if member_surface else frozenset(),
    )
    changed_origins: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            for imported_alias in node.names:
                imported_name: str = imported_alias.name
                root = imported_name.split(".")[0]
                binding = imported_alias.asname or root
                if binding in changed_members:
                    changed_origins |= {imported_name if imported_alias.asname else root}
    for name, alias in module.aliases.items():
        imported_target: str = alias.target
        origin = (
            imported_target
            if alias.kind is ImportKind.MODULE
            else imported_target.rpartition(".")[0]
        )
        if origin in changed_origins:
            changed_members |= {name}
    return changed_members


def member_binding_closure(
    nodes: Sequence[ast.AST],
    roots: AbstractSet[str],
    *,
    member_surface: bool,
    contained: AbstractSet[tuple[str, str]] = frozenset(),
    local_references: AbstractSet[ast.AST] = frozenset(),
    namespace_owners: AbstractSet[str] = frozenset(),
    namespace_bindings: AbstractSet[str] = frozenset(),
) -> set[str]:
    changed_members = set(roots)
    if not changed_members:
        return changed_members
    aliases = {
        (target.id, value.id)
        for node in nodes
        if isinstance(node, ast.Assign | ast.AnnAssign)
        and (
            isinstance(node.value, ast.Name)
            or (member_surface and isinstance(node.value, ast.Attribute))
        )
        for target in (node.targets if isinstance(node, ast.Assign) else (node.target,))
        if isinstance(target, ast.Name) and target not in local_references
        for value in ast.walk(node.value)
        if isinstance(value, ast.Name) and value not in local_references
    }
    adjacent: dict[str, set[str]] = {}
    for name, value in aliases:
        names: set[str] = adjacent.setdefault(name, set())
        names.add(value)
        values: set[str] = adjacent.setdefault(value, set())
        values.add(name)
    for owner, value in contained:
        children: set[str] = adjacent.setdefault(owner, set())
        children.add(value)
    pending = list(changed_members)
    namespace_expanded = False
    while pending:
        current = pending.pop()
        if not namespace_expanded and current in namespace_owners:
            # Every exposing owner reaches the same namespace; expand this fanout once.
            namespace_expanded = True
            for binding in namespace_bindings:
                if binding not in changed_members:
                    changed_members.add(binding)
                    pending.append(binding)
        for value in adjacent.get(current, ()):
            if value not in changed_members:
                changed_members.add(value)
                pending.append(value)
    return changed_members


def bound_once_before(statements: Sequence[ast.stmt], stop: ast.AST, name: str) -> bool:
    """Prove one direct module binding exists before a class definition."""
    count = 0
    for statement in statements:
        if statement is stop:
            return count == 1
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            bindings = [statement.name]
        elif isinstance(statement, ast.Import | ast.ImportFrom):
            if isinstance(statement, ast.ImportFrom) and any(
                alias.name == "*" for alias in statement.names
            ):
                return False
            bindings = [
                alias.asname
                or (alias.name.split(".")[0] if isinstance(statement, ast.Import) else alias.name)
                for alias in statement.names
            ]
        elif isinstance(statement, ast.Assign | ast.AnnAssign):
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            bindings = [
                child.id
                for target in targets
                for child in ast.walk(target)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
            ]
        else:
            if any(
                isinstance(child, ast.Name)
                and child.id == name
                and isinstance(child.ctx, ast.Store | ast.Del)
                for child in ast.walk(statement)
            ):
                return False
            continue
        count += bindings.count(name)
        if count > 1:
            return False
    return False


def generic_parameters(module: ParsedModule, node: ast.ClassDef) -> list[str]:
    """Return verified TypeVars from one explicit ``Generic[...]`` base."""
    typevars: set[str] = set()
    for statement in module.tree.body:
        if not isinstance(statement, ast.Assign | ast.AnnAssign):
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        if len(targets) != 1 or not isinstance(targets[0], ast.Name):
            continue
        name = targets[0].id
        value = statement.value
        if not isinstance(value, ast.Call):
            continue
        typevar_root = (
            value.func.id
            if isinstance(value.func, ast.Name)
            else value.func.value.id
            if isinstance(value.func, ast.Attribute) and isinstance(value.func.value, ast.Name)
            else None
        )
        if (
            not isinstance(typevar_root, str)
            or not bound_once_before(module.tree.body, statement, typevar_root)
            or resolve_static_name(module, value.func)
            not in {"typing.TypeVar", "typing_extensions.TypeVar"}
            or not value.args
            or not isinstance(value.args[0], ast.Constant)
            or value.args[0].value != name
            or not bound_once_before(module.tree.body, node, name)
        ):
            continue
        typevars.add(name)

    generic_bases = [
        base
        for base in node.bases
        if isinstance(base, ast.Subscript)
        and resolve_static_name(module, base.value)
        in {"typing.Generic", "typing_extensions.Generic"}
    ]
    if len(generic_bases) != 1:
        return []
    root = generic_bases[0].value
    root_name = (
        root.id
        if isinstance(root, ast.Name)
        else root.value.id
        if isinstance(root, ast.Attribute) and isinstance(root.value, ast.Name)
        else None
    )
    if not isinstance(root_name, str) or not bound_once_before(module.tree.body, node, root_name):
        return []
    arguments = generic_bases[0].slice
    values = list(arguments.elts) if isinstance(arguments, ast.Tuple) else [arguments]
    names = [value.id for value in values if isinstance(value, ast.Name)]
    if len(names) != len(values) or len(set(names)) != len(names) or not set(names) <= typevars:
        return []
    return names


def _native_generic_base_static(
    module: ParsedModule,
    expression: ast.expr,
    owner: ast.ClassDef,
    unsafe_providers: AbstractSet[str],
    visited: frozenset[str] = frozenset(),
) -> bool:
    if "typing" in unsafe_providers:
        return False
    head = expression.value if isinstance(expression, ast.Subscript) else expression
    if is_proven_decorator(module, head, owner, None, frozenset({"typing.Generic"})):
        return True
    if not isinstance(head, ast.Name) or head.id in visited:
        return False
    definitions = [
        node for node in module.tree.body if isinstance(node, ast.ClassDef) and node.name == head.id
    ]
    if len(definitions) != 1 or not bound_once_before(module.tree.body, owner, head.id):
        return False
    [definition] = definitions
    if (
        not generic_parameters(module, definition)
        or not class_creation_static(
            module, definition, owner_exposure_only=True, unsafe_providers=unsafe_providers
        )
        or any(
            name[:2] == "__"
            for child in definition.body
            if (bindings := _class_statement_bindings(child)) is not None
            for name in bindings[0]
        )
    ):
        return False
    return all(
        _native_generic_base_static(module, base, definition, unsafe_providers, visited | {head.id})
        for base in definition.bases
    )


def _protected_class_owner_references(
    module: ParsedModule, unsafe_providers: AbstractSet[str]
) -> set[ast.AST]:
    protected: set[ast.AST] = set()
    plain_classes = {
        owner.name
        for owner in module.tree.body
        if isinstance(owner, ast.ClassDef)
        and not owner.bases
        and class_header_static(owner)
        and owner.name in unique_direct_module_bindings(module)
        and class_creation_static(
            module, owner, owner_exposure_only=True, unsafe_providers=frozenset()
        )
    }
    for owner in module.tree.body:
        if not isinstance(owner, ast.ClassDef):
            continue
        parameters = generic_parameters(module, owner)
        for base in owner.bases:
            if not isinstance(base, ast.Subscript):
                continue
            values = base.slice.elts if isinstance(base.slice, ast.Tuple) else (base.slice,)
            if all(
                isinstance(value, ast.Name)
                and (value.id in plain_classes or value.id in parameters)
                for value in values
            ) and _native_generic_base_static(module, base, owner, unsafe_providers):
                protected |= set(values)
    for node in module.scope_nodes:
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Store | ast.Del)
            and node.attr[:2] != "__"
            and isinstance(node.value, ast.Name)
            and node.value.id in plain_classes
        ):
            protected |= {node.value}
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            protected |= {
                value
                for value in (*node.args.defaults, *node.args.kw_defaults)
                if isinstance(value, ast.Name) and value.id in plain_classes
            }
        elif (
            isinstance(node, ast.Call)
            and _bare_builtin(module, node.func, {"setattr"})
            and len(node.args) == 3
            and not node.keywords
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in plain_classes
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
            and node.args[1].value[:2] != "__"
            and (isinstance(node.args[2], ast.Name) or _inert_creation_operand(node.args[2]))
        ):
            protected |= {node.args[0]}
    return protected


def _protected_member_references(
    module: ParsedModule,
    nodes: Sequence[ast.AST],
    *,
    member_surface: bool,
    owner_exposure_only: bool,
    unsafe_providers: AbstractSet[str] = frozenset(),
) -> set[ast.AST]:
    type_expressions = _protected_type_expressions(nodes)
    protected = _type_reference_nodes(module, type_expressions) if member_surface else set()
    if member_surface:
        protected |= {
            root
            for expression in module._non_escaping_enum_values
            if isinstance((root := expression.value), ast.Name)
        }
        protected |= {
            expression.func
            for expression in module._proven_constructor_returns
            if isinstance(expression, ast.Call)
        }
        protected |= {
            item
            for expression in module._proven_class_values
            for item in ast.walk(expression)
            if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load)
        }
        protected |= _type_reference_nodes(module, list(module._proven_callable_expressions))
        protected |= {
            item
            for expression in module._proven_map_union_expressions
            for item in ast.walk(expression)
            if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load)
        }
        protected |= {
            item
            for owner in nodes
            if isinstance(owner, ast.ClassDef)
            for method in property_bindings(module, owner)
            for decorator in method.decorator_list
            for item in ast.walk(decorator)
        }
        protected |= _type_reference_nodes(
            module,
            [base for node in nodes if isinstance(node, ast.ClassDef) for base in node.bases],
        )
    protected |= {
        node.value
        for node in module.tree.body
        if isinstance(node, ast.Assign | ast.AnnAssign)
        and isinstance(node.value, ast.Name)
        and all(
            isinstance(target, ast.Name)
            for target in (node.targets if isinstance(node, ast.Assign) else (node.target,))
        )
    }
    if owner_exposure_only:
        protected |= _protected_class_owner_references(module, unsafe_providers)
        protected |= _type_reference_nodes(
            module,
            [
                node.func
                for node in nodes
                if isinstance(node, ast.Call)
                and (
                    isinstance(node.func, ast.Name)
                    or isinstance(node.func, ast.Attribute)
                    and (path := attribute_path(node.func)) is not None
                    and all(part[:2] != "__" for part in path[1])
                )
            ]
            + [
                decorator
                for node in nodes
                if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
                for decorator in node.decorator_list
            ]
            + [node.test for node in nodes if isinstance(node, ast.If | ast.While | ast.IfExp)],
        )
    return protected


def member_escape_references(
    module: ParsedModule,
    nodes: Sequence[ast.AST],
    *,
    member_surface: bool,
    owner_exposure_only: bool,
    unsafe_providers: AbstractSet[str] = frozenset(),
) -> Iterator[ast.Name]:
    """Keep escape sites bound to their lexical owner."""
    protected = _protected_member_references(
        module,
        nodes,
        member_surface=member_surface,
        owner_exposure_only=owner_exposure_only,
        unsafe_providers=unsafe_providers,
    )
    local_references = setter_local_references(module) if member_surface else frozenset()
    for node in nodes:
        pending: list[ast.AST]
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store | ast.Del):
            pending = [node.value]
        elif member_surface and isinstance(node, ast.Call):
            pending = [*node.args, *(keyword.value for keyword in node.keywords)]
            if not owner_exposure_only and node not in module._proven_constructor_returns:
                pending.append(node.func)
        elif (
            member_surface
            and isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node not in protected
        ):
            pending = [node]
        else:
            continue
        while pending:
            target = pending.pop()
            if isinstance(target, ast.Name) and target not in local_references:
                if owner_exposure_only and target in protected:
                    continue
                yield target
            elif isinstance(target, ast.Attribute):
                if member_surface and target in module._non_escaping_enum_values:
                    continue
                pending.append(target.value)
            elif not isinstance(target, ast.Call):
                pending.extend(ast.iter_child_nodes(target))


def _unproven_member_roots(
    module: ParsedModule,
    nodes: Sequence[ast.AST],
    *,
    member_surface: bool,
    owner_exposure_only: bool,
    unsafe_providers: AbstractSet[str],
    include_creation_uncertainty: bool,
) -> set[str]:
    properties = {
        method
        for owner in nodes
        if member_surface and include_creation_uncertainty and isinstance(owner, ast.ClassDef)
        for method in property_bindings(module, owner)
    }
    changed: set[str] = (
        {
            node.name
            for node in nodes
            if (
                isinstance(node, ast.ClassDef)
                and not class_creation_static(
                    module,
                    node,
                    owner_exposure_only=owner_exposure_only,
                    unsafe_providers=unsafe_providers,
                )
                or isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and node not in properties
                and _method_signature(module, node, None)[1] is not True
            )
        }
        if member_surface and include_creation_uncertainty
        else set()
    )
    if member_surface and owner_exposure_only:
        changed.update(
            node.name
            for node in nodes
            if isinstance(node, ast.ClassDef) and _class_members_receive_owner(module, node)
        )
    changed.update(
        node.id
        for node in member_escape_references(
            module,
            nodes,
            member_surface=member_surface,
            owner_exposure_only=owner_exposure_only,
            unsafe_providers=unsafe_providers,
        )
    )
    return changed


def _type_reference_nodes(module: ParsedModule, expressions: Sequence[ast.expr]) -> set[ast.AST]:
    """Exclude declared type references, not executable operands of an unknown type shape."""
    protected: set[ast.AST] = set()
    pending: list[tuple[ast.AST, bool]] = [(expression, False) for expression in expressions]
    bound = frozenset(module.bound_names)
    stable = stable_direct_module_bindings(module) & unique_direct_module_bindings(module)
    while pending:
        node, callback_reference = pending.pop()
        if isinstance(node, ast.Name):
            protected |= {node}
        elif isinstance(node, ast.Attribute):
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                protected |= set(ast.walk(node))
        elif isinstance(node, ast.Subscript):
            pending.append((node.value, callback_reference))
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if (
                (
                    node in module._proven_callable_expressions
                    or node in module._proven_annotation_carriers
                    or is_static_type_alias_value(module, node)
                )
                and isinstance(root, ast.Name)
                and (root.id not in bound or (root.id in module.aliases and root.id in stable))
            ):
                pending.append(
                    (node.slice, callback_reference or node in module._proven_callable_expressions)
                )
        elif isinstance(node, ast.Tuple | ast.List):
            pending.extend((element, callback_reference) for element in node.elts)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            if callback_reference or any(
                isinstance(operand, ast.Constant) and operand.value is None
                for operand in (node.left, node.right)
            ):
                pending.extend(((node.left, callback_reference), (node.right, callback_reference)))
    return protected


def is_static_type_alias_value(module: ParsedModule, node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return True
    if isinstance(node, ast.Subscript):
        if node in module._proven_callable_expressions:
            return True
        head = resolve_static_name(module, node.value)
        return head in {
            "typing.Annotated",
            "typing.Literal",
            "typing.Optional",
            "typing.Union",
            "typing_extensions.Annotated",
            "typing_extensions.Literal",
            "typing_extensions.TypeAliasType",
            "dict",
            "list",
            "set",
            "tuple",
            "frozenset",
        }
    return False


def admitted_type_alias_value(module: ParsedModule, node: ast.AST) -> ast.expr | None:
    """Reuse symbol admission without asserting provider or member safety."""
    if node not in module.tree.body:
        return None
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id[:1].isupper()
        and is_static_type_alias_value(module, node.value)
    ):
        return node.value
    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and isinstance(node.value, ast.expr)
        and resolve_static_name(module, node.annotation) == "typing.TypeAlias"
    ):
        return node.value
    if sys.version_info >= (3, 12) and isinstance(node, ast.TypeAlias) and not node.type_params:
        return node.value
    return None


def _bare_builtin(module: ParsedModule, node: ast.AST, names: AbstractSet[str]) -> bool:
    return (
        isinstance(node, ast.Name)
        and node.id in names
        and module.binding_names is not None
        and node.id not in module.bound_names
        and not (
            sys.version_info >= (3, 12)
            and any(
                isinstance(
                    item, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef | ast.TypeAlias
                )
                and item.type_params
                for item in module.all_nodes
            )
        )
    )


def _nullable_builtin_key(module: ParsedModule, node: ast.AST) -> bool:
    return (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.BitOr)
        and _bare_builtin(module, node.left, {"str"})
        and isinstance(node.right, ast.Constant)
        and node.right.value is None
    )


def intrinsic_nullable_aliases(module: ParsedModule) -> frozenset[str]:
    stable = stable_direct_module_bindings(module)
    counts = Counter(module.bound_names)
    return frozenset(
        name
        for node, name in module_scope_bindings(module)
        if counts[name] == 1
        and name in stable
        and (value := admitted_type_alias_value(module, node)) is not None
        and _nullable_builtin_key(module, value)
    )


def _class_value_expressions(module: ParsedModule) -> Iterator[ast.expr]:
    for owner in module.tree.body:
        if not isinstance(owner, ast.ClassDef):
            continue
        for statement in owner.body:
            if not isinstance(statement, ast.Assign | ast.AnnAssign) or statement.value is None:
                continue
            expression = statement.value
            if _inert_creation_operand(expression) or any(
                binding_may_exist_before(module, owner.body, statement, node.id)
                for node in ast.walk(expression)
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
            ):
                continue
            yield expression


_CLASS_VALUE_TYPE_HEADS: Final = frozenset({"dict", "list", "tuple", "set", "frozenset"})
_CLASS_VALUE_BUILTIN_TYPES: Final = _CLASS_VALUE_TYPE_HEADS | {
    "str",
    "int",
    "float",
    "bool",
    "bytes",
    "object",
    "type",
    "complex",
}


def _prove_class_numeric_value(
    provider: ParsedModule,
    expression: ast.expr,
    pending: frozenset[tuple[str, str]],
    modules: Mapping[str, ParsedModule],
    imported_bindings: Mapping[tuple[str, str], tuple[str, str]],
    definitions: dict[tuple[str, str], ast.expr],
) -> tuple[bool, frozenset[tuple[str, str]]] | None:
    if any(isinstance(node, ast.Call) for node in ast.walk(expression)):
        return None
    try:
        value = ast.literal_eval(expression)
    except (ValueError, TypeError, SyntaxError, RecursionError):
        pass
    else:
        return isinstance(value, int | float | complex), frozenset()
    if isinstance(expression, ast.Name):
        binding = (provider.module, expression.id)
        if binding in pending or expression.id not in stable_direct_module_bindings(provider):
            return None
        origin = imported_bindings.get(binding, binding)
        declaration = definitions.get(origin)
        if declaration is None or (origin == binding and declaration.lineno >= expression.lineno):
            return None
        result = _prove_class_numeric_value(
            modules[origin[0]],
            declaration,
            pending | {binding, origin},
            modules,
            imported_bindings,
            definitions,
        )
        if result is not None:
            numeric, dependencies = result
            return numeric, dependencies | {binding, origin}
    elif isinstance(expression, ast.BinOp) and isinstance(
        expression.op,
        ast.Add
        | ast.Sub
        | ast.Mult
        | ast.Div
        | ast.FloorDiv
        | ast.Mod
        | ast.Pow
        | ast.LShift
        | ast.RShift
        | ast.BitOr
        | ast.BitAnd
        | ast.BitXor,
    ):
        left = _prove_class_numeric_value(
            provider, expression.left, pending, modules, imported_bindings, definitions
        )
        right = _prove_class_numeric_value(
            provider, expression.right, pending, modules, imported_bindings, definitions
        )
        if left is not None and right is not None and left[0] and right[0]:
            return True, left[1] | right[1]
    elif isinstance(expression, ast.UnaryOp) and isinstance(
        expression.op, ast.UAdd | ast.USub | ast.Invert
    ):
        operand = _prove_class_numeric_value(
            provider, expression.operand, pending, modules, imported_bindings, definitions
        )
        if operand is not None and operand[0]:
            return operand
    return None


def _prove_class_type_value(
    provider: ParsedModule,
    expression: ast.expr,
    statement: ast.AST,
    modules: Mapping[str, ParsedModule],
    imported_bindings: Mapping[tuple[str, str], tuple[str, str]],
    classes: dict[tuple[str, str], ast.ClassDef],
    unsafe_providers: AbstractSet[str],
) -> frozenset[tuple[str, str]] | None:
    if isinstance(expression, ast.Constant) and expression.value is None:
        return frozenset()
    if isinstance(expression, ast.Name):
        if _bare_builtin(provider, expression, _CLASS_VALUE_BUILTIN_TYPES):
            return frozenset()
        if not bound_once_before(provider.tree.body, statement, expression.id):
            return None
        binding = (provider.module, expression.id)
        origin = imported_bindings.get(binding, binding)
        definition = classes.get(origin)
        if definition is None:
            return None
        owner = modules[origin[0]]
        class_dependencies = frozenset({binding, origin})
        if not definition.bases and class_creation_static(
            owner, definition, owner_exposure_only=False, unsafe_providers=unsafe_providers
        ):
            return class_dependencies
        if (
            len(definition.bases) == 1
            and resolve_static_name(owner, definition.bases[0]) in NATIVE_TYPED_DICT_BASES
            and native_owner_creation_static(owner, definition, unsafe_providers)
        ):
            base = definition.bases[0]
            root = base.value if isinstance(base, ast.Attribute) else base
            if isinstance(root, ast.Name):
                return class_dependencies | {(owner.module, root.id)}
        return None
    if isinstance(expression, ast.Subscript) and _bare_builtin(
        provider, expression.value, _CLASS_VALUE_TYPE_HEADS
    ):
        arguments: Sequence[ast.expr] = (
            expression.slice.elts
            if isinstance(expression.slice, ast.Tuple)
            else (expression.slice,)
        )
    elif isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.BitOr):
        arguments = (expression.left, expression.right)
    else:
        return None
    argument_dependencies: set[tuple[str, str]] = set()
    for argument in arguments:
        proof = _prove_class_type_value(
            provider, argument, statement, modules, imported_bindings, classes, unsafe_providers
        )
        if proof is None:
            return None
        argument_dependencies |= proof
    return frozenset(argument_dependencies)


def proven_class_value_candidates(
    modules: Mapping[str, ParsedModule],
    imported_bindings: Mapping[tuple[str, str], tuple[str, str]],
    *,
    unsafe_providers: AbstractSet[str] = frozenset(),
) -> dict[str, dict[ast.expr, frozenset[tuple[str, str]]]]:
    """Prove closed values without invoking user-defined value or type operators."""
    definitions = {
        (name, target.id): statement.value
        for name, provider in modules.items()
        for statement in provider.tree.body
        if isinstance(statement, ast.Assign | ast.AnnAssign) and statement.value is not None
        for target in (
            statement.targets if isinstance(statement, ast.Assign) else (statement.target,)
        )
        if isinstance(target, ast.Name) and target.id in stable_direct_module_bindings(provider)
    }

    builtin_dependencies = frozenset(
        (name, node.id)
        for name, provider in modules.items()
        for node in provider.all_nodes
        if isinstance(node, ast.Name) and node.id in _CLASS_VALUE_BUILTIN_TYPES
    )
    for name in modules:
        for binding in modules[name].aliases:
            target: str = modules[name].aliases[binding].target
            if target == "builtins" or target.startswith("builtins."):
                builtin_dependencies |= {(name, binding)}
    type_values_static = not any(
        exposes_dynamic_namespace(modules[name], node, member_surface=True)
        for name in modules
        for node in modules[name].all_nodes
    )
    classes: dict[tuple[str, str], ast.ClassDef] = {
        (name, node.name): node
        for name, provider in modules.items()
        for node in provider.tree.body
        if isinstance(node, ast.ClassDef)
        and node.name in stable_direct_module_bindings(provider)
        and node.name in unique_direct_module_bindings(provider)
    }
    unsafe = unsafe_providers | frozenset(modules)

    candidates: dict[str, dict[ast.expr, frozenset[tuple[str, str]]]] = {}
    for name, module in modules.items():
        values: dict[ast.expr, frozenset[tuple[str, str]]] = {}
        for expression in _class_value_expressions(module):
            proof = _prove_class_numeric_value(
                module, expression, frozenset(), modules, imported_bindings, definitions
            )
            if proof is not None:
                values[expression] = proof[1]
        if type_values_static:
            for statement, binding in module_scope_bindings(module):
                value = admitted_type_alias_value(module, statement)
                if value is None or binding not in stable_direct_module_bindings(module):
                    continue
                type_proof = _prove_class_type_value(
                    module, value, statement, modules, imported_bindings, classes, unsafe
                )
                if type_proof is not None:
                    values[value] = type_proof | builtin_dependencies | {(name, binding)}
        module._proven_class_values = frozenset(values)
        candidates[name] = values
    return candidates


def _inert_constructor_classes(
    module: ParsedModule, stable: frozenset[str], builtin_annotations: frozenset[str]
) -> dict[str, ast.ClassDef]:
    return {
        node.name: node
        for node in module.tree.body
        if isinstance(node, ast.ClassDef)
        and node.name in stable
        and not node.bases
        and not node.keywords
        and not node.decorator_list
        and all(
            isinstance(child, ast.Pass)
            or isinstance(child, ast.Expr)
            and isinstance(child.value, ast.Constant)
            and isinstance(child.value.value, str)
            or isinstance(child, ast.AnnAssign)
            and isinstance(child.target, ast.Name)
            and child.value is None
            and (
                _inert_creation_operand(child.annotation)
                or _bare_builtin(module, child.annotation, builtin_annotations)
            )
            for child in node.body
        )
    }


def proven_constructor_return_candidates(
    module: ParsedModule,
) -> dict[ast.expr, frozenset[tuple[str, str]]]:
    stable = stable_direct_module_bindings(module) & unique_direct_module_bindings(module)
    builtin_annotations = frozenset({"str", "int", "float", "bool", "bytes", "object"})
    classes = _inert_constructor_classes(module, stable, builtin_annotations)
    candidates: dict[ast.expr, frozenset[tuple[str, str]]] = {}
    for function in module.tree.body:
        if (
            not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
            or function.name not in stable
            or function.decorator_list
        ):
            continue
        arguments = [
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
            *(item for item in (function.args.vararg, function.args.kwarg) if item is not None),
        ]
        if not all(
            _inert_creation_operand(value)
            for value in [
                *function.args.defaults,
                *(item for item in function.args.kw_defaults if item is not None),
            ]
        ):
            continue
        annotations = _protected_type_expressions([function, *arguments])
        header_names = {
            value.id
            for value in annotations
            if isinstance(value, ast.Name)
            and value.id in classes
            and classes[value.id].lineno < function.lineno
        }
        if not all(
            _deferred_creation_annotation(module, value)
            or _inert_creation_operand(value)
            or _bare_builtin(module, value, builtin_annotations)
            or isinstance(value, ast.Name)
            and value.id in header_names
            for value in annotations
        ):
            continue
        shadowed = lexical_binding_names(function)
        for statement in function.body:
            if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.Call):
                continue
            call = statement.value
            if not isinstance(call.func, ast.Name) or call.args or call.keywords:
                continue
            owner = classes.get(call.func.id)
            if owner is not None and owner.lineno < function.lineno and owner.name not in shadowed:
                # Exposing this native function exposes its class through __globals__.
                candidates[call] = frozenset(
                    {(module.module, owner.name), (module.module, function.name)}
                    | {(module.module, name) for name in header_names}
                )
    module._proven_constructor_returns = frozenset(candidates)
    return candidates


def proven_map_union_candidates(
    module: ParsedModule, aliases: Mapping[str, tuple[str, str]]
) -> dict[ast.expr, frozenset[tuple[str, str]]]:
    candidates: dict[ast.expr, frozenset[tuple[str, str]]] = {}
    expressions = [
        *_protected_type_expressions(module.all_nodes),
        *(
            value
            for node in module.tree.body
            if (value := admitted_type_alias_value(module, node)) is not None
        ),
    ]
    for expression in expressions:
        pending = [expression]
        maps: list[ast.expr] = []
        while pending:
            arm = pending.pop()
            if isinstance(arm, ast.BinOp) and isinstance(arm.op, ast.BitOr):
                pending.extend((arm.right, arm.left))
            else:
                maps.append(arm)
        if len(maps) < 2:
            continue
        dependencies: set[tuple[str, str]] = set()
        alias_count = 0
        for arm in maps:
            if not (
                isinstance(arm, ast.Subscript)
                and _bare_builtin(module, arm.value, {"dict"})
                and isinstance(arm.slice, ast.Tuple)
                and len(arm.slice.elts) == 2
                and _bare_builtin(module, arm.slice.elts[1], {"str", "int", "float"})
            ):
                break
            key = arm.slice.elts[0]
            if _bare_builtin(module, key, {"str"}) or _nullable_builtin_key(module, key):
                continue
            if (
                isinstance(key, ast.Subscript)
                and _bare_builtin(module, key.value, {"tuple"})
                and isinstance(key.slice, ast.Tuple)
                and len(key.slice.elts) == 2
                and all(_bare_builtin(module, item, {"int"}) for item in key.slice.elts)
            ):
                continue
            if isinstance(key, ast.Name) and key.id in aliases:
                alias_count += 1
                dependencies.update(((module.module, key.id), aliases[key.id]))
                if alias_count <= 1:
                    continue
            break
        else:
            candidates[expression] = frozenset(dependencies)
    return candidates


def proven_annotation_carrier_candidates(
    module: ParsedModule, scanned_modules: AbstractSet[str]
) -> dict[ast.expr, frozenset[tuple[str, str]]]:
    stable = stable_direct_module_bindings(module) & unique_direct_module_bindings(module)
    annotations = [
        node.annotation
        for node in module.all_nodes
        if isinstance(node, ast.arg | ast.AnnAssign) and node.annotation is not None
    ] + [
        node.returns
        for node in module.all_nodes
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.returns is not None
    ]
    candidates: dict[ast.expr, frozenset[tuple[str, str]]] = {}
    for annotation in annotations:
        for node in ast.walk(annotation):
            if not isinstance(node, ast.Subscript):
                continue
            head: str = resolve_static_name(module, node.value)
            if head not in {
                "collections.abc.Mapping",
                "collections.abc.Sequence",
                "typing.Mapping",
                "typing.Sequence",
            }:
                continue
            provider: str = head.rpartition(".")[0]
            if head == provider + ".Mapping":
                if not isinstance(node.slice, ast.Tuple) or len(node.slice.elts) != 2:
                    continue
            elif isinstance(node.slice, ast.Tuple):
                continue
            if head in scanned_modules or any(
                provider == name or provider.startswith(name + ".") for name in scanned_modules
            ):
                continue
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name) and root.id in module.aliases and root.id in stable:
                binding = module.aliases[root.id]
                if binding.kind is not ImportKind.MODULE or binding.target != head:
                    candidates[node] = frozenset({(module.module, root.id)})
    return candidates


def proven_callable_candidates(
    module: ParsedModule, providers: Mapping[str, frozenset[tuple[str, str]]]
) -> dict[ast.expr, frozenset[tuple[str, str]]]:
    callable_bindings: set[str] = set()
    for provider_head in providers:
        callable_head: str = provider_head
        callable_bindings.add(callable_head.split(".", 1)[0])
    module._proven_callable_providers = frozenset(callable_bindings)
    expressions = list(_protected_type_expressions(module.all_nodes))
    aliases: dict[ast.expr, str] = {}
    for node, name in module_scope_bindings(module):
        value = None
        name_prefix: str = name[:1]
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and name_prefix.isupper():
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            value = admitted_type_alias_value(module, node)
        elif sys.version_info >= (3, 12) and isinstance(node, ast.TypeAlias):
            value = admitted_type_alias_value(module, node)
        if value is not None:
            expressions.append(value)
            aliases[value] = name
    candidates: dict[ast.expr, frozenset[tuple[str, str]]] = {}
    pending = list(expressions)
    while pending:
        expression = pending.pop()
        if isinstance(expression, ast.Subscript):
            head = annotation_text(expression.value) or ""
            if head in providers:
                candidates[expression] = providers[head]
                pending.append(expression.slice)
            elif is_static_type_alias_value(module, expression):
                pending.append(expression.slice)
        elif isinstance(expression, ast.Tuple | ast.List):
            pending.extend(expression.elts)
        elif isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.BitOr):
            pending.extend((expression.left, expression.right))
    module._proven_callable_expressions = frozenset(candidates)
    for expression, dependencies in tuple(candidates.items()):
        aliases_used: set[tuple[str, str]] = {
            (module.module, name)
            for value, name in aliases.items()
            if expression in ast.walk(value)
        }
        candidates[expression] = dependencies | aliases_used
    return candidates


def resolve_static_name(module: ParsedModule, node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        text = node.id
    elif isinstance(node, ast.Attribute) and (path := attribute_path(node)) is not None:
        text = ".".join((path[0], *path[1]))
    else:
        text = annotation_text(node) or ""
    parts = text.split(".")
    binding = module.aliases.get(parts[0]) if parts else None
    if binding is None:
        return text
    return ".".join([binding.target, *parts[1:]])


def exposes_dynamic_namespace(
    module: ParsedModule,
    node: ast.AST,
    *,
    local_namespace: bool = False,
    member_surface: bool = False,
    include_import_effects: bool = True,
) -> bool:
    if (
        member_surface
        and isinstance(node, ast.Name | ast.Attribute)
        and isinstance(node.ctx, ast.Load)
        and (
            isinstance(node, ast.Name)
            and node.id == "__annotations__"
            or isinstance(node, ast.Attribute)
            and node.attr in {"f_globals", "f_locals", "f_builtins"}
        )
    ):
        return True
    if isinstance(node, ast.Call):
        target = node.func
        namespace_access = not node.args
    elif isinstance(node, ast.Assign | ast.AnnAssign) and isinstance(
        node.value, ast.Name | ast.Attribute
    ):
        target = node.value
        namespace_access = True
    elif isinstance(node, ast.Name | ast.Attribute) and isinstance(node.ctx, ast.Load):
        target = node
        namespace_access = True
    else:
        return False
    name = resolve_static_name(module, target)
    if member_surface and name in {
        "typing.get_type_hints",
        "typing_extensions.get_type_hints",
        "inspect.get_annotations",
    }:
        return True
    if name in {
        "globals",
        "builtins.globals",
        "exec",
        "builtins.exec",
        "eval",
        "builtins.eval",
        "__builtins__",
    }:
        return True
    if name in {"__import__", "builtins.__import__"}:
        return include_import_effects
    return (
        local_namespace
        and namespace_access
        and name in {"locals", "vars", "builtins.locals", "builtins.vars"}
    )


# The calls and names that expose only the namespace of the module that uses them (AD-273).
# `globals()` is not one of them: its dict holds references to shared objects such as `importlib`.
_OWN_NAMESPACE_NAMES: Final = frozenset(
    {
        "exec",
        "builtins.exec",
        "eval",
        "builtins.eval",
        "typing.get_type_hints",
        "typing_extensions.get_type_hints",
        "inspect.get_annotations",
    }
)


_NAME_CONTAINERS: Final = frozenset({"set", "frozenset", "sorted", "list", "tuple", "len"})


def reads_only_namespace_names(
    module: ParsedModule, node: ast.AST, parents: Mapping[ast.AST, ast.AST]
) -> bool:
    """Whether a `globals()` call only reads the names of the module (AD-273).

    The keys are strings, so reading them reaches no shared object. Any other use of the dict
    (`globals()[name]`, `.get`, `.items()`, `dict(globals())`, a variable) can reach `importlib` or
    `builtins` through the module's bindings and is not a read of names.
    """
    if not (
        isinstance(node, ast.Call)
        and not node.args
        and resolve_static_name(module, node.func) in {"globals", "builtins.globals"}
    ):
        return False
    return _consumed_as_names(module, node, parents)


def _consumed_as_names(
    module: ParsedModule, node: ast.expr, parents: Mapping[ast.AST, ast.AST]
) -> bool:
    # A keys view keeps its dict in `.mapping`, so `.keys()` only passes on to the same consumers.
    parent = parents.get(node)
    if isinstance(parent, ast.Attribute) and parent.attr == "keys":
        call = parents.get(parent)
        return (
            isinstance(call, ast.Call)
            and call.func is parent
            and _consumed_as_names(module, call, parents)
        )
    if isinstance(parent, ast.Call):
        # A module-level `def set(...)` must not pass for the builtin.
        return parent.args == [node] and _bare_builtin(module, parent.func, _NAME_CONTAINERS)
    if isinstance(parent, ast.Compare):
        # `a in b in c` runs `c.__contains__(b)`: any other operand is handed to a user object.
        return parent.comparators[-1] is node and isinstance(parent.ops[-1], ast.In | ast.NotIn)
    return isinstance(parent, ast.For | ast.AsyncFor | ast.comprehension) and parent.iter is node


def exposes_own_namespace_only(module: ParsedModule, node: ast.AST) -> bool:
    """Whether an exposure that `exposes_dynamic_namespace` found stays in the module itself.

    Fail closed: an exposure that is not listed here (a frame's `f_globals`, `__builtins__`, any
    trigger added later) is treated as reaching other modules.
    """
    if isinstance(node, ast.Name):
        return node.id == "__annotations__" or resolve_static_name(module, node) in (
            _OWN_NAMESPACE_NAMES
        )
    if isinstance(node, ast.Call):
        target = node.func
    elif isinstance(node, ast.Assign | ast.AnnAssign) and isinstance(
        node.value, ast.Name | ast.Attribute
    ):
        target = node.value
    elif isinstance(node, ast.Attribute):
        target = node
    else:
        return False
    return resolve_static_name(module, target) in _OWN_NAMESPACE_NAMES


def _import_bindings(node: ast.Import | ast.ImportFrom) -> tuple[str, ...]:
    return tuple(
        alias.asname or (alias.name.split(".")[0] if isinstance(node, ast.Import) else alias.name)
        for alias in node.names
        if alias.name != "*"
    )


def _bound_names(nodes: Iterable[ast.AST]) -> list[str]:
    nodes = list(nodes)
    imports = [
        name
        for child in nodes
        if isinstance(child, ast.Import | ast.ImportFrom)
        for name in _import_bindings(child)
    ]
    return (
        [
            child.id
            for child in nodes
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store | ast.Del)
        ]
        + [child.arg for child in nodes if isinstance(child, ast.arg)]
        + [
            child.name
            for child in nodes
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        ]
        + imports
        + [child.name for child in nodes if isinstance(child, ast.ExceptHandler) and child.name]
        + [child.name for child in nodes if isinstance(child, ast.MatchAs) and child.name]
        + [child.name for child in nodes if isinstance(child, ast.MatchStar) and child.name]
        + [child.rest for child in nodes if isinstance(child, ast.MatchMapping) and child.rest]
        + [
            name
            for child in nodes
            if isinstance(child, ast.Global | ast.Nonlocal)
            for name in child.names
        ]
    )


def _module_scope_nodes(module: ast.Module) -> Iterator[ast.AST]:
    """Walk module-evaluated expressions, excluding nested function/class bodies."""
    pending: list[ast.AST] = [module]
    while pending:
        node = pending.pop()
        yield node
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            expressions: list[ast.AST] = [*node.decorator_list, *node.args.defaults]
            expressions.extend(item for item in node.args.kw_defaults if item is not None)
            expressions.extend(
                argument.annotation
                for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                if argument.annotation is not None
            )
            if node.args.vararg and node.args.vararg.annotation:
                expressions.append(node.args.vararg.annotation)
            if node.args.kwarg and node.args.kwarg.annotation:
                expressions.append(node.args.kwarg.annotation)
            if node.returns:
                expressions.append(node.returns)
            pending.extend(reversed(expressions))
        elif isinstance(node, ast.ClassDef):
            expressions = [*node.decorator_list, *node.bases]
            expressions.extend(keyword.value for keyword in node.keywords)
            pending.extend(reversed(expressions))
        elif isinstance(node, ast.Lambda):
            expressions = [*node.args.defaults]
            expressions.extend(item for item in node.args.kw_defaults if item is not None)
            pending.extend(reversed(expressions))
        elif isinstance(node, ast.comprehension):
            pending.extend(reversed([node.iter, *node.ifs]))
        elif isinstance(node, ast.ListComp | ast.SetComp | ast.GeneratorExp):
            pending.extend(reversed([node.elt, *node.generators]))
        elif isinstance(node, ast.DictComp):
            pending.extend(reversed([node.key, node.value, *node.generators]))
        else:
            pending.extend(reversed(list(ast.iter_child_nodes(node))))


def module_scope_bindings(
    module: ParsedModule,
) -> Iterator[tuple[ast.AST, str]]:
    """Yield names that module-evaluated binding forms may bind."""
    for node in module.scope_nodes:
        targets: Iterable[ast.AST] = ()
        if isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
            if isinstance(node, ast.AnnAssign) and node.value is None:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
        elif isinstance(node, ast.NamedExpr):
            targets = (node.target,)
        elif isinstance(node, ast.For | ast.AsyncFor):
            targets = (node.target,)
        elif isinstance(node, ast.With | ast.AsyncWith):
            targets = tuple(item.optional_vars for item in node.items if item.optional_vars)
        elif sys.version_info >= (3, 12) and isinstance(node, ast.TypeAlias):
            yield node, node.name.id
        elif (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            and node not in module.tree.body
        ):
            yield node, node.name
        for target in targets:
            for child in ast.walk(target):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    yield node, child.id
        if isinstance(node, ast.ExceptHandler) and node.name:
            yield node, node.name
        elif isinstance(node, ast.MatchAs | ast.MatchStar) and node.name:
            yield node, node.name
        elif isinstance(node, ast.MatchMapping) and node.rest:
            yield node, node.rest


def _excerpt(module: ParsedModule, node: ast.AST) -> str:
    start, _, _ = location(node)
    return module.lines[start - 1].rstrip() if start <= len(module.lines) else ""


def add_evidence(evidence: dict[str, RawEvidence], module: ParsedModule, node: ast.AST) -> str:
    line, end_line, column = location(node)
    return record_evidence(
        evidence, module.rel_path, (line, end_line, column), _excerpt(module, node)
    )


def quoted_type_expression(node: ast.expr) -> ast.expr | None:
    """Decode one syntax-only string layer of names, None and unions."""
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return None
    text: str = node.value
    try:
        expression = ast.parse(text.strip(), mode="eval").body
    except SyntaxError:
        return None
    if all(
        isinstance(child, ast.Name | ast.Load | ast.BinOp | ast.BitOr)
        or (isinstance(child, ast.Constant) and child.value is None)
        for child in ast.walk(expression)
    ):
        return expression
    return None


def annotation_text(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if type(node) is ast.Name:
        return node.id
    try:
        return ast.unparse(node)
    except ValueError:
        return None


def decorator_names(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    names: list[str] = []
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        try:
            names.append(ast.unparse(target))
        except ValueError:
            continue
    return sorted(names)


def body_is_empty(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when nothing but a docstring, `pass` or `...` stands in the body.

    Collectors are peers that never import each other (AD-25), so the predicate the binding
    collector and the construct collector both need lives here, where both may reach it.
    """
    return all(
        isinstance(statement, ast.Pass)
        or (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant))
        for statement in node.body
    )


def module_for(path: Path, *, root: Path, namespace: str) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    prefix = namespace.split(".")
    for index in range(len(parts) - len(prefix) + 1):
        if parts[index : index + len(prefix)] == prefix:
            return ".".join(parts[index:])
    raise ValueError(f"source path does not contain configured namespace {namespace!r}")


def package_for(module: str) -> str:
    parts = module.split(".")
    return ".".join(parts[:2]) if len(parts) > 1 else module


# The collector entry sets this recursion limit. The recursive walkers use about three frames
# for each AST level, so a deeper tree would stop the whole scan with a RecursionError.
RECURSION_LIMIT: Final = 20_000
MAX_AST_DEPTH: Final = 5_000


class TooDeepError(ValueError):
    pass


def _ast_depth(tree: ast.AST) -> int:
    deepest = 0
    pending: list[tuple[ast.AST, int]] = [(tree, 1)]
    while pending:
        node, depth = pending.pop()
        deepest = max(deepest, depth)
        pending.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
    return deepest


def _parse_bounded(source: str, filename: str) -> ast.Module:
    """Parse one module, or refuse it when the tree is too deep for the walkers to traverse."""
    try:
        tree = ast.parse(source, filename=filename)
    except (RecursionError, MemoryError) as exc:
        # CPython raises MemoryError when its parser stack overflows on a very deep expression.
        raise TooDeepError("expression nesting exceeds the parser stack") from exc
    depth = _ast_depth(tree)
    if depth > MAX_AST_DEPTH:
        raise TooDeepError(f"expression nesting of {depth} levels exceeds {MAX_AST_DEPTH}")
    return tree


@dataclass(frozen=True)
class ParsedSources:
    """Modules parsed from one scan pass, their coverage failures and source digest."""

    modules: list[ParsedModule]
    failures: list[RawRecord]
    files_read: int
    source_digest: str


def parse_sources(paths: Sequence[Path], *, root: Path, namespace: str) -> ParsedSources:
    """Read, digest and parse each candidate path into a module or a coverage failure."""
    modules: list[ParsedModule] = []
    failures: list[RawRecord] = []
    read_count = 0
    digest = hashlib.sha256()
    for path in paths:
        rel = path.relative_to(root).as_posix()
        try:
            raw = path.read_bytes()
            read_count += 1
            digest.update(rel.encode("utf-8"))
            digest.update(b"\0")
            digest.update(raw)
            digest.update(b"\0")
            source = raw.decode("utf-8")
            tree = _parse_bounded(source, rel)
            module_name = module_for(path, root=root, namespace=namespace)
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as exc:
            if isinstance(exc, SyntaxError):
                line, message = exc.lineno or 1, exc.msg
            elif isinstance(exc, TooDeepError):
                line, message = 1, str(exc)
            elif isinstance(exc, OSError):
                line, message = 1, exc.strerror or exc.__class__.__name__
            else:
                line, message = 1, exc.__class__.__name__
            failure_id = stable_id("COVERAGE", rel, line, exc.__class__.__name__, message)
            failures.append(
                classified(
                    item_id=failure_id,
                    evidence_class=EvidenceClass.UNKNOWN,
                    area="analysis_coverage",
                    kind=exc.__class__.__name__,
                    title=f"{rel}:{line} could not be analyzed",
                    subjects=[rel],
                    data={"file": rel, "line": line, "message": str(message)},
                )
            )
            continue
        modules.append(
            ParsedModule(
                path=path,
                rel_path=rel,
                module=module_name,
                package=package_for(module_name),
                source=source,
                source_bytes=raw,
                lines=re.split(r"\r\n?|\n", source),
                tree=tree,
            )
        )
    return ParsedSources(
        modules=modules,
        failures=failures,
        files_read=read_count,
        source_digest=digest.hexdigest(),
    )


def parse_provider(source: PythonProviderSource) -> ParsedModule | None:
    """Parse one captured provider source; a syntax error leaves it unparsed."""
    text: str = source.source
    try:
        tree = ast.parse(text, filename=source.path)
    except (SyntaxError, ValueError):
        return None
    return ParsedModule(
        Path(source.path),
        source.path,
        source.module,
        package_for(source.module),
        text,
        text.encode("utf-8"),
        re.split(r"\r\n?|\n", text),
        tree,
    )


def is_stdlib_root(name: str) -> bool:
    """A top-level standard library module: the only scope of the 3.13+ layout proofs (#724)."""
    return name in sys.stdlib_module_names and "." not in name


@dataclass(frozen=True, slots=True)
class ModuleRegistry:
    """How one module uses sys.modules."""

    # Child name -> the one proven top-level write and the plain import that it publishes.
    published: dict[str, tuple[ast.Assign, str]]
    # Literal keys of every registry access, also in deferred bodies.
    keys: frozenset[str]


def module_registry(module: ParsedModule) -> ModuleRegistry:
    """Find the sys.modules writes that publish a child and every other registry access."""
    if module.registry_cache is None:
        module.registry_cache = _scan_registry(module)
    return module.registry_cache


def _scan_registry(module: ParsedModule) -> ModuleRegistry:
    # Any `import sys` counts, also a conditional one: it can be the registry.
    systems = {
        alias.asname or alias.name
        for node in module.all_nodes
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "sys"
    }
    registries = {
        alias.asname or alias.name
        for node in module.all_nodes
        if isinstance(node, ast.ImportFrom) and node.module == "sys" and not node.level
        for alias in node.names
        if alias.name == "modules"
    }
    owners = {child: node for node in module.all_nodes for child in ast.iter_child_nodes(node)}
    keys = _registry_keys(module, systems, registries, owners)
    writes = _registry_writes(module)
    matched = {
        node for found in writes.values() for statement, _ in found for node in ast.walk(statement)
    }
    # Another registry access, also through an alias or the namespace of sys, can replace a child.
    if any(
        node not in matched
        and (
            isinstance(node, ast.Attribute)
            and node.attr == "modules"
            or isinstance(node, ast.Attribute)
            and node.attr == "__dict__"
            and isinstance(node.value, ast.Name)
            and node.value.id in systems
            or isinstance(node, ast.Name)
            and node.id in registries
        )
        for node in module.all_nodes
    ):
        return ModuleRegistry({}, keys)
    return ModuleRegistry(
        {
            child: found[0]
            for child, found in writes.items()
            if len(found) == 1 and _child_published(module, child, found[0], owners)
        },
        keys,
    )


def _registry_keys(
    module: ParsedModule,
    systems: set[str],
    registries: set[str],
    owners: Mapping[ast.AST, ast.AST],
) -> frozenset[str]:
    """Literal keys of every sys.modules subscript or method call, also in deferred bodies."""
    keys: set[str] = set()
    for node in module.all_nodes:
        if not (
            isinstance(node, ast.Attribute)
            and node.attr == "modules"
            and isinstance(node.value, ast.Name)
            and node.value.id in systems
            or isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "__dict__"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id in systems
            and isinstance(node.slice, ast.Constant)
            and node.slice.value == "modules"
            or isinstance(node, ast.Name)
            and node.id in registries
        ):
            continue
        owner = owners.get(node)
        call = owners.get(owner) if isinstance(owner, ast.Attribute) else None
        arguments: list[ast.expr] = (
            [owner.slice]
            if isinstance(owner, ast.Subscript)
            else call.args
            if isinstance(call, ast.Call)
            else []
        )
        keys.update(
            item.value
            for item in arguments
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        )
    return frozenset(keys)


def _registry_writes(module: ParsedModule) -> dict[str, list[tuple[ast.Assign, str]]]:
    """Top-level `sys.modules['<package>.<child>'] = <module>` writes with stable imports."""
    writes: dict[str, list[tuple[ast.Assign, str]]] = {}
    for index, statement in enumerate(module.tree.body):
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        [target] = statement.targets
        if (
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Attribute)
            and target.value.attr == "modules"
            and isinstance(target.value.value, ast.Name)
            and _plain_import(module, target.value.value.id, index) == "sys"
            and isinstance(target.slice, ast.Constant)
            and isinstance(target.slice.value, str)
            and isinstance(statement.value, ast.Name)
            and _plain_import(module, statement.value.id, index) == statement.value.id
        ):
            key: str = target.slice.value
            package, _, child = key.rpartition(".")
            if package == module.module:
                writes[child] = [*writes.get(child, []), (statement, statement.value.id)]
    return writes


def _child_published(
    module: ParsedModule,
    child: str,
    write: tuple[ast.Assign, str],
    owners: Mapping[ast.AST, ast.AST],
) -> bool:
    """The write publishes the one import of the module, and nothing can change that module."""
    statement, value = write
    body: list[ast.stmt] = module.tree.body
    bindings = [
        item
        for item in body
        if isinstance(item, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == child for target in item.targets)
    ]
    attribute = [item.value for item in bindings if isinstance(item.value, ast.Name)]
    start = next(
        index
        for index, item in enumerate(body)
        if isinstance(item, ast.Import)
        and value in {alias.asname or alias.name for alias in item.names}
    )
    end = max(body.index(item) for item in (statement, *bindings))
    # Another import here can import `<package>.<module>` and rebind the module name.
    between = [
        item for item in body[start + 1 : end + 1] if item is not statement and item not in bindings
    ]
    imports = [
        alias
        for node in module.all_nodes
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == value
    ]
    return (
        (
            child not in module.scope_bound_names
            or module.scope_bound_names.count(child) == 1
            and len(attribute) == 1
            and attribute[0].id == value
        )
        and all(
            isinstance(item, ast.Import) and {alias.name for alias in item.names} == {"sys"}
            for item in between
        )
        and len(imports) == 1
        and not any(
            isinstance(node, ast.ImportFrom)
            and node.level
            or isinstance(node, ast.Import)
            and any("." in alias.name for alias in node.names)
            or isinstance(node, ast.Constant)
            and node.value == value
            for node in module.all_nodes
        )
        and _module_unchanged(
            module,
            {value, *(child for _ in attribute)},
            owners,
            {statement.value, *attribute, *(name for item in bindings for name in item.targets)},
        )
    )


def _module_unchanged(
    module: ParsedModule,
    names: set[str],
    owners: Mapping[ast.AST, ast.AST],
    allowed: set[ast.expr],
) -> bool:
    """The module only reads plain members of the published module, through any of its names."""
    for node in module.all_nodes:
        if not isinstance(node, ast.Name) or node.id not in names or node in allowed:
            continue
        owner = owners.get(node)
        call = owners.get(owner) if owner is not None else None
        # A store, a call, `__dict__` or an escape of the module can change a published member.
        if not (
            isinstance(owner, ast.Attribute)
            and isinstance(owner.ctx, ast.Load)
            and owner.attr != "__dict__"
            and not (isinstance(call, ast.Call) and call.func is owner)
        ):
            return False
    return True


def _plain_import(module: ParsedModule, name: str, before: int) -> str | None:
    """The module that a unique top-level `import` before `before` binds to `name`."""
    # The import collector fills module.aliases later, and the decoder has no import collector.
    found = [
        alias.name
        for statement in module.tree.body[:before]
        if isinstance(statement, ast.Import)
        for alias in statement.names
        if (alias.asname or alias.name) == name
    ]
    unique = (
        len(found) == 1
        and module.scope_bound_names.count(name) == 1
        and name not in module.global_names
    )
    return found[0] if unique else None


def stdlib_member_static(module: ParsedModule, member: ast.stmt) -> bool:
    """A stdlib binding that no missing-name hook or star import can answer first."""
    # During an import cycle, a hook or a star import before the binding answers the import.
    body: list[ast.stmt] = module.tree.body
    before = {node for statement in body[: body.index(member)] for node in ast.walk(statement)}
    # Module scope only: a method named __getattr__ is no module hook.
    earlier = [node for node in module.scope_nodes if node in before]
    stars = [
        node
        for node in module.scope_nodes
        if isinstance(node, ast.ImportFrom) and "*" in {alias.name for alias in node.names}
    ]
    return (
        is_stdlib_root(module.module)
        and all(
            node in before and not node.level and node.module in sys.stdlib_module_names
            for node in stars
        )
        and "__getattr__" not in _bound_names(earlier)
    )


def provider_source_eligible(module: ParsedModule) -> bool:
    if BuiltinImporter.find_spec(module.module) is not None:
        return False
    if FrozenImporter.find_spec(module.module) is None:
        return True
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    source = stdlib.joinpath(*module.module.split("."))
    source = (
        source / "__init__.py" if module.path.name == "__init__.py" else source.with_suffix(".py")
    )
    try:
        code = FrozenImporter.get_code(module.module)
        if (
            source.resolve().is_relative_to(stdlib)
            and source.read_bytes() == module.source_bytes
            and isinstance(code, CodeType)
        ):
            compiled = compile(
                module.source,
                code.co_filename,
                "exec",
                dont_inherit=True,
                optimize=sys.flags.optimize,
            )
            return _same_provider_code(compiled, code)
    except (OSError, ImportError, SyntaxError, ValueError, TypeError):
        pass
    return False


def _same_provider_code(left: CodeType, right: CodeType) -> bool:
    return (
        left == right
        and left.co_filename == right.co_filename
        and left.co_stacksize == right.co_stacksize
        and left.co_linetable == right.co_linetable
        and left.co_exceptiontable == right.co_exceptiontable
        and all(
            not isinstance(a, CodeType) or isinstance(b, CodeType) and _same_provider_code(a, b)
            for a, b in zip(left.co_consts, right.co_consts, strict=True)
        )
    )
