# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Parsed-module primitives shared by the scanner and its context collector."""

from __future__ import annotations

import ast
import hashlib
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal, Protocol, TypedDict

from archkeel.ir.facts import EvidenceClass, stable_id
from archkeel.ir.facts_codec import RawData as RecordData
from archkeel.ir.facts_codec import (
    RawEvidence,
    RawRecord,
    classified,
)
from archkeel.ir.facts_codec import (
    file_evidence as file_evidence,
)
from archkeel.ir.facts_codec import (
    record_evidence as record_evidence,
)
from archkeel.ir.source_records import FRAMEWORK_BASES as FRAMEWORK_BASES
from archkeel.ir.source_records import is_public_method_name as is_public_method_name


class _PropertyBinding(TypedDict):
    """One ordered operation on a statically named standard property binding."""

    operation: Literal["create", "getter", "setter"]
    source: Literal["new", "local", "base"]
    line: int
    source_line: int


FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
DefinitionNode = ast.ClassDef | FunctionNode
DefinitionContexts = tuple[tuple[ast.AST, str, str], ...]

_CONTROL_FLOW_KINDS = {
    ast.If: "if",
    ast.For: "for",
    ast.AsyncFor: "async_for",
    ast.While: "while",
    ast.Try: "try",
    ast.TryStar: "try_star",
    ast.With: "with",
    ast.AsyncWith: "async_with",
    ast.Match: "match",
}
_DEFINITION_BRANCHES = {
    "body": "body",
    "orelse": "else",
    "handlers": "handler",
    "finalbody": "finally",
    "cases": "case",
}

NATIVE_DATACLASS_DECORATOR: Final = "dataclasses.dataclass"
NATIVE_TYPED_DICT_BASE: Final = "typing.TypedDict"
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


def definition_sites(
    node: ast.AST,
    parent: DefinitionNode | None = None,
    contexts: DefinitionContexts = (),
) -> Iterator[tuple[DefinitionNode, DefinitionNode | None, DefinitionContexts]]:
    if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        yield node, parent, contexts
        parent = node
    for field_name, children in ast.iter_fields(node):
        if field_name not in _DEFINITION_BRANCHES or not isinstance(children, list):
            continue
        for child in children:
            if isinstance(child, ast.AST):
                nested = contexts
                if type(node) in _CONTROL_FLOW_KINDS:
                    nested = (*contexts, _branch_context(node, child, field_name))
                yield from definition_sites(child, parent, nested)


def _branch_context(node: ast.AST, child: ast.AST, field_name: str) -> tuple[ast.AST, str, str]:
    site = (
        child
        if isinstance(child, ast.ExceptHandler)
        else child.pattern
        if isinstance(child, ast.match_case)
        else node
    )
    return site, _CONTROL_FLOW_KINDS[type(node)], _DEFINITION_BRANCHES[field_name]


