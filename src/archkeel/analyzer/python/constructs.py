# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Construct collection: asserts, broad excepts, empty bodies, reflection, str literal compares."""

from __future__ import annotations

import ast
import sys
from collections import Counter
from collections.abc import Sequence
from enum import Enum
from typing import Protocol

from archkeel.ir.facts import (
    MAX_NUMERIC_EVIDENCE_CHARS,
    MAX_STATIC_INTEGER,
    CallBindingOrigin,
    EvidenceClass,
    SourceNameVisibility,
    stable_id,
)
from archkeel.ir.facts import RawJson as RawJson
from archkeel.ir.facts_codec import RawData as RecordData
from archkeel.ir.facts_codec import RawEvidence, RawRecord, classified
from archkeel.ir.source_records import source_name_visibility as _source_name_visibility

from .resolve import SymbolIndex
from .scopes import BindingKind, LexicalScopes, Scope
from .source import (
    ParsedModule,
    add_evidence,
    body_is_empty,
    decorator_names,
    location,
    own_scope,
    stable_direct_module_bindings,
)

_NumericAlias = dict[str, str | int]


def _numeric_evidence_excerpt_supported(excerpt: str) -> bool:
    if not excerpt or len(excerpt) > MAX_NUMERIC_EVIDENCE_CHARS or "\n" in excerpt:
        return False
    stripped: str = excerpt.lstrip(" \t")
    if stripped.startswith("@"):
        return _numeric_decorator_excerpt(excerpt) is not None
    if _numeric_elif_start(excerpt) is not None:
        return _numeric_elif_excerpt_supported(excerpt)
    try:
        ast.parse(excerpt)
        return True
    except (IndentationError, SyntaxError, ValueError, RecursionError):
        indentation = excerpt[: len(excerpt) - len(excerpt.lstrip(" \t"))]
        parsed = _numeric_indented_excerpt(excerpt, indentation, synthetic_body=False)
        if parsed is not None:
            return True
        parsed = _numeric_indented_excerpt(excerpt, indentation, synthetic_body=True)
        return (
            parsed is not None
            and len(parsed[0]) == 1
            and _numeric_header_has_synthetic_body(parsed[0][0])
        )


def _numeric_decorator_excerpt(excerpt: str) -> tuple[tuple[ast.stmt, ...], int] | None:
    indentation = excerpt[: len(excerpt) - len(excerpt.lstrip(" \t"))]
    unit = "\t" if "\t" in indentation else "    "
    prefix = "if True:\n" if indentation else ""
    offset = 1 if indentation else 0
    source = (
        f"{prefix}{excerpt}\n"
        f"{indentation}def __archkeel_numeric_witness__():\n"
        f"{indentation}{unit}pass"
    )
    try:
        parsed = ast.parse(source)
    except (IndentationError, SyntaxError, ValueError, RecursionError):
        return None
    roots = tuple(parsed.body)
    if indentation and (len(roots) != 1 or not isinstance(roots[0], ast.If)):
        return None
    body = tuple(roots[0].body) if indentation and isinstance(roots[0], ast.If) else roots
    if (
        len(body) != 1
        or not isinstance(body[0], ast.FunctionDef)
        or len(body[0].decorator_list) != 1
    ):
        return None
    return roots, offset


def _numeric_elif_start(excerpt: str) -> int | None:
    for index, character in enumerate(excerpt):
        if character not in " \t":
            if excerpt[index : index + 4] != "elif":
                return None
            if index + 4 < len(excerpt) and excerpt[index + 4] not in " \t(":
                return None
            return index
    return None


def _numeric_indented_excerpt(
    excerpt: str, indentation: str, *, synthetic_body: bool
) -> tuple[tuple[ast.stmt, ...], int] | None:
    unit = "\t" if "\t" in indentation else "    "
    depth = 1 if indentation else 0
    wrappers = "if True:\n" if indentation else ""
    suffix = f"\n{indentation}{unit}pass" if synthetic_body else ""
    try:
        parsed = ast.parse(wrappers + excerpt + suffix)
    except (IndentationError, SyntaxError, ValueError, RecursionError):
        return None
    roots = tuple(parsed.body)
    for _ in range(depth):
        if len(roots) != 1 or not isinstance(roots[0], ast.If):
            return None
        roots = tuple(roots[0].body)
    return roots, depth


def _numeric_header_has_synthetic_body(node: ast.stmt) -> bool:
    header_types = (
        ast.If,
        ast.While,
        ast.For,
        ast.AsyncFor,
        ast.With,
        ast.AsyncWith,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
    )
    return (
        isinstance(node, header_types)
        and len(node.body) == 1
        and isinstance(node.body[0], ast.Pass)
    )


def _numeric_elif_excerpt_supported(excerpt: str) -> bool:
    indentation = excerpt[: len(excerpt) - len(excerpt.lstrip(" \t"))]
    unit = "\t" if "\t" in indentation else "    "
    source = f"{indentation}if True:\n{indentation}{unit}pass\n{excerpt}"
    for synthetic_body in (False, True):
        parsed = _numeric_indented_excerpt(source, indentation, synthetic_body=synthetic_body)
        if parsed is None:
            continue
        roots, _depth = parsed
        if len(roots) != 1 or not isinstance(roots[0], ast.If):
            return False
        preceding = roots[0]
        if len(preceding.body) != 1 or not isinstance(preceding.body[0], ast.Pass):
            return False
        if len(preceding.orelse) != 1 or not isinstance(preceding.orelse[0], ast.If):
            return False
        alternate = preceding.orelse[0]
        if not synthetic_body or _numeric_header_has_synthetic_body(alternate):
            return True
    return False


class _StringPredicate(Enum):
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"


def _string_predicate(node: ast.Call) -> _StringPredicate | None:
    """Decode written member syntax without asserting the receiver's runtime type."""
    if not isinstance(node.func, ast.Attribute):
        return None
    try:
        return _StringPredicate(node.func.attr)
    except ValueError:
        return None


_BROAD_NAMES = frozenset({"Exception", "BaseException"})
_REFLECTION_CALLS = {
    "getattr": "getattr_call",
    "hasattr": "hasattr_call",
    "setattr": "setattr_call",
    "delattr": "delattr_call",
    "vars": "vars_call",
}
_INTEGER_DEPTH = 12
# A stub carrying one of these declares a shape; emptiness is its interface, not a gap (AD-29).
_STUB_DECORATORS = frozenset(
    {
        "abstractmethod",
        "abstractproperty",
        "abstractclassmethod",
        "abstractstaticmethod",
        "overload",
    }
)


class SelectorReceiverResolver(Protocol):
    """Typed call evidence reused to resolve selector receiver origins."""

    index: SymbolIndex

    def _stored_type(
        self, node: ast.Attribute
    ) -> tuple[str, list[str], dict[str, object]] | None: ...

    def _constructed_type(
        self, expression: ast.expr, call_site: ast.expr
    ) -> tuple[str, list[str], dict[str, object]] | None: ...


def _raises_not_implemented(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = [
        statement
        for statement in node.body
        if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant))
    ]
    return (
        len(body) == 1
        and isinstance(body[0], ast.Raise)
        and "NotImplementedError" in ast.unparse(body[0])
    )


