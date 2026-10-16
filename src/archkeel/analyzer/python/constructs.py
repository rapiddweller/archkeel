# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Construct collection: asserts, broad excepts, empty bodies, reflection, str literal compares."""

from __future__ import annotations

import ast
from collections.abc import Sequence
from enum import Enum

from archkeel.ir.facts import EvidenceClass, stable_id
from archkeel.ir.facts_codec import RawData as RecordData
from archkeel.ir.facts_codec import RawEvidence, RawRecord, classified

from .scopes import LexicalScopes
from .source import ParsedModule, add_evidence, body_is_empty, decorator_names, location


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
_REFLECTION_CALLS = {"setattr": "setattr_call", "delattr": "delattr_call", "vars": "vars_call"}
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
    module: ParsedModule, scopes: LexicalScopes
) -> dict[str, ast.Tuple | ast.List | ast.Set]:
    """Retain qualified literal nodes; only tuples also serve predicate arguments."""
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
            and all(_is_str(item) for item in value.elts)
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
            if not member_name.startswith("_") and _is_str(child.value):
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
        self.scopes = LexicalScopes(module)
        self.module_values, self.class_values, self.enum_classes = _static_string_constants(module)
        self.collections = _literal_collections(module, self.scopes)
        self.enum_value_classes = frozenset(
            f"{module.module}.{node.name}"
            for node in module.tree.body
            if isinstance(node, ast.ClassDef)
            and len(node.bases) == 1
            and self._enum_base(node.bases[0])
            and not node.keywords
            and not node.decorator_list
            and _literal_enum_body(node)
        )

    def _module_name(self, node: ast.expr) -> bool:
        root = node
        while isinstance(root, ast.Attribute):
            root = root.value
        if not isinstance(root, ast.Name):
            return False
        binding = self.scopes.lookup(root, root.id)
        return binding.owner is self.scopes.root and not binding.uncertain

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
            and _is_str(assignment.value)
        )

    def scalar(self, node: ast.expr) -> bool:
        if _is_str(node) or (isinstance(node, ast.Name) and self._local_scalar(node)):
            return True
        if not self._module_name(node):
            return False
        if isinstance(node, ast.Name):
            return self.module_values.get(node.id) is not None
        if not isinstance(node, ast.Attribute):
            return False
        owner = _dotted_name(node.value)
        if owner is None:
            return False
        class_name = f"{self.module.module}.{owner}"
        if class_name in self.class_values and class_name not in self.enum_classes:
            return self.class_values[class_name].get(node.attr) is not None
        member = node.value
        if (
            node.attr != "value"
            or not isinstance(member, ast.Attribute)
            or not isinstance(member.value, ast.Name)
        ):
            return False
        enum_class = f"{self.module.module}.{member.value.id}"
        values = self.class_values.get(enum_class, {})
        return (
            enum_class in self.enum_value_classes
            and "value" not in values
            and values.get(member.attr) is not None
        )

    def collection(self, node: ast.expr) -> bool:
        if isinstance(node, ast.Tuple | ast.List | ast.Set):
            return bool(node.elts) and all(self.scalar(item) for item in node.elts)
        return (
            isinstance(node, ast.Name) and node.id in self.collections and self._module_name(node)
        )

    def predicate(self, node: ast.expr) -> bool:
        if isinstance(node, ast.Tuple):
            return any(self.scalar(item) for item in node.elts)
        return self.scalar(node) or (
            isinstance(node, ast.Name)
            and node.id in self.collections
            and isinstance(self.collections[node.id], ast.Tuple)
            and self._module_name(node)
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

    def __init__(self, module: ParsedModule, evidence: dict[str, RawEvidence]) -> None:
        self.module = module
        self.evidence = evidence
        self.items: list[RawRecord] = []
        self.scope_stack: list[str] = [module.module]
        self.comparisons = _LiteralComparisons(module)
        self.inherits_stack: list[bool] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified = f"{self.scope_stack[-1]}.{node.name}"
        self.scope_stack.append(qualified)
        self.inherits_stack.append(bool(node.bases))
        self.generic_visit(node)
        self.inherits_stack.pop()
        self.scope_stack.pop()

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
        self.scope_stack.append(f"{self.scope_stack[-1]}.{node.name}")
        form = self._placeholder_form(node)
        if form is not None:
            self._record(
                node, kind="placeholder_body", construct="placeholder_body", handled=None, form=form
            )
        self.generic_visit(node)
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

    def visit_Call(self, node: ast.Call) -> None:
        name = _as_written(node.func)
        if name is not None and name in _REFLECTION_CALLS:
            self._record(node, kind=_REFLECTION_CALLS[name], construct=name, handled=None)
        predicate = _string_predicate(node)
        if predicate is not None and node.args and self.comparisons.predicate(node.args[0]):
            self._record(
                node,
                kind="string_literal_compare",
                construct="string_literal_compare",
                handled=None,
                form=predicate.value,
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Both nodes of `x.__dict__.__dict__` start at one column, so one id; the inner records.
        outer_of_chain = isinstance(node.value, ast.Attribute) and node.value.attr == "__dict__"
        if node.attr == "__dict__" and not outer_of_chain:
            self._record(node, kind="dunder_dict", construct="dunder_dict", handled=None)
        self.generic_visit(node)

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


def collect_constructs(
    parsed: Sequence[ParsedModule], evidence: dict[str, RawEvidence]
) -> list[RawRecord]:
    """Run the construct collector over every module and sort records by id."""
    items: list[RawRecord] = []
    for module in parsed:
        collector = ConstructCollector(module, evidence)
        collector.visit(module.tree)
        items.extend(collector.items)
    items.sort(key=lambda item: item["id"])
    return items