def control_flow_contexts(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> DefinitionContexts:
    contexts: list[tuple[ast.AST, str, str]] = []
    while node in parents:
        parent = parents[node]
        if type(parent) in _CONTROL_FLOW_KINDS:
            for field_name, children in ast.iter_fields(parent):
                if (
                    field_name in _DEFINITION_BRANCHES
                    and isinstance(children, list)
                    and node in children
                ):
                    contexts.append(_branch_context(parent, node, field_name))
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


@dataclass(frozen=True)
class AliasBinding:
    target: str
    kind: Literal["module", "symbol"]
    imported_name: str | None = None


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
    all_nodes: tuple[ast.AST, ...] = field(init=False, repr=False)
    scope_nodes: tuple[ast.AST, ...] = field(init=False, repr=False)
    bound_names: tuple[str, ...] = field(init=False, repr=False)
    scope_bound_names: tuple[str, ...] = field(init=False, repr=False)
    unique_bindings: frozenset[str] = field(init=False, repr=False)
    stable_binding_cache: tuple[dict[str, AliasBinding], frozenset[str]] | None = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self.all_nodes = tuple(ast.walk(self.tree))
        self.scope_nodes = tuple(_module_scope_nodes(self.tree))
        self.bound_names = tuple(_bound_names(self.all_nodes))
        self.scope_bound_names = tuple(_bound_names(self.scope_nodes))
        self.unique_bindings = _unique_direct_module_bindings(self)


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


def stable_direct_module_bindings(module: ParsedModule) -> frozenset[str]:
    """Names bound once at module level without a conditional or explicit global rebind."""
    cache = module.stable_binding_cache
    if cache is None or cache[0] != module.aliases:
        cache = (dict(module.aliases), _stable_direct_module_bindings(module))
        module.stable_binding_cache = cache
    return cache[1]


def _stable_direct_module_bindings(module: ParsedModule) -> frozenset[str]:
    direct: dict[str, int] = {}
    for statement in module.tree.body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            direct[statement.name] = direct.get(statement.name, 0) + 1
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
    all_nodes = module.all_nodes
    if any(exposes_dynamic_namespace(module, node) for node in all_nodes) or any(
        exposes_dynamic_namespace(module, node, local_namespace=True) for node in nodes
    ):
        return frozenset()
    changed_members = _member_binding_roots(module, all_nodes, member_surface=False)
    global_names = {
        name for node in all_nodes if isinstance(node, ast.Global) for name in node.names
    }
    return frozenset(
        name
        for name, count in direct.items()
        if count == 1 and counts[name] == 1 and name not in global_names | changed_members
    )


def binding_may_exist_before(
    statements: Sequence[ast.stmt], stop: ast.AST | None, name: str
) -> bool:
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
                if any(
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
            and not binding_may_exist_before(module.tree.body, None, root)
            and (parent is None or not binding_may_exist_before(parent.body, method, root))
        )
    if (
        root is None
        or root not in module.aliases
        or root not in stable_direct_module_bindings(module)
        or not binding_may_exist_before(module.tree.body, parent or method, root)
    ):
        return False
    return parent is None or not binding_may_exist_before(parent.body, method, root)


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
) -> tuple[list[str], bool, bool] | None:
    if (
        isinstance(child, ast.Assign | ast.AnnAssign | ast.NamedExpr)
        and child.value is not None
        and not isinstance(child.value, ast.Constant | ast.List | ast.Tuple | ast.Set | ast.Dict)
        and not (inert_values and _inert_creation_operand(child.value))
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


def unproven_class_body(
    module: ParsedModule, node: ast.ClassDef, *, inert_values: bool = False
) -> bool:
    """Keep member binding and class-creation transformations conservative."""
    if any(
        isinstance(item, ast.NamedExpr)
        or exposes_dynamic_namespace(module, item, local_namespace=True)
        for expr in class_definition_expressions(node)
        for item in ast.walk(expr)
    ):
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
            or (
                child not in properties
                and method_decorator_data(module, child, node)["signature_decorators_proven"]
                is not True
            )
        ):
            return True
        if (
            isinstance(child, ast.Assign | ast.AnnAssign)
            and child.value is not None
            and any(isinstance(item, ast.NamedExpr) for item in ast.walk(child.value))
        ):
            return True
        statement_bindings = _class_statement_bindings(child, inert_values=inert_values)
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
) -> dict[FunctionNode, _PropertyBinding]:
    if parent not in module.tree.body:
        return {}
    bindings: dict[FunctionNode, _PropertyBinding] = {}
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
    bindings: dict[FunctionNode, _PropertyBinding],
) -> _PropertyBinding | None:
    if len(node.decorator_list) != 1 or isinstance(node, ast.AsyncFunctionDef):
        return None
    decorator = node.decorator_list[0]
    if is_proven_decorator(
        module, decorator, node, parent, frozenset({"property", "builtins.property"})
    ) and not isinstance(decorator, ast.Call):
        return {"operation": "create", "source": "new", "line": node.lineno, "source_line": 0}
    if not isinstance(decorator, ast.Attribute) or decorator.attr not in {"getter", "setter"}:
        return None
    operation: Literal["getter", "setter"] = "getter" if decorator.attr == "getter" else "setter"
    descriptor = decorator.value
    if isinstance(descriptor, ast.Name) and descriptor.id == node.name:
        origin = previous.get(node.name)
        if origin is not None and origin in bindings:
            return {
                "operation": operation,
                "source": "local",
                "line": node.lineno,
                "source_line": origin.lineno,
            }
    if (
        isinstance(descriptor, ast.Attribute)
        and descriptor.attr == node.name
        and len(parent.bases) == 1
        and ast.dump(descriptor.value) == ast.dump(parent.bases[0])
    ):
        root = descriptor.value
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name) and not binding_may_exist_before(parent.body, node, root.id):
            return {"operation": operation, "source": "base", "line": node.lineno, "source_line": 0}
    return None