def _as_written(node: ast.AST) -> str | None:
    """The name a node spells as written, bare or as `builtins.<name>`; aliases stay unseen."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return node.attr if node.value.id == "builtins" else None
    return None


def _is_broad_type(node: ast.AST) -> bool:
    if isinstance(node, ast.Tuple):
        return any(_is_broad_type(element) for element in node.elts)
    return _as_written(node) in _BROAD_NAMES


def _is_str(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str | bytes)


def _str_value(node: ast.expr | None) -> str | bytes | None:
    return (
        node.value
        if isinstance(node, ast.Constant) and isinstance(node.value, str | bytes)
        else None
    )


def _bind_string(
    bindings: dict[str, str | bytes | None], name: str, value: str | bytes | None
) -> None:
    """Keep only one unambiguous binding; a second binding becomes undecidable."""
    bindings[name] = value if name not in bindings else None


def _target_name(node: ast.AST) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent is not None else None
    return None


def _is_enum_class(node: ast.ClassDef, module: ParsedModule) -> bool:
    enum_bases = {"Enum", "IntEnum", "StrEnum", "enum.Enum", "enum.IntEnum", "enum.StrEnum"}
    for base in node.bases:
        name = _dotted_name(base)
        if name is None:
            continue
        parts = name.split(".")
        binding = module.aliases.get(parts[0])
        resolved = ".".join([binding.target, *parts[1:]]) if binding else name
        if name in enum_bases or resolved in enum_bases:
            return True
    return False


def _unknown_assignments(node: ast.AST, values: dict[str, str | bytes | None]) -> None:
    """Mark nested assignments unknown, stopping at nested scopes."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
            continue
        if isinstance(child, ast.Assign | ast.AnnAssign | ast.AugAssign | ast.NamedExpr):
            targets = child.targets if isinstance(child, ast.Assign) else [child.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    values[target.id] = None
        elif isinstance(child, ast.Delete):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = None
        elif isinstance(child, ast.Import):
            for alias in child.names:
                values[alias.asname or alias.name.split(".")[0]] = None
        elif isinstance(child, ast.ImportFrom):
            for alias in child.names:
                if alias.name != "*":
                    values[alias.asname or alias.name] = None
        _unknown_assignments(child, values)


def _static_string_constants(
    module: ParsedModule,
) -> tuple[dict[str, str | bytes | None], dict[str, dict[str, str | bytes | None]], set[str]]:
    module_values: dict[str, str | bytes | None] = {}
    class_values: dict[str, dict[str, str | bytes | None]] = {}
    enum_classes: set[str] = set()

    def collect(body: list[ast.stmt], prefix: str, values: dict[str, str | bytes | None]) -> None:
        for statement in body:
            if isinstance(statement, ast.Assign | ast.AnnAssign):
                value = statement.value
                targets = (
                    statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                )
                for target in targets:
                    name = _target_name(target)
                    if name is not None:
                        _bind_string(values, name, _str_value(value))
            elif isinstance(statement, ast.ClassDef):
                _bind_string(values, statement.name, None)
                qualified = f"{prefix}.{statement.name}"
                class_values[qualified] = {}
                if _is_enum_class(statement, module):
                    enum_classes.add(qualified)
                collect(statement.body, qualified, class_values[qualified])
            elif isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
                _bind_string(values, statement.name, None)
            elif isinstance(statement, ast.Import):
                for alias in statement.names:
                    _bind_string(values, alias.asname or alias.name.split(".")[0], None)
            elif isinstance(statement, ast.ImportFrom):
                for alias in statement.names:
                    if alias.name != "*":
                        _bind_string(values, alias.asname or alias.name, None)
            else:
                _unknown_assignments(statement, values)

    collect(module.tree.body, module.module, module_values)
    for node in ast.walk(module.tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign | ast.AugAssign):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = node.targets
        for target in targets:
            if not isinstance(target, ast.Attribute):
                continue
            owner = _dotted_name(target.value)
            class_name = f"{module.module}.{owner}" if owner is not None else None
            if class_name in class_values:
                class_values[class_name][target.attr] = None
    return module_values, class_values, enum_classes


def _literal_collections(
    literals: _LiteralComparisons,
) -> dict[str, ast.Tuple | ast.List | ast.Set]:
    """Retain qualified literal nodes; only tuples also serve predicate arguments."""
    module, scopes = literals.module, literals.scopes
    candidates: dict[str, ast.Tuple | ast.List | ast.Set] = {}
    for statement in module.tree.body:
        if not isinstance(statement, ast.Assign | ast.AnnAssign):
            continue
        if isinstance(statement, ast.Assign) and len(statement.targets) != 1:
            continue
        value = statement.value
        if not (
            isinstance(value, ast.Tuple | ast.List | ast.Set)
            and value.elts
            and all(literals.scalar(item) for item in value.elts)
        ):
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        candidates.update(
            {
                target.id: value
                for target in targets
                if isinstance(target, ast.Name)
                and module.scope_bound_names.count(target.id) == 1
                and target.id not in module.global_names
            }
        )
    parents = {
        child: parent for parent in module.all_nodes for child in ast.iter_child_nodes(parent)
    }
    for node in module.all_nodes:
        if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
            continue
        if node.id not in candidates or scopes.lookup(node, node.id).owner is not scopes.root:
            continue
        parent = parents[node]
        membership = (
            isinstance(parent, ast.Compare)
            and parent.comparators[-1] is node
            and isinstance(parent.ops[-1], ast.In | ast.NotIn)
        )
        predicate = (
            isinstance(candidates[node.id], ast.Tuple)
            and isinstance(parent, ast.Call)
            and bool(parent.args)
            and parent.args[0] is node
            and _string_predicate(parent) is not None
        )
        if not membership and not predicate:
            candidates.pop(node.id, None)
    return candidates


def _literal_enum_body(node: ast.ClassDef) -> bool:
    """Only ordinary literal members establish their written Enum value."""
    for child in node.body:
        if (
            isinstance(child, ast.Assign)
            and len(child.targets) == 1
            and isinstance(child.targets[0], ast.Name)
        ):
            member_name: str = child.targets[0].id
            if _source_name_visibility(member_name) is SourceNameVisibility.PUBLIC_NAME and _is_str(
                child.value
            ):
                continue
        if isinstance(child, ast.Pass):
            continue
        if (
            isinstance(child, ast.Expr)
            and isinstance(child.value, ast.Constant)
            and isinstance(child.value.value, str)
        ):
            continue
        return False
    return True


class _LiteralComparisons:
    """Classify written literal vocabularies without adding runtime binding proof."""

    def __init__(self, module: ParsedModule) -> None:
        self.module = module
        self.scopes = LexicalScopes.for_module(module)
        module_values, class_values, enum_classes = _static_string_constants(module)
        self.module_values = module_values
        self.class_values = class_values
        self.origins: dict[str, str] = {}
        self.stable_names = stable_direct_module_bindings(module)
        enum_value_classes = frozenset(
            f"{module.module}.{node.name}"
            for node in module.tree.body
            if isinstance(node, ast.ClassDef)
            and len(node.bases) == 1
            and self._enum_base(node.bases[0])
            and not node.keywords
            and not node.decorator_list
            and _literal_enum_body(node)
            and node.name in self.stable_names
        )
        self.scalar_names = frozenset(
            f"{module.module}.{name}"
            for name, value in module_values.items()
            if value is not None and name in self.stable_names
        ) | frozenset(
            f"{owner}.{name}"
            for owner, values in class_values.items()
            if owner not in enum_classes
            and owner[len(module.module) + 1 :].split(".")[0] in self.stable_names
            for name, value in values.items()
            if value is not None
        )
        self.enum_member_names = frozenset(
            f"{owner}.{name}"
            for owner in enum_value_classes
            for name, value in class_values[owner].items()
            if "value" not in class_values[owner] and value is not None
        )
        self.collections: dict[str, ast.Tuple | ast.List | ast.Set] = {}

    def string_value(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name) and self._module_name(node):
            value = self.module_values.get(node.id)
            return value if isinstance(value, str) else None
        if isinstance(node, ast.Attribute):
            if not self._module_name(node):
                return None
            owner = _dotted_name(node.value)
            values = self.class_values.get(f"{self.module.module}.{owner}") if owner else None
            value = values.get(node.attr) if values else None
            return value if isinstance(value, str) else None
        return None

    def string_values(self, node: ast.expr) -> tuple[str, ...] | None:
        scalar = self.string_value(node)
        if scalar is not None:
            return (scalar,)
        collection: ast.expr = node
        if isinstance(node, ast.Name) and self._module_name(node):
            collection = self.collections.get(node.id, node)
        if isinstance(collection, ast.Tuple | ast.List | ast.Set):
            values = tuple(self.string_value(item) for item in collection.elts)
            if values and all(value is not None for value in values):
                return tuple(value for value in values if value is not None)
        return None

    def _module_name(self, node: ast.expr) -> bool:
        root = node
        while isinstance(root, ast.Attribute):
            root = root.value
        if not isinstance(root, ast.Name):
            return False
        binding = self.scopes.lookup(root, root.id)
        return (
            binding.owner is self.scopes.root
            and not binding.uncertain
            and root.id in self.stable_names
        )

    def _enum_base(self, node: ast.expr) -> bool:
        if not self._module_name(node):
            return False
        if isinstance(node, ast.Name):
            binding = self.module.aliases.get(node.id)
            resolved = binding.target if binding else None
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            binding = self.module.aliases.get(node.value.id)
            resolved = f"{binding.target}.{node.attr}" if binding else None
        else:
            return False
        return resolved in {"enum.Enum", "enum.StrEnum"}

    def _local_scalar(self, node: ast.Name) -> bool:
        """One preceding literal write in the same function is written syntax evidence."""
        binding = self.scopes.lookup(node, node.id)
        owner = binding.owner
        if (
            binding.uncertain
            or owner is None
            or owner is not self.scopes.by_node[node]
            or not isinstance(owner.node, ast.FunctionDef | ast.AsyncFunctionDef)
        ):
            return False
        sites = owner.bindings.get(node.id, [])
        if len(sites) != 1:
            return False
        assignment = self.scopes.parents.get(sites[0])
        return (
            isinstance(assignment, ast.Assign | ast.AnnAssign)
            and self.scopes.parents.get(assignment) is owner.node
            and (assignment.lineno, assignment.col_offset) < (node.lineno, node.col_offset)
            and assignment.value is not None
            and self._written_scalar(assignment.value)
        )

    def _canonical_name(self, node: ast.expr) -> str | None:
        """Follow stable written import origins, without claiming runtime member closure."""
        attributes: list[str] = []
        root = node
        while isinstance(root, ast.Attribute):
            attributes.append(root.attr)
            root = root.value
        if not isinstance(root, ast.Name) or not self._module_name(node):
            return None
        binding = self.scopes.lookup(root, root.id)
        qualified = f"{self.module.module}.{root.id}"
        if binding.kind is BindingKind.SYMBOL:
            qualified = self.origins.get(qualified, "")
            if not qualified:
                return None
        elif binding.kind is BindingKind.MODULE:
            if len(binding.targets) != 1:
                return None
            qualified = binding.targets[0]
        suffix = ".".join(reversed(attributes))
        name = qualified + ("." + suffix if attributes else "")
        # Module aliases can expose a supported re-export below the imported module.
        parts = name.split(".")
        for length in range(len(parts), 0, -1):
            origin = self.origins.get(".".join(parts[:length]))
            if origin is not None:
                return ".".join([origin, *parts[length:]])
        return name

    def _written_scalar(self, node: ast.expr) -> bool:
        if _is_str(node):
            return True
        name = self._canonical_name(node)
        if name in self.scalar_names:
            return True
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "value"
            and self._canonical_name(node.value) in self.enum_member_names
        )

    def scalar(self, node: ast.expr) -> bool:
        return self._written_scalar(node) or (
            isinstance(node, ast.Name) and self._local_scalar(node)
        )

    def collection(self, node: ast.expr) -> bool:
        if isinstance(node, ast.Tuple | ast.List | ast.Set):
            return bool(node.elts) and all(self.scalar(item) for item in node.elts)
        return (
            isinstance(node, ast.Name) and node.id in self.collections and self._module_name(node)
        )