def method_decorator_data(
    module: ParsedModule,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parent: ast.ClassDef | None,
) -> RecordData:
    method_kind = "instance"
    signature_proven = True
    descriptor_count = 0
    targets = frozenset(
        {
            "staticmethod",
            "builtins.staticmethod",
            "classmethod",
            "builtins.classmethod",
            "property",
            "builtins.property",
            "typing.overload",
            "typing_extensions.overload",
            "abc.abstractmethod",
        }
    )
    for decorator in node.decorator_list:
        proven = not isinstance(decorator, ast.Call) and is_proven_decorator(
            module, decorator, node, parent, targets
        )
        signature_proven = signature_proven and proven
        if proven:
            resolved = resolve_static_name(module, decorator)
            if resolved not in {
                "typing.overload",
                "typing_extensions.overload",
                "abc.abstractmethod",
            }:
                descriptor_count += 1
            if resolved in {"staticmethod", "builtins.staticmethod"}:
                method_kind = "static"
            elif resolved in {"classmethod", "builtins.classmethod"}:
                method_kind = "class"
    properties = property_bindings(module, parent) if parent is not None else {}
    binding = properties.get(node)
    if (
        binding is not None
        and parent is not None
        and parent.name not in stable_direct_module_bindings(module)
    ):
        binding = None
    return {
        "method_kind": method_kind,
        "signature_decorators_proven": signature_proven and descriptor_count <= 1,
        "source_final_method_binding": not node.decorator_list
        and parent is not None
        and parent in module.tree.body
        and parent.name in stable_direct_module_bindings(module)
        and binding_may_exist_before(parent.body, node, node.name)
        and not binding_may_exist_before(tuple(reversed(parent.body)), node, node.name),
        **({"property_binding": binding} if binding is not None else {}),
    }


def class_header_static(node: ast.ClassDef) -> bool:
    return not node.decorator_list and not node.keywords


def _class_members_receive_owner(module: ParsedModule, owner: ast.ClassDef) -> bool:
    for node in _module_scope_nodes(ast.Module(body=owner.body, type_ignores=[])):
        if exposes_dynamic_namespace(module, node, local_namespace=True):
            return True
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if method_decorator_data(module, node, owner)[
                "signature_decorators_proven"
            ] is not True and node not in property_bindings(module, owner):
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
            elif _class_statement_bindings(node, inert_values=True, member_surface=False) is None:
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


def _class_creation_static(
    module: ParsedModule,
    node: ast.ClassDef,
    *,
    owner_exposure_only: bool,
    unsafe_providers: AbstractSet[str],
) -> bool:
    return (
        class_header_static(node)
        and not unproven_class_body(module, node)
        and _class_base_operands_static(module, node)
    ) or (owner_exposure_only and native_owner_creation_static(module, node, unsafe_providers))


def _inert_creation_operand(node: ast.expr) -> bool:
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
        method_decorator_data(module, node, None)["signature_decorators_proven"] is True
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
                _inert_creation_operand(child.value)
            ):
                return False
        elif isinstance(child, ast.AnnAssign):
            if (
                not isinstance(child.target, ast.Name)
                or not (
                    _deferred_creation_annotation(module, child.annotation)
                    or _inert_creation_operand(child.annotation)
                )
                or (child.value is not None and not _inert_creation_operand(child.value))
            ):
                return False
        else:
            return False
    return True


def native_owner_creation_static(
    module: ParsedModule, node: ast.ClassDef, unsafe_providers: AbstractSet[str]
) -> bool:
    if node not in module.tree.body:
        return False
    if not node.bases and not node.keywords and len(node.decorator_list) == 1:
        decorator = node.decorator_list[0]
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if "dataclasses" in unsafe_providers or not _native_factory_binding_static(
            module, node, decorator, target, NATIVE_DATACLASS_DECORATOR
        ):
            return False
        if isinstance(decorator, ast.Call) and (
            decorator.args
            or any(
                keyword.arg not in DATACLASS_OPTIONS
                or not isinstance(keyword.value, ast.Constant)
                or not isinstance(keyword.value.value, bool)
                for keyword in decorator.keywords
            )
        ):
            return False
        return _native_class_body_static(module, node)
    if len(node.bases) == 1 and not node.decorator_list and not node.keywords:
        base = node.bases[0]
        return (
            "typing" not in unsafe_providers
            and _native_factory_binding_static(module, node, base, base, NATIVE_TYPED_DICT_BASE)
            and all(
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
                    and _deferred_creation_annotation(module, child.annotation)
                )
                for child in node.body
            )
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


def _contained_member_roots(
    module: ParsedModule,
    nodes: Sequence[ast.AST],
    *,
    owner_exposure_only: bool = False,
    unsafe_providers: AbstractSet[str] = frozenset(),
) -> set[tuple[str, str]]:
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
    # Native functions expose their defining namespace, including through a class's methods.
    namespace = frozenset(module.scope_bound_names)
    uncertain_bases = member_binding_closure(
        nodes, module.incoming_member_escapes, member_surface=True
    )
    contained |= {
        (name, binding)
        for name, owner in owners
        if (
            owner_exposure_only
            and isinstance(owner, ast.ClassDef)
            and (
                not _class_creation_static(
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
        for binding in namespace
    }
    return contained


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
    if any(exposes_dynamic_namespace(module, node, member_surface=True) for node in nodes) or any(
        exposes_dynamic_namespace(module, node, local_namespace=True) for node in module.scope_nodes
    ):
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
    contained = (
        _contained_member_roots(
            module,
            nodes,
            owner_exposure_only=owner_exposure_only,
            unsafe_providers=unsafe_providers,
        )
        if member_surface
        else set()
    )
    if member_surface:
        changed_members |= module.incoming_member_escapes if incoming is None else incoming
    changed_members = member_binding_closure(
        nodes, changed_members, member_surface=member_surface, contained=contained
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
        origin = imported_target if alias.kind == "module" else imported_target.rpartition(".")[0]
        if origin in changed_origins:
            changed_members |= {name}
    return changed_members


def member_binding_closure(
    nodes: Sequence[ast.AST],
    roots: AbstractSet[str],
    *,
    member_surface: bool,
    contained: AbstractSet[tuple[str, str]] = frozenset(),
) -> set[str]:
    changed_members = set(roots)
    aliases = {
        (target.id, value.id)
        for node in nodes
        if isinstance(node, ast.Assign | ast.AnnAssign)
        and (
            isinstance(node.value, ast.Name)
            or (member_surface and isinstance(node.value, ast.Attribute))
        )
        for target in (node.targets if isinstance(node, ast.Assign) else (node.target,))
        if isinstance(target, ast.Name)
        for value in ast.walk(node.value)
        if isinstance(value, ast.Name)
    }
    while (
        additions := (
            {value for name, value in aliases if name in changed_members}
            | {name for name, value in aliases if value in changed_members}
            | {value for owner, value in contained if owner in changed_members}
        )
        - changed_members
    ):
        changed_members |= additions
    return changed_members


def _protected_member_references(
    module: ParsedModule,
    nodes: Sequence[ast.AST],
    *,
    member_surface: bool,
    owner_exposure_only: bool,
) -> set[ast.AST]:
    type_expressions = _protected_type_expressions(nodes)
    protected = _type_reference_nodes(module, type_expressions) if member_surface else set()
    if member_surface:
        protected |= {
            item
            for owner in nodes
            if isinstance(owner, ast.ClassDef)
            for method in property_bindings(module, owner)
            for decorator in method.decorator_list
            for item in ast.walk(decorator)
        }
    if member_surface:
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
        protected |= _type_reference_nodes(
            module,
            [node.func for node in nodes if isinstance(node, ast.Call)]
            + [
                decorator
                for node in nodes
                if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
                for decorator in node.decorator_list
            ]
            + [node.test for node in nodes if isinstance(node, ast.If | ast.While | ast.IfExp)],
        )
    return protected


def _unproven_member_roots(
    module: ParsedModule,
    nodes: Sequence[ast.AST],
    *,
    member_surface: bool,
    owner_exposure_only: bool,
    unsafe_providers: AbstractSet[str],
    include_creation_uncertainty: bool,
) -> set[str]:
    protected = _protected_member_references(
        module, nodes, member_surface=member_surface, owner_exposure_only=owner_exposure_only
    )
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
                and not _class_creation_static(
                    module,
                    node,
                    owner_exposure_only=owner_exposure_only,
                    unsafe_providers=unsafe_providers,
                )
                or isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and node not in properties
                and method_decorator_data(module, node, None)["signature_decorators_proven"]
                is not True
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
    for node in nodes:
        pending: list[ast.AST]
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store | ast.Del):
            pending = [node.value]
        elif member_surface and isinstance(node, ast.Call):
            pending = [*node.args, *(keyword.value for keyword in node.keywords)]
            if not owner_exposure_only:
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
            if isinstance(target, ast.Name):
                changed.add(target.id)
            elif isinstance(target, ast.Attribute):
                pending.append(target.value)
            elif not isinstance(target, ast.Call):
                pending.extend(ast.iter_child_nodes(target))
    return changed


def _type_reference_nodes(module: ParsedModule, expressions: Sequence[ast.expr]) -> set[ast.AST]:
    """Exclude declared type references, not executable operands of an unknown type shape."""
    protected: set[ast.AST] = set()
    pending: list[ast.AST] = list(expressions)
    bound = frozenset(module.bound_names)
    stable = stable_direct_module_bindings(module) & unique_direct_module_bindings(module)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Name):
            protected |= {node}
        elif isinstance(node, ast.Attribute):
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                protected |= set(ast.walk(node))
        elif isinstance(node, ast.Subscript):
            pending.append(node.value)
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            if (
                is_static_type_alias_value(module, node)
                and isinstance(root, ast.Name)
                and (root.id not in bound or (root.id in module.aliases and root.id in stable))
            ):
                pending.append(node.slice)
        elif isinstance(node, ast.Tuple | ast.List):
            pending.extend(node.elts)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            if any(
                isinstance(operand, ast.Constant) and operand.value is None
                for operand in (node.left, node.right)
            ):
                pending.extend((node.left, node.right))
    return protected


def is_static_type_alias_value(module: ParsedModule, node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return True
    if isinstance(node, ast.Subscript):
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


def resolve_static_name(module: ParsedModule, node: ast.AST) -> str:
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
) -> bool:
    if (
        member_surface
        and isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == "__annotations__"
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
    if name in {"globals", "builtins.globals", "exec", "builtins.exec", "eval", "builtins.eval"}:
        return True
    return (
        local_namespace
        and namespace_access
        and name in {"locals", "vars", "builtins.locals", "builtins.vars"}
    )


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


def annotation_text(node: ast.AST | None) -> str | None:
    if node is None:
        return None
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
            tree = ast.parse(source, filename=rel)
            module_name = module_for(path, root=root, namespace=namespace)
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as exc:
            if isinstance(exc, SyntaxError):
                line, message = exc.lineno or 1, exc.msg
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
                lines=source.splitlines(),
                tree=tree,
            )
        )
    return ParsedSources(
        modules=modules,
        failures=failures,
        files_read=read_count,
        source_digest=digest.hexdigest(),
    )