def _predicate_matches(literals: _LiteralComparisons, node: ast.expr) -> bool:
    if isinstance(node, ast.Tuple):
        return any(literals.scalar(item) for item in node.elts)
    return literals.scalar(node) or (
        isinstance(node, ast.Name)
        and node.id in literals.collections
        and isinstance(literals.collections[node.id], ast.Tuple)
        and literals._module_name(node)
    )


def _comparison_form(literals: _LiteralComparisons, node: ast.Compare) -> str | None:
    operands = [node.left, *node.comparators]
    for operator, left, right in zip(node.ops, operands[:-1], operands[1:], strict=True):
        if isinstance(operator, ast.Eq | ast.NotEq) and (
            literals.scalar(left) or literals.scalar(right)
        ):
            return "compare"
        if isinstance(operator, ast.In | ast.NotIn) and (
            literals.scalar(left) or literals.collection(right)
        ):
            return "membership"
    return None


def _matches_literal(literals: _LiteralComparisons, node: ast.Match) -> bool:
    return any(
        isinstance(pattern, ast.MatchValue) and literals.scalar(pattern.value)
        for case in node.cases
        for pattern in ast.walk(case.pattern)
    )


def _handled_types(caught: ast.expr) -> list[str]:
    elements = caught.elts if isinstance(caught, ast.Tuple) else [caught]
    return sorted(ast.unparse(element) for element in elements)


class ConstructCollector(ast.NodeVisitor):
    """Walk one module, recording each construct under the scope that owns it."""

    def __init__(
        self,
        module: ParsedModule,
        evidence: dict[str, RawEvidence],
        comparisons: _LiteralComparisons,
        symbol_index: SymbolIndex | None = None,
        call_collector: SelectorReceiverResolver | None = None,
        imports: Sequence[RawRecord] = (),
        include_parameter_owner_proof: bool = True,
    ) -> None:
        self.module = module
        self.evidence = evidence
        self.items: list[RawRecord] = []
        self.scope_stack: list[str] = [module.module]
        self.comparisons = comparisons
        self.symbol_index = symbol_index
        self.call_collector = call_collector
        self.imports = imports
        self.include_parameter_owner_proof = include_parameter_owner_proof
        self.inherits_stack: list[bool] = []
        self.scopes = comparisons.scopes
        self.parents = {
            child: parent for parent in module.all_nodes for child in ast.iter_child_nodes(parent)
        }
        self.receiver_types: list[dict[str, str | None]] = []
        self.receiver_scope_names: list[str] = []
        self.parameter_receivers: list[set[str]] = []
        self.parameter_annotations: list[dict[str, tuple[str, ast.expr]]] = []
        self.local_classes: set[str] = set()
        self.local_members: set[str] = set()
        self.selector_ids: set[str] = set()

    def _integer(
        self, node: ast.expr, use: ast.AST, depth: int = 0, seen: frozenset[str] = frozenset()
    ) -> tuple[int | None, list[_NumericAlias]]:
        """Evaluate a small exact integer grammar, refusing expensive work before it runs."""
        value: int | None
        if depth > _INTEGER_DEPTH:
            return None, []
        if isinstance(node, ast.Constant) and type(node.value) is int:
            value = node.value
            return (value, []) if -MAX_STATIC_INTEGER <= value <= MAX_STATIC_INTEGER else (None, [])
        if isinstance(node, ast.Constant) and type(node.value) is bool:
            value = int(node.value)
            return (value, []) if -MAX_STATIC_INTEGER <= value <= MAX_STATIC_INTEGER else (None, [])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value, derivation = self._integer(node.operand, use, depth + 1, seen)
            if value is None:
                return None, derivation
            return (value if isinstance(node.op, ast.UAdd) else -value), derivation
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            base, left = self._integer(node.left, use, depth + 1, seen)
            exponent, right = self._integer(node.right, use, depth + 1, seen)
            if base is None or exponent is None or exponent < 0 or exponent > 256:
                return None, []
            magnitude = -base if base < 0 else base
            result = 1
            for _ in range(exponent):
                if magnitude and result > MAX_STATIC_INTEGER // magnitude:
                    return None, []
                result *= magnitude
            if base < 0 and exponent % 2:
                result = -result
            return result, left + right
        if isinstance(node, ast.Name):
            return self._integer_alias(node, use, depth, seen)
        return None, []

    def _integer_alias(
        self, node: ast.Name, use: ast.AST, depth: int, seen: frozenset[str]
    ) -> tuple[int | None, list[_NumericAlias]]:
        name = node.id
        if name in seen:
            return None, []
        binding = self.scopes.lookup(node, name)
        owner = binding.owner
        assignment = None
        scope_evidence_id: str | None = None
        if owner is self.scopes.root:
            matches = [
                statement
                for statement in self.module.tree.body
                if isinstance(statement, ast.Assign | ast.AnnAssign)
                and any(
                    isinstance(target, ast.Name) and target.id == name
                    for target in (
                        statement.targets
                        if isinstance(statement, ast.Assign)
                        else [statement.target]
                    )
                )
            ]
            if name in stable_direct_module_bindings(self.module) and len(matches) == 1:
                assignment = matches[0]
        elif owner is not None:
            sites = owner.bindings.get(name, [])
            if len(sites) == 1:
                candidate = self.scopes.parents.get(sites[0])
                if (
                    isinstance(candidate, (ast.Assign, ast.AnnAssign))
                    and self.scopes.parents.get(candidate) is owner.node
                ):
                    assignment = candidate
        if assignment is None or assignment.value is None:
            return None, []
        if owner is None:
            return None, []
        evidence_id = add_evidence(self.evidence, self.module, assignment)
        use_line, _, use_column = location(use)
        assignment_line, _, assignment_column = location(assignment)
        if (assignment_line, assignment_column) >= (use_line, use_column):
            return None, []
        value, derivation = self._integer(assignment.value, assignment, depth + 1, seen | {name})
        if value is None:
            return None, []
        if owner is not self.scopes.root:
            scope_evidence_id = self._numeric_scope_evidence(owner)
            if scope_evidence_id is None:
                return None, []
        line, _, column = location(assignment)
        end_line: int = assignment.end_lineno if assignment.end_lineno is not None else line
        end_column: int = (
            assignment.end_col_offset if assignment.end_col_offset is not None else column
        )
        origin: _NumericAlias = {
            "name": name,
            "value": value,
            "expression": ast.unparse(assignment.value),
            "evidence_id": evidence_id,
            "line": line,
            "column": column,
            "end_line": end_line,
            "end_column": end_column,
        }
        if scope_evidence_id is not None:
            origin["scope_evidence_id"] = scope_evidence_id
            origin["scope_owner"] = owner.qualified_name
            scope_line, _, scope_column = location(owner.node)
            origin["scope_symbol_id"] = stable_id(
                "SYM", owner.qualified_name, self.module.rel_path, scope_line, scope_column
            )
        return value, [origin, *derivation]

    def _numeric_scope_evidence(self, owner: Scope) -> str | None:
        node = owner.node
        if not isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            return None
        line, end_line, column = location(node)
        if end_line > len(self.module.lines) or line < 1:
            return None
        excerpt = "\n".join(self.module.lines[line - 1 : end_line])
        if not excerpt or len(excerpt) > MAX_NUMERIC_EVIDENCE_CHARS:
            return None
        evidence_id = stable_id(
            "EVD", self.module.rel_path, line, end_line, column, "numeric_scope"
        )
        self.evidence[evidence_id] = {
            "id": evidence_id,
            "file": self.module.rel_path,
            "line": line,
            "end_line": end_line,
            "column": column,
            "excerpt": excerpt,
        }
        return evidence_id

    def _numeric_use_scope_chain(self, use: ast.AST) -> list[dict[str, str]] | None:
        scope = self.scopes.by_node.get(use)
        chain: list[dict[str, str]] = []
        anonymous = False
        while scope is not None and scope is not self.scopes.root:
            if not isinstance(scope.node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                if isinstance(
                    scope.node,
                    ast.Lambda | ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
                ):
                    anonymous = True
                    scope = scope.parent
                    continue
                return None
            evidence_id = self._numeric_scope_evidence(scope)
            if evidence_id is None:
                return None
            line, _, column = location(scope.node)
            chain.append(
                {
                    "scope_owner": scope.qualified_name,
                    "scope_evidence_id": evidence_id,
                    "scope_symbol_id": stable_id(
                        "SYM", scope.qualified_name, self.module.rel_path, line, column
                    ),
                }
            )
            scope = scope.parent
        if anonymous and not chain:
            return None
        return chain

    @staticmethod
    def _terminal_name(node: ast.expr) -> str | None:
        return (
            node.id
            if isinstance(node, ast.Name)
            else node.attr
            if isinstance(node, ast.Attribute)
            else None
        )

    def _modulo(
        self, node: ast.BinOp | ast.AugAssign, left: ast.expr, right: ast.expr, form: str
    ) -> None:
        subject = self._terminal_name(left)
        value, derivation = self._integer(right, node)
        binding_scopes: list[dict[str, str]] | None = (
            self._numeric_use_scope_chain(node)
            if any(
                isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load)
                for item in ast.walk(right)
            )
            else []
        )
        if binding_scopes is None:
            value, derivation = None, []
        evidence_lines = [node.lineno, *(item["line"] for item in derivation)]
        if value is not None and (
            node.end_lineno != node.lineno
            or any(item["line"] != item["end_line"] for item in derivation)
            or any(
                not isinstance(line, int)
                or line < 1
                or line > len(self.module.lines)
                or len(self.module.lines[line - 1]) > MAX_NUMERIC_EVIDENCE_CHARS
                or not _numeric_evidence_excerpt_supported(self.module.lines[line - 1])
                for line in evidence_lines
            )
        ):
            value, derivation = None, []
        start = (node.lineno, node.col_offset)
        end = (
            node.end_lineno if node.end_lineno is not None else node.lineno,
            node.end_col_offset if node.end_col_offset is not None else node.col_offset,
        )
        evidence_id = add_evidence(self.evidence, self.module, node)
        evidence_ids = [evidence_id]
        for item in derivation:
            alias_evidence = item.get("evidence_id")
            if not isinstance(alias_evidence, str):
                raise AssertionError("numeric alias proof must retain its evidence id")
            evidence_ids.append(alias_evidence)
            scope_evidence = item.get("scope_evidence_id")
            if isinstance(scope_evidence, str):
                evidence_ids.append(scope_evidence)
        evidence_ids.extend(scope["scope_evidence_id"] for scope in binding_scopes or [])
        owner = self.scope_stack[-1]
        self.items.append(
            classified(
                item_id=stable_id(
                    "CONSTRUCT", self.module.rel_path, *start, *end, "numeric_operand"
                ),
                evidence_class=EvidenceClass.FACT,
                area="constructs",
                kind="numeric_operand",
                title=f"{owner} uses modulo operand",
                subjects=[owner],
                evidence_ids=evidence_ids,
                data={
                    "owner": owner,
                    "module": self.module.module,
                    "operation": "modulo",
                    "form": form,
                    "line": start[0],
                    "column": start[1],
                    "end_line": end[0],
                    "end_column": end[1],
                    "subject": subject,
                    "proof": "known" if value is not None else "unknown",
                    "value": value,
                    "derivation": derivation,
                    "binding_scopes": binding_scopes or [],
                },
            )
        )

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Mod):
            self._modulo(node, node.left, node.right, "binary")
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.op, ast.Mod):
            self._modulo(node, node.target, node.value, "augmented")
        self.generic_visit(node)

    def _receiver_type(self, node: ast.expr) -> str | None:
        if not isinstance(node, ast.Name):
            return None
        binding = self.scopes.lookup(node, node.id)
        if binding.owner is None or binding.uncertain:
            return None
        for index in reversed(range(len(self.receiver_types))):
            scope = self.receiver_types[index]
            if (
                node.id in scope
                and self.receiver_scope_names[index] == binding.owner.qualified_name
            ):
                return scope[node.id]
        return None

    def _parameter_receiver(self, node: ast.expr) -> bool:
        return isinstance(node, ast.Name) and any(
            node.id in frame for frame in self.parameter_receivers
        )

    def _receiver_binding(
        self, expression: ast.expr | None, use: ast.AST
    ) -> tuple[
        str | None,
        dict[str, object] | None,
        str | None,
        list[str],
        str | None,
        list[dict[str, str]] | None,
    ]:
        if expression is None:
            return None, None, None, [], None, None
        if isinstance(expression, ast.Name):
            declared = self._declared_receiver_binding(expression, use)
            if declared is not None:
                return declared
        if self.call_collector is None:
            return self._receiver_type(expression), None, None, [], None, None
        call_site = use if isinstance(use, ast.Call) else expression
        if isinstance(expression, ast.Attribute):
            stored = self.call_collector._stored_type(expression)
            if stored is not None:
                target, evidence, proof = stored
                evidence = self._local_evidence(evidence)
                return (
                    target,
                    {
                        "origin": CallBindingOrigin.STORED_RECEIVER.value,
                        "target": target,
                        "evidence_ids": evidence,
                        "proof": proof,
                    },
                    None,
                    evidence,
                    None,
                    None,
                )
        constructed = self.call_collector._constructed_type(expression, call_site)
        if constructed is not None:
            target, evidence, proof = constructed
            evidence = self._local_evidence(evidence)
            return (
                target,
                {
                    "origin": CallBindingOrigin.CONSTRUCTED_RECEIVER.value,
                    "target": target,
                    "evidence_ids": evidence,
                    "proof": proof,
                },
                None,
                evidence,
                None,
                None,
            )
        return self._receiver_type(expression), None, None, [], None, None

    def _declared_receiver_binding(
        self, expression: ast.Name, use: ast.AST
    ) -> (
        tuple[
            str,
            dict[str, object],
            str,
            list[str],
            str,
            list[dict[str, str]],
        ]
        | None
    ):
        lexical = self.scopes.lookup(expression, expression.id)
        if lexical.owner is None or lexical.uncertain:
            return None
        binding_sites = lexical.owner.bindings.get(expression.id, [])
        if len(binding_sites) != 1 or not isinstance(binding_sites[0], ast.arg):
            return None
        for index in reversed(range(len(self.parameter_annotations))):
            frame = self.parameter_annotations[index]
            owner = self.receiver_scope_names[index]
            if expression.id not in frame or owner != lexical.owner.qualified_name:
                continue
            scopes = self._selector_parameter_scope_chain(use, lexical.owner)
            if scopes is None:
                return None
            target, annotation = frame[expression.id]
            support_evidence = [add_evidence(self.evidence, self.module, annotation)]
            support_evidence.extend(item["scope_evidence_id"] for item in scopes)
            if self.symbol_index is not None:
                support_evidence.extend(self._selector_declaration_evidence((owner, target)))
            support_evidence = sorted(set(support_evidence))
            proof: dict[str, object] = {
                "origin": CallBindingOrigin.DECLARED_RECEIVER.value,
                "target": target,
                "evidence_ids": support_evidence,
            }
            return target, proof, expression.id, support_evidence, owner, scopes
        return None

    def _selector_declaration_evidence(self, owners: tuple[str, str]) -> list[str]:
        if self.symbol_index is None:
            return []
        evidence: list[str] = []
        for qualified_name in (owners[0], self.scope_stack[-1], owners[1]):
            declaration = self.symbol_index.binding_declarations.get(qualified_name)
            if declaration is None:
                continue
            declaration_data: dict[str, RawJson] = declaration["data"]
            if declaration_data.get("module") == self.module.module:
                evidence.extend(declaration["evidence_ids"])
        return evidence

    def _selector_parameter_scope_chain(
        self, use: ast.AST, parameter_scope: Scope
    ) -> list[dict[str, str]] | None:
        scopes: list[Scope] = []
        current = self.scopes.by_node.get(use)
        while current is not None:
            scopes.append(current)
            if current is parameter_scope:
                break
            current = current.parent
        if not scopes or scopes[-1] is not parameter_scope:
            return None
        chain: list[dict[str, str]] = []
        for scope in scopes:
            if isinstance(
                scope.node,
                ast.Lambda | ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
            ):
                continue
            if not isinstance(scope.node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                return None
            evidence_id = self._numeric_scope_evidence(scope)
            if evidence_id is None:
                return None
            line, _, column = location(scope.node)
            chain.append(
                {
                    "scope_owner": scope.qualified_name,
                    "scope_evidence_id": evidence_id,
                    "scope_symbol_id": stable_id(
                        "SYM", scope.qualified_name, self.module.rel_path, line, column
                    ),
                }
            )
        return chain

    def _local_evidence(self, identifiers: list[str]) -> list[str]:
        return sorted(
            identifier
            for identifier in set(identifiers)
            if (item := self.evidence.get(identifier)) is not None
            and item.get("file") == self.module.rel_path
        )

    def _builtin_call(self, node: ast.expr, name: str) -> bool:
        if isinstance(node, ast.Name) and node.id == name:
            binding = self.comparisons.scopes.lookup(node, node.id)
            return binding.kind is BindingKind.UNBOUND and not binding.uncertain
        if (
            isinstance(node, ast.Attribute)
            and node.attr == name
            and isinstance(node.value, ast.Name)
            and node.value.id == "builtins"
        ):
            binding = self.comparisons.scopes.lookup(node.value, node.value.id)
            if binding.kind is BindingKind.UNBOUND and not binding.uncertain:
                return True
            if binding.owner is None or binding.uncertain:
                return False
            sites = binding.owner.bindings.get(node.value.id, [])
            return (
                len(sites) == 1
                and isinstance(sites[0], ast.Import)
                and any(
                    alias.name == "builtins" and alias.asname is None for alias in sites[0].names
                )
            )
        return False

    def _selector_record(
        self,
        node: ast.AST,
        role: str,
        receiver: str | None,
        member: str | None,
        literal: str | None = None,
        status: str = "decided",
        operation: str = "read",
        receiver_node: ast.expr | None = None,
    ) -> None:
        owner = self.scope_stack[-1]
        line, _, column = location(node)
        evidence_id = add_evidence(self.evidence, self.module, node)
        (
            receiver,
            status,
            receiver_binding,
            receiver_parameter,
            receiver_evidence,
            receiver_parameter_owner,
            receiver_parameter_scopes,
        ) = self._selector_receiver_proof(node, role, receiver, literal, status, receiver_node)
        if receiver_parameter_owner is not None and not self.include_parameter_owner_proof:
            receiver = None
            status = "unknown"
            receiver_binding = None
            receiver_parameter = None
            receiver_evidence = []
            receiver_parameter_owner = None
            receiver_parameter_scopes = None
        data: RecordData = {
            "owner": owner,
            "construct": "selector",
            "selector_role": role,
            "receiver_type": receiver,
            "member": member,
            "literal": literal,
            "status": status,
            "operation": operation,
            "receiver_binding": receiver_binding,
            "receiver_parameter": receiver_parameter,
            **(
                {
                    "receiver_parameter_owner": receiver_parameter_owner,
                    "receiver_parameter_scopes": receiver_parameter_scopes,
                }
                if receiver_parameter_owner is not None and self.include_parameter_owner_proof
                else {}
            ),
        }
        item_id = stable_id(
            "CONSTRUCT-SELECTOR",
            self.module.rel_path,
            line,
            column,
            role,
            receiver or "",
            member or "",
            literal or "",
            operation,
        )

        if item_id in self.selector_ids:
            return
        self.selector_ids.add(item_id)
        self.items.append(
            classified(
                item_id=item_id,
                evidence_class=EvidenceClass.FACT,
                area="constructs",
                kind="construct_selector",
                title=f"{owner} has a {role} selector observation",
                subjects=[owner],
                evidence_ids=[evidence_id, *receiver_evidence],
                data=data,
            )
        )

    def _selector_receiver_proof(
        self,
        node: ast.AST,
        role: str,
        receiver: str | None,
        literal: str | None,
        status: str,
        receiver_node: ast.expr | None,
    ) -> tuple[
        str | None,
        str,
        dict[str, object] | None,
        str | None,
        list[str],
        str | None,
        list[dict[str, str]] | None,
    ]:
        (
            proven_receiver,
            receiver_binding,
            receiver_parameter,
            receiver_evidence,
            receiver_parameter_owner,
            receiver_parameter_scopes,
        ) = self._receiver_binding(receiver_node, node)
        if receiver is None and proven_receiver is not None:
            receiver = proven_receiver
            if role in {"read", "write", "call", "reflect", "constructor", "type_probe"} or (
                literal is not None
            ):
                status = "decided"
        elif receiver is not None and proven_receiver is not None and receiver != proven_receiver:
            receiver = None
        if receiver_node is None and receiver is not None and self.symbol_index is not None:
            declaration = self.symbol_index.binding_declarations.get(receiver)
            if declaration is not None:
                declaration_data: dict[str, RawJson] = declaration["data"]
                declaration_module = declaration_data.get("module")
                if declaration_module == self.module.module:
                    receiver_evidence = list(declaration["evidence_ids"])
                else:
                    receiver_evidence = self._selector_import_evidence(node, role, receiver)
                if receiver_evidence:
                    receiver_binding = {
                        "origin": CallBindingOrigin.DIRECT.value,
                        "target": receiver,
                        "evidence_ids": receiver_evidence,
                    }
                else:
                    status = "unknown"
                    receiver = None
        if receiver is not None and receiver_node is not None and receiver_binding is None:
            status = "unknown"
            receiver = None
        if receiver_binding is not None and not self._selector_excerpt_replays(node):
            # The validator deliberately proves selectors from their bounded source excerpt.
            # A selector inside a multiline expression can start on a line that is not a
            # standalone Python fragment (for example ``), FilesToWrite()``). Do not emit a
            # typed receiver binding that the independent reader cannot replay from that line.
            status = "unknown"
            receiver = None
            receiver_binding = None
            receiver_parameter = None
            receiver_parameter_owner = None
            receiver_parameter_scopes = None
            receiver_evidence = []
        return (
            receiver,
            status,
            receiver_binding,
            receiver_parameter,
            receiver_evidence,
            receiver_parameter_owner,
            receiver_parameter_scopes,
        )

    def _selector_excerpt_replays(self, node: ast.AST) -> bool:
        line, _, _ = location(node)
        line_text: str = self.module.lines[line - 1] if line <= len(self.module.lines) else ""
        excerpt: str = line_text.rstrip()
        if not excerpt:
            return False
        try:
            ast.parse(excerpt)
            return True
        except (IndentationError, SyntaxError, ValueError, RecursionError):
            try:
                ast.parse(f"if True:\n{excerpt}\n")
                return True
            except (IndentationError, SyntaxError, ValueError, RecursionError):
                trimmed: str = excerpt.rstrip()
                if isinstance(node, ast.Match) and trimmed.endswith(":"):
                    indentation: str = excerpt.lstrip(" ")
                    indent = len(excerpt) - len(indentation)
                    try:
                        ast.parse(f"if True:\n{excerpt}\n{' ' * (indent + 4)}case _: pass\n")
                        return True
                    except (IndentationError, SyntaxError, ValueError, RecursionError):
                        pass
                return False

    def _selector_import_evidence(self, node: ast.AST, role: str, target: str) -> list[str]:
        expression = (
            node.func
            if role == "constructor" and isinstance(node, ast.Call)
            else (
                node.args[1]
                if role == "type_probe" and isinstance(node, ast.Call) and len(node.args) > 1
                else node
                if role == "type_probe"
                else None
            )
        )
        if expression is None:
            return []
        suffix: list[str] = []
        root = expression
        while isinstance(root, ast.Attribute):
            suffix.append(root.attr)
            root = root.value
        if not isinstance(root, ast.Name):
            return []
        if role == "type_probe":
            direct_targets = self._direct_selector_import_targets(root.id)
            if target not in direct_targets:
                return []
        matches = self._selector_import_matches(root.id, target, suffix)
        return list(matches[0]["evidence_ids"]) if len(matches) == 1 else []

    def _direct_selector_import_targets(self, binding: str) -> set[str]:
        targets: set[str] = set()
        for item in self.imports:
            data: RecordData = item["data"]
            target_module = data.get("target_module")
            symbol = data.get("symbol")
            if (
                data.get("source_module") == self.module.module
                and data.get("binding") == binding
                and isinstance(target_module, str)
                and isinstance(symbol, str)
            ):
                targets.add(f"{target_module}.{symbol}")
        return targets

    def _selector_import_matches(
        self, binding: str, target: str, suffix: list[str]
    ) -> list[RawRecord]:
        matches: list[RawRecord] = []
        for item in self.imports:
            data: RecordData = item["data"]
            origin = data.get("origin_definition")
            if (
                data.get("source_module") == self.module.module
                and data.get("binding") == binding
                and isinstance(origin, str)
                and target == ".".join([origin, *reversed(suffix)])
            ):
                matches.append(item)
        return matches

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_definition_header(node)
        qualified = f"{self.scope_stack[-1]}.{node.name}"
        self.scope_stack.append(qualified)
        self.inherits_stack.append(bool(node.bases))
        for statement in node.body:
            self.visit(statement)
        self.inherits_stack.pop()
        self.scope_stack.pop()

    def _visit_definition_header(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    ) -> None:
        for child in ast.iter_child_nodes(node):
            if child not in node.body:
                self.visit(child)

    def _placeholder_form(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
        """Name what the body holds instead of an implementation, or nothing when it is one."""
        if _STUB_DECORATORS.intersection(decorator_names(node)):
            return None
        # A class with a base declares a shape its members may leave empty on purpose.
        if self.inherits_stack and self.inherits_stack[-1]:
            return None
        if body_is_empty(node):
            return "empty"
        return "not_implemented" if _raises_not_implemented(node) else None

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._visit_definition_header(node)
        qualified = f"{self.scope_stack[-1]}.{node.name}"
        self.scope_stack.append(qualified)
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        receivers = {
            argument.arg: (
                annotation_target
                if argument.annotation is not None
                and (annotation_target := self.comparisons._canonical_name(argument.annotation))
                in self.local_classes
                else None
            )
            for argument in arguments
        }
        for statement in own_scope(node):
            targets: list[ast.expr] = []
            if isinstance(statement, ast.Assign):
                targets = statement.targets
            elif isinstance(statement, ast.AnnAssign | ast.AugAssign):
                targets = [statement.target]
            elif isinstance(statement, ast.For | ast.AsyncFor):
                targets = [statement.target]
            elif isinstance(statement, ast.NamedExpr):
                targets = [statement.target]
            elif isinstance(statement, ast.withitem) and statement.optional_vars is not None:
                targets = [statement.optional_vars]
            for target in targets:
                for part in ast.walk(target):
                    if (
                        isinstance(part, ast.Name)
                        and isinstance(part.ctx, ast.Store)
                        and part.id in receivers
                    ):
                        binding = self.scopes.lookup(part, part.id)
                        if binding.owner is not None and binding.owner.qualified_name == qualified:
                            receivers[part.id] = None
            if isinstance(statement, ast.ExceptHandler) and statement.name in receivers:
                receivers[statement.name] = None
        parameter_annotations = {
            argument.arg: (
                annotation_target,
                argument.annotation,
            )
            for argument in arguments
            if argument.annotation is not None
            and (annotation_target := self.comparisons._canonical_name(argument.annotation))
            in self.local_classes
            and receivers.get(argument.arg) == annotation_target
        }
        self.receiver_types.append(receivers)
        self.receiver_scope_names.append(qualified)
        self.parameter_receivers.append({argument.arg for argument in arguments})
        self.parameter_annotations.append(parameter_annotations)
        form = self._placeholder_form(node)
        if form is not None:
            self._record(
                node, kind="placeholder_body", construct="placeholder_body", handled=None, form=form
            )
        for statement in node.body:
            self.visit(statement)
        self.parameter_receivers.pop()
        self.parameter_annotations.pop()
        self.receiver_scope_names.pop()
        self.receiver_types.pop()
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self._record(node, kind="assert_statement", construct="assert", handled=None)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None or _is_broad_type(node.type):
            handled = [] if node.type is None else _handled_types(node.type)
            self._record(node, kind="broad_except", construct="broad_except", handled=handled)
        self.generic_visit(node)

    def _reflection_selector(self, node: ast.Call, name: str) -> None:
        if node.args and self._builtin_call(node.func, name):
            receiver = self._receiver_type(node.args[0])
            member = self.comparisons.string_value(node.args[1]) if len(node.args) > 1 else None
            if member is not None:
                self._selector_record(
                    node,
                    "reflect",
                    receiver,
                    member,
                    status="decided" if receiver is not None else "unknown",
                    operation="probe",
                    receiver_node=node.args[0],
                )
            else:
                self._selector_record(
                    node,
                    "reflect",
                    receiver,
                    None,
                    status="unknown",
                    operation="probe",
                    receiver_node=node.args[0],
                )
        elif node.keywords:
            self._selector_record(node, "reflect", None, None, status="unknown", operation="probe")

    def _selected_type_call(self, node: ast.Call, name: str | None) -> None:
        if name in {"isinstance", "issubclass"} and self._builtin_call(node.func, name):
            if len(node.args) >= 2:
                target = self.comparisons._canonical_name(node.args[1])
                if target in self.local_classes:
                    self._selector_record(
                        node.args[1],
                        "type_probe",
                        target,
                        None,
                        operation="probe",
                        receiver_node=node.args[1] if node.lineno != node.end_lineno else None,
                    )
        target = self.comparisons._canonical_name(node.func)
        if target in self.local_classes:
            self._selector_record(node, "constructor", target, None, operation="construct")

    def _string_predicate_selector(
        self, node: ast.Call, predicate: _StringPredicate | None
    ) -> None:
        if predicate is None or not isinstance(node.func, ast.Attribute) or not node.args:
            return
        selected = node.func.value
        receiver_node = selected.value if isinstance(selected, ast.Attribute) else selected
        receiver_type = (
            self._receiver_type(selected.value)
            if isinstance(selected, ast.Attribute)
            else self._receiver_type(selected)
        )
        member = selected.attr if isinstance(selected, ast.Attribute) else node.func.attr
        if receiver_type is None and not isinstance(selected, ast.Attribute):
            return
        literals = self.comparisons.string_values(node.args[0])
        if literals is not None:
            for literal in dict.fromkeys(literals):
                self._selector_record(
                    node,
                    predicate.value,
                    receiver_type,
                    member,
                    literal,
                    "decided" if receiver_type is not None else "unknown",
                    "compare",
                    receiver_node,
                )
        else:
            self._selector_record(
                node,
                predicate.value,
                receiver_type,
                member,
                status="unknown",
                operation="compare",
                receiver_node=receiver_node,
            )

    def visit_Call(self, node: ast.Call) -> None:
        name = _as_written(node.func)
        if name is not None and name in _REFLECTION_CALLS and self._builtin_call(node.func, name):
            self._record(node, kind=_REFLECTION_CALLS[name], construct=name, handled=None)
            self._reflection_selector(node, name)
        self._selected_type_call(node, name)
        predicate = _string_predicate(node)
        if (
            predicate is not None
            and node.args
            and _predicate_matches(self.comparisons, node.args[0])
        ):
            self._record(
                node,
                kind="string_literal_compare",
                construct="string_literal_compare",
                handled=None,
                form=predicate.value,
            )
        self._string_predicate_selector(node, predicate)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Both nodes of `x.__dict__.__dict__` start at one column, so one id; the inner records.
        outer_of_chain = isinstance(node.value, ast.Attribute) and node.value.attr == "__dict__"
        if node.attr == "__dict__" and not outer_of_chain:
            self._record(node, kind="dunder_dict", construct="dunder_dict", handled=None)
        receiver = self._receiver_type(node.value)
        unresolved_name = isinstance(node.value, ast.Name) and node.value.id not in {"self", "cls"}
        expression_receiver = isinstance(node.value, ast.Attribute | ast.Call)
        if (
            receiver is not None
            or self._parameter_receiver(node.value)
            or unresolved_name
            or expression_receiver
        ):
            parent = self.parents.get(node)
            operation = (
                "call"
                if isinstance(parent, ast.Call) and parent.func is node
                else ("write" if isinstance(node.ctx, ast.Store) else "read")
            )
            if not self._is_nonruntime_attribute_context(
                node, parent
            ) and not self._has_role_specific_attribute_operand(node, parent):
                self._selector_record(
                    node,
                    operation,
                    receiver,
                    node.attr,
                    status="decided" if receiver is not None else "unknown",
                    operation=operation,
                    receiver_node=node.value,
                )
        self.generic_visit(node)

    def _is_nonruntime_attribute_context(self, node: ast.Attribute, parent: ast.AST | None) -> bool:
        current: ast.AST = node
        while parent is not None:
            if isinstance(parent, ast.ExceptHandler) and parent.type is current:
                return True
            if isinstance(parent, ast.arg) and parent.annotation is current:
                return True
            if isinstance(parent, ast.AnnAssign) and parent.annotation is current:
                return True
            if (
                isinstance(parent, ast.FunctionDef | ast.AsyncFunctionDef)
                and parent.returns is current
            ):
                return True
            if (
                sys.version_info >= (3, 12)
                and isinstance(parent, ast.TypeAlias)
                and parent.value is current
            ):
                return True
            if isinstance(
                parent, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
            ):
                return False
            current, parent = parent, self.parents.get(parent)
        return False

    def _has_role_specific_attribute_operand(
        self, node: ast.Attribute, parent: ast.AST | None
    ) -> bool:
        if isinstance(parent, ast.Compare) and node in [parent.left, *parent.comparators]:
            return True
        if isinstance(parent, ast.Match) and parent.subject is node:
            return True
        if isinstance(parent, ast.Attribute) and parent.value is node:
            call = self.parents.get(parent)
            return (
                isinstance(call, ast.Call)
                and call.func is parent
                and _string_predicate(call) is not None
            )
        return False

    def visit_Compare(self, node: ast.Compare) -> None:
        form = _comparison_form(self.comparisons, node)
        if form is not None:
            self._record(
                node,
                kind="string_literal_compare",
                construct="string_literal_compare",
                handled=None,
                form=form,
            )
        operands = [node.left, *node.comparators]
        for operator, left, right in zip(node.ops, operands[:-1], operands[1:], strict=True):
            role = (
                "equality"
                if isinstance(operator, ast.Eq | ast.NotEq)
                else ("membership" if isinstance(operator, ast.In | ast.NotIn) else None)
            )
            if role is None:
                continue
            for selected, other in ((left, right), (right, left)):
                if isinstance(selected, ast.Attribute):
                    receiver = self._receiver_type(selected.value)
                    literals = (
                        self.comparisons.string_values(other)
                        if role == "membership"
                        else (
                            (value,)
                            if (value := self.comparisons.string_value(other)) is not None
                            else None
                        )
                    )
                    if literals:
                        for literal in dict.fromkeys(literals):
                            self._selector_record(
                                selected,
                                role,
                                receiver,
                                selected.attr,
                                literal,
                                "decided" if receiver is not None else "unknown",
                                "compare",
                                selected.value,
                            )
                    else:
                        self._selector_record(
                            selected,
                            role,
                            receiver,
                            selected.attr,
                            None,
                            "unknown",
                            "compare",
                            selected.value,
                        )
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        if _matches_literal(self.comparisons, node):
            self._record(
                node,
                kind="string_literal_compare",
                construct="string_literal_compare",
                handled=None,
                form="match",
            )
        if isinstance(node.subject, ast.Attribute):
            receiver_node = node.subject.value
            receiver = self._receiver_type(receiver_node)
            values: list[str] = []
            unsupported = False
            for case in node.cases:
                pattern = case.pattern
                if isinstance(pattern, ast.MatchValue):
                    literal = self.comparisons.string_value(pattern.value)
                    if literal is None:
                        unsupported = True
                    else:
                        values.append(literal)
                elif any(isinstance(part, ast.MatchValue) for part in ast.walk(pattern)):
                    unsupported = True
            status = "decided" if receiver is not None else "unknown"
            for literal in dict.fromkeys(values):
                self._selector_record(
                    node,
                    "match",
                    receiver,
                    node.subject.attr,
                    literal,
                    status,
                    "compare",
                    receiver_node,
                )
            if unsupported or not values:
                self._selector_record(
                    node,
                    "match",
                    receiver,
                    node.subject.attr,
                    None,
                    "unknown",
                    "compare",
                    receiver_node,
                )
        self.generic_visit(node)

    def _record(
        self,
        node: ast.AST,
        *,
        kind: str,
        construct: str,
        handled: list[str] | None,
        form: str | None = None,
    ) -> None:
        owner = self.scope_stack[-1]
        line, _, column = location(node)
        evidence_id = add_evidence(self.evidence, self.module, node)
        data: RecordData = {"owner": owner, "construct": construct}
        if handled is not None:
            data["handled"] = handled
        if form is not None:
            data["form"] = form
        self.items.append(
            classified(
                item_id=stable_id("CONSTRUCT", self.module.rel_path, line, column, kind),
                evidence_class=EvidenceClass.FACT,
                area="constructs",
                kind=kind,
                title=f"{owner} uses {construct}",
                subjects=[owner],
                evidence_ids=[evidence_id],
                data=data,
            )
        )


def _literal_import_origins(imports: Sequence[RawRecord]) -> dict[str, str]:
    """Reuse proven canonical symbol routes; unresolved or conditional imports add no proof."""
    origins: dict[str, str] = {}
    for item in imports:
        data = item["data"]
        origin = data.get("origin_definition")
        if (
            isinstance(origin, str)
            and data.get("module_level_import") is True
            and data.get("source_binding_unique") is True
            and data.get("origin_binding_unique") is True
            and not data.get("under_type_checking")
            and not data.get("reexport_candidate")
            and not data.get("reexport_candidates")
        ):
            origins[f"{data['source_module']}.{data['binding']}"] = origin
    return origins


def _class_member_names(module: ParsedModule) -> set[str]:
    names: set[str] = set()
    for declaration in module.tree.body:
        if not isinstance(declaration, ast.ClassDef):
            continue
        for member in declaration.body:
            if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef):
                names.add(member.name)
            elif isinstance(member, ast.Assign):
                names.update(target.id for target in member.targets if isinstance(target, ast.Name))
            elif isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name):
                names.add(member.target.id)
    return names


def collect_constructs(
    parsed: Sequence[ParsedModule],
    evidence: dict[str, RawEvidence],
    *,
    imports: Sequence[RawRecord] = (),
    symbol_index: SymbolIndex | None = None,
    receiver_resolvers: Sequence[SelectorReceiverResolver] = (),
    include_parameter_owner_proof: bool = True,
) -> list[RawRecord]:
    """Collect written constructs using scanned literal providers and resolved import origins."""
    contexts = [_LiteralComparisons(module) for module in parsed]
    counts = Counter(module.module for module in parsed)
    providers = [context for context in contexts if counts[context.module.module] == 1]
    scalar_names = frozenset(name for context in providers for name in context.scalar_names)
    enum_member_names = frozenset(
        name for context in providers for name in context.enum_member_names
    )
    origins = _literal_import_origins(imports)
    known_classes = {
        f"{module.module.module}.{node.name}"
        for module in providers
        for node in module.module.tree.body
        if isinstance(node, ast.ClassDef)
    }
    if symbol_index is not None:
        for item in imports:
            data: dict[str, RawJson] = item["data"]
            origin = data.get("origin_definition")
            if not isinstance(origin, str):
                continue
            declaration = symbol_index.binding_declarations.get(origin)
            if (
                declaration is not None
                and declaration["kind"] == "class"
                and data.get("source_binding_unique") is True
                and data.get("origin_binding_unique") is True
            ):
                known_classes.add(origin)
    items: list[RawRecord] = []
    resolvers = receiver_resolvers or (None,) * len(parsed)
    for module, context, call_collector in zip(parsed, contexts, resolvers, strict=True):
        context.scalar_names = scalar_names
        context.enum_member_names = enum_member_names
        context.origins = origins
        context.collections = _literal_collections(context)
        collector = ConstructCollector(
            module,
            evidence,
            context,
            symbol_index,
            call_collector,
            imports,
            include_parameter_owner_proof,
        )
        collector.local_classes = known_classes
        collector.local_members = _class_member_names(module)
        collector.visit(module.tree)
        items.extend(collector.items)
    items.sort(key=lambda item: item["id"])
    return items
