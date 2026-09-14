# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Conservative deterministic AST scanner for the Python architecture profile."""

from __future__ import annotations

import ast
import builtins
import hashlib
import importlib.util
import io
import tokenize
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from archkeel.ir.model import (
    ArchitectureContract,
    ContractComponent,
    ContractDeclarations,
    ContractPath,
    EvidenceClass,
    in_scope,
)

from .graph import condensation_ranks, strongly_connected_components, transitive_paths
from .records import classified, stable_id
from .violations import rule_scopes, rule_violations

_MUTATING_METHODS = {
    "add",
    "append",
    "clear",
    "discard",
    "extend",
    "insert",
    "pop",
    "popitem",
    "remove",
    "reverse",
    "setdefault",
    "sort",
    "update",
}
_BUILTINS = frozenset(dir(builtins))


def _location(node: ast.AST) -> tuple[int, int, int]:
    if not isinstance(node, ast.stmt | ast.expr | ast.excepthandler | ast.arg | ast.keyword):
        return 1, 1, 0
    line = max(node.lineno, 1)
    return line, node.end_lineno or line, node.col_offset


@dataclass(frozen=True)
class AliasBinding:
    target: str
    kind: str
    imported_name: str | None = None


@dataclass
class ParsedModule:
    path: Path
    rel_path: str
    module: str
    package: str
    source: str
    source_bytes: bytes
    lines: list[str]
    tree: ast.Module
    aliases: dict[str, AliasBinding] = field(default_factory=dict)
    all_exports: set[str] = field(default_factory=set)


@dataclass
class ScanResult:
    source_digest: str
    coverage: dict[str, Any]
    evidence: list[dict[str, Any]]
    scope_observations: list[dict[str, Any]]
    packages: list[dict[str, Any]]
    modules: list[dict[str, Any]]
    symbols: list[dict[str, Any]]
    imports: list[dict[str, Any]]
    dependency_edges: list[dict[str, Any]]
    transitive_paths: list[dict[str, Any]]
    path_observations: list[dict[str, Any]]
    cycles: list[dict[str, Any]]
    calls: list[dict[str, Any]]
    typing_signals: list[dict[str, Any]]
    contexts: list[dict[str, Any]]
    context_evidence: list[dict[str, Any]]
    violations: list[dict[str, Any]]
    unknowns: list[dict[str, Any]]


def iter_source_paths(root: Path, *, roots: tuple[str, ...]) -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for source_root in (root / source for source in roots)
            if source_root.is_dir()
            for path in source_root.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    )


def _module_for(path: Path, *, root: Path, namespace: str) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    prefix = namespace.split(".")
    for index in range(len(parts) - len(prefix) + 1):
        if parts[index : index + len(prefix)] == prefix:
            return ".".join(parts[index:])
    raise ValueError(f"source path does not contain configured namespace {namespace!r}")


def _package_for(module: str) -> str:
    parts = module.split(".")
    return ".".join(parts[:2]) if len(parts) > 1 else module


def _top_level_scope(module: str) -> str | None:
    parts = module.split(".")
    return ".".join(parts[:2]) if len(parts) > 1 else None


def _owning_package(module: ParsedModule) -> str:
    if module.path.name == "__init__.py":
        return module.module
    return module.module.rpartition(".")[0]


def _excerpt(module: ParsedModule, node: ast.AST) -> str:
    start, _, _ = _location(node)
    return module.lines[start - 1].rstrip() if start <= len(module.lines) else ""


def _add_evidence(evidence: dict[str, dict[str, Any]], module: ParsedModule, node: ast.AST) -> str:
    line, end_line, column = _location(node)
    # One source location is one evidence owner even when several observations
    # (for example a call and a dynamic-typing signal) refer to it.
    evidence_id = stable_id("EVD", module.rel_path, line, end_line, column)
    evidence[evidence_id] = {
        "id": evidence_id,
        "file": module.rel_path,
        "line": line,
        "end_line": end_line,
        "column": column,
        "excerpt": _excerpt(module, node),
    }
    return evidence_id


def _is_type_checking_test(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Name)
        and node.id == "TYPE_CHECKING"
        or (isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING")
    )


class _ImportCollector(ast.NodeVisitor):
    def __init__(
        self,
        module: ParsedModule,
        module_names: set[str],
        evidence: dict[str, dict[str, Any]],
        *,
        namespace: str,
    ) -> None:
        self.module = module
        self.module_names = module_names
        self.evidence = evidence
        self.namespace = namespace
        self.under_type_checking = False
        self.items: list[dict[str, Any]] = []

    def visit_If(self, node: ast.If) -> None:  # noqa: N802 - ast visitor API
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

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - ast visitor API
        for alias in node.names:
            binding = alias.asname or alias.name.split(".")[0]
            # ``import a.b`` binds ``a``; ``import a.b as b`` binds the full module.
            binding_target = alias.name if alias.asname else alias.name.split(".")[0]
            self.module.aliases[binding] = AliasBinding(target=binding_target, kind="module")
            self._record(node, target=alias.name, symbol=None, binding=binding, relative_level=0)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - ast visitor API
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
            target = submodule if submodule in self.module_names else anchor
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
        evidence_id = _add_evidence(self.evidence, self.module, node)
        target_package = (
            _package_for(target) if in_scope(target, self.namespace) else target.split(".")[0]
        )
        line, _, column = _location(node)
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
                    "reexport": self.module.path.name == "__init__.py",
                },
            )
        )


def _literal_all_exports(tree: ast.Module) -> set[str]:
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


def _annotation(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _resolve_static_name(module: ParsedModule, node: ast.AST) -> str:
    text = _annotation(node) or ""
    parts = text.split(".")
    binding = module.aliases.get(parts[0]) if parts else None
    if binding is None:
        return text
    return ".".join([binding.target, *parts[1:]])


def _decorator_names(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    names: list[str] = []
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        try:
            names.append(ast.unparse(target))
        except Exception:
            continue
    return sorted(names)


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any]:
    positional = [*node.args.posonlyargs, *node.args.args]
    parameters = [
        {"name": argument.arg, "annotation": _annotation(argument.annotation)}
        for argument in [*positional, *node.args.kwonlyargs]
    ]
    if node.args.vararg:
        parameters.append(
            {
                "name": f"*{node.args.vararg.arg}",
                "annotation": _annotation(node.args.vararg.annotation),
            }
        )
    if node.args.kwarg:
        parameters.append(
            {
                "name": f"**{node.args.kwarg.arg}",
                "annotation": _annotation(node.args.kwarg.annotation),
            }
        )
    return {
        "parameters": parameters,
        "returns": _annotation(node.returns),
        "async": isinstance(node, ast.AsyncFunctionDef),
    }


def _class_is_frozen(
    node: ast.ClassDef, module: ParsedModule, *, allow_pydantic: bool = False
) -> bool:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        name = _resolve_static_name(module, decorator.func)
        if name in {"dataclasses.dataclass", "pydantic.dataclasses.dataclass"} and any(
            keyword.arg == "frozen"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in decorator.keywords
        ):
            return True
    if not allow_pydantic:
        return False
    for child in node.body:
        if not isinstance(child, (ast.Assign, ast.AnnAssign)):
            continue
        targets = child.targets if isinstance(child, ast.Assign) else [child.target]
        value = child.value
        if not any(
            isinstance(target, ast.Name) and target.id == "model_config" for target in targets
        ):
            continue
        if (
            isinstance(value, ast.Call)
            and _resolve_static_name(module, value.func) == "pydantic.ConfigDict"
            and any(
                keyword.arg == "frozen"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in value.keywords
            )
        ):
            return True
    return False


def _collect_symbols(
    modules: Sequence[ParsedModule], evidence: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, ast.AST], dict[str, ParsedModule]]:
    symbols: list[dict[str, Any]] = []
    nodes: dict[str, ast.AST] = {}
    owners: dict[str, ParsedModule] = {}
    classes: dict[str, ast.ClassDef] = {}

    def add_symbol(
        module: ParsedModule,
        node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        qualname: str,
        kind: str,
        parent: str | None = None,
    ) -> None:
        evidence_id = _add_evidence(evidence, module, node)
        data: dict[str, Any] = {
            "qualified_name": qualname,
            "module": module.module,
            "package": module.package,
            "name": node.name,
            "visibility": "private" if node.name.startswith("_") else "public_name",
            "declared_in_all": node.name in module.all_exports,
            "parent": parent,
            "decorators": _decorator_names(node),
        }
        if isinstance(node, ast.ClassDef):
            data.update(
                {
                    "bases": sorted(filter(None, (_annotation(base) for base in node.bases))),
                    "frozen_object": _class_is_frozen(node, module),
                    "symbol_category": "class",
                }
            )
            classes[qualname] = node
        else:
            data.update(_function_signature(node))
            data["symbol_category"] = "method" if parent else "function"
        line, _, column = _location(node)
        symbols.append(
            classified(
                item_id=stable_id(
                    "SYM",
                    qualname,
                    module.rel_path,
                    line,
                    column,
                ),
                evidence_class=EvidenceClass.FACT,
                area="repository_topology",
                kind=kind,
                title=node.name,
                subjects=[qualname, module.module],
                evidence_ids=[evidence_id],
                data=data,
            )
        )
        nodes[qualname] = node
        owners[qualname] = module

    def walk_class(module: ParsedModule, node: ast.ClassDef, parent: str | None = None) -> None:
        qualname = f"{module.module}.{node.name}" if parent is None else f"{parent}.{node.name}"
        add_symbol(module, node, qualname=qualname, kind="class", parent=parent)
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add_symbol(
                    module,
                    child,
                    qualname=f"{qualname}.{child.name}",
                    kind="method",
                    parent=qualname,
                )
            elif isinstance(child, ast.ClassDef):
                walk_class(module, child, parent=qualname)

    for module in modules:
        for node in module.tree.body:
            if isinstance(node, ast.ClassDef):
                walk_class(module, node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add_symbol(module, node, qualname=f"{module.module}.{node.name}", kind="function")

    known_categories = {
        "typing.Protocol": "protocol",
        "typing_extensions.Protocol": "protocol",
        "enum.Enum": "enum",
        "enum.IntEnum": "enum",
        "enum.StrEnum": "enum",
        "pydantic.BaseModel": "pydantic_model",
    }
    symbol_by_name = {item["data"]["qualified_name"]: item for item in symbols}
    changed = True
    while changed:
        changed = False
        for qualname, node in classes.items():
            item = symbol_by_name[qualname]
            current = item["data"].get("class_kind")
            candidates: set[str] = set()
            for base in node.bases:
                base_text = _annotation(base) or ""
                tail = base_text.rsplit(".", 1)[-1]
                resolved_base = _resolve_static_name(owners[qualname], base)
                if resolved_base in known_categories:
                    candidates.add(known_categories[resolved_base])
                local_target = f"{owners[qualname].module}.{tail}"
                inherited = symbol_by_name.get(resolved_base, {}).get("data", {}).get(
                    "class_kind"
                ) or symbol_by_name.get(local_target, {}).get("data", {}).get("class_kind")
                if inherited:
                    candidates.add(inherited)
            if any(
                _resolve_static_name(
                    owners[qualname],
                    decorator.func if isinstance(decorator, ast.Call) else decorator,
                )
                in {"dataclasses.dataclass", "pydantic.dataclasses.dataclass"}
                for decorator in node.decorator_list
            ):
                candidates.add("dataclass")
            class_kind = sorted(candidates)[0] if candidates else "class"
            if current != class_kind:
                item["data"]["class_kind"] = class_kind
                changed = True
    for qualname, node in classes.items():
        item = symbol_by_name[qualname]
        item["data"]["frozen_object"] = _class_is_frozen(
            node,
            owners[qualname],
            allow_pydantic=item["data"].get("class_kind") == "pydantic_model",
        )
    return sorted(symbols, key=lambda item: item["id"]), nodes, owners


def _dotted_expression(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


class _CallCollector(ast.NodeVisitor):
    def __init__(
        self,
        module: ParsedModule,
        symbol_names: set[str],
        method_names: dict[str, list[str]],
        symbol_evidence: dict[str, list[str]],
        evidence: dict[str, dict[str, Any]],
    ) -> None:
        self.module = module
        self.symbol_names = symbol_names
        self.method_names = method_names
        self.symbol_evidence = symbol_evidence
        self.evidence = evidence
        self.items: list[dict[str, Any]] = []
        self.class_stack: list[str] = []
        self.scope_stack: list[str] = [module.module]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        qualname = f"{self.scope_stack[-1]}.{node.name}"
        self.class_stack.append(qualname)
        self.scope_stack.append(qualname)
        self.generic_visit(node)
        self.scope_stack.pop()
        self.class_stack.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.scope_stack.append(f"{self.scope_stack[-1]}.{node.name}")
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        expression = _annotation(node.func) or "<unparseable>"
        status, targets, reason, candidate_count = self._resolve(node.func)
        target_evidence_ids = sorted(
            {
                evidence_id
                for target in targets
                for evidence_id in self.symbol_evidence.get(target, [])
            }
        )
        evidence_id = _add_evidence(self.evidence, self.module, node)
        line, _, column = _location(node)
        item_id = stable_id(
            "CALL",
            self.module.rel_path,
            line,
            column,
            expression,
        )
        self.items.append(
            classified(
                item_id=item_id,
                evidence_class=EvidenceClass.FACT,
                area="call_hierarchy",
                kind=f"{status}_call",
                title=f"Call {expression}",
                subjects=[self.scope_stack[-1], *targets],
                evidence_ids=[evidence_id],
                data={
                    "source_scope": self.scope_stack[-1],
                    "source_module": self.module.module,
                    "expression": expression,
                    "status": status,
                    "targets": targets,
                    "candidate_count": candidate_count,
                    "candidates_truncated": candidate_count > len(targets),
                    "reason": reason,
                    "target_evidence_ids": target_evidence_ids,
                },
            )
        )
        self.generic_visit(node)

    def _resolve(self, func: ast.AST) -> tuple[str, list[str], str, int]:
        if isinstance(func, ast.Name):
            local = f"{self.module.module}.{func.id}"
            if local in self.symbol_names:
                return "resolved", [local], "module-local symbol", 1
            binding = self.module.aliases.get(func.id)
            if binding:
                return "resolved", [binding.target], f"imported {binding.kind} binding", 1
            if func.id in _BUILTINS:
                return "resolved", [f"builtins.{func.id}"], "Python builtin", 1
            candidates = self.method_names.get(func.id, [])
            if candidates:
                return (
                    "partially_resolved",
                    candidates[:5],
                    "name matches internal symbols without a proven binding",
                    len(candidates),
                )
            return "unresolved", [], "name has no statically indexed binding", 0

        dotted = _dotted_expression(func)
        if dotted:
            parts = dotted.split(".")
            binding = self.module.aliases.get(parts[0])
            if binding:
                target = ".".join([binding.target, *parts[1:]])
                return "resolved", [target], f"attribute of imported {binding.kind} binding", 1
            if parts[0] == "self" and self.class_stack:
                target = f"{self.class_stack[-1]}.{'.'.join(parts[1:])}"
                if target in self.symbol_names:
                    return "resolved", [target], "method on current class", 1
                return (
                    "partially_resolved",
                    [target],
                    "current-class attribute without indexed method target",
                    1,
                )
            local_class = f"{self.module.module}.{parts[0]}"
            target = f"{local_class}.{'.'.join(parts[1:])}"
            if target in self.symbol_names:
                return "resolved", [target], "class-qualified local method", 1
            candidates = self.method_names.get(parts[-1], [])
            if candidates:
                return (
                    "partially_resolved",
                    candidates[:5],
                    "dynamic receiver with matching internal methods",
                    len(candidates),
                )
            return "unresolved", [], "dynamic attribute receiver", 0
        return "unresolved", [], "call target is a dynamic expression", 0


def _annotation_signals(
    module: ParsedModule,
    node: ast.AST,
    annotation: ast.AST | None,
    *,
    owner: str,
    evidence: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    text = _annotation(annotation)
    if not text:
        return []
    assert annotation is not None
    names = {
        child.id if isinstance(child, ast.Name) else child.attr
        for child in ast.walk(annotation)
        if isinstance(child, (ast.Name, ast.Attribute))
    }
    root_name = ""
    if isinstance(annotation, ast.Subscript):
        root_name = (_annotation(annotation.value) or "").rsplit(".", 1)[-1]
    kinds: list[str] = []
    if "Any" in names:
        kinds.append("any_annotation")
    if root_name in {"dict", "Dict"} and "Any" in names:
        kinds.append("dict_any_annotation")
    if root_name == "Callable" and "Any" in names:
        kinds.append("callable_any_annotation")
    if isinstance(annotation, ast.Name) and annotation.id == "object":
        kinds.append("object_annotation")
    items: list[dict[str, Any]] = []
    for kind in sorted(set(kinds)):
        evidence_id = _add_evidence(evidence, module, node)
        line, _, _ = _location(node)
        items.append(
            classified(
                item_id=stable_id("TYPE", module.rel_path, line, owner, kind, text),
                evidence_class=EvidenceClass.FACT,
                area="type_architecture",
                kind=kind,
                title=f"{owner}: {text}",
                subjects=[owner],
                evidence_ids=[evidence_id],
                data={"owner": owner, "annotation": text, "signal": kind},
            )
        )
    return items


def _collect_typing_signals(
    modules: Sequence[ParsedModule],
    calls: Sequence[dict[str, Any]],
    symbols: Sequence[dict[str, Any]],
    imports: Sequence[dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    used_cross_package: set[str] = set()
    for item in imports:
        data = item["data"]
        if data["source_package"] == data["target_package"] or not data["symbol"]:
            continue
        used_cross_package.add(f"{data['target_module']}.{data['symbol']}")

    for module in modules:
        for node in ast.walk(module.tree):
            if isinstance(node, ast.AnnAssign):
                owner = _annotation(node.target) or module.module
                items.extend(
                    _annotation_signals(
                        module, node, node.annotation, owner=owner, evidence=evidence
                    )
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner = f"{module.module}.{node.name}"
                for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
                    items.extend(
                        _annotation_signals(
                            module,
                            argument,
                            argument.annotation,
                            owner=f"{owner}:{argument.arg}",
                            evidence=evidence,
                        )
                    )
                items.extend(
                    _annotation_signals(
                        module, node, node.returns, owner=f"{owner}:return", evidence=evidence
                    )
                )
        comments = tokenize.generate_tokens(io.StringIO(module.source).readline)
        for token in comments:
            if token.type != tokenize.COMMENT or "type: ignore" not in token.string:
                continue
            line_number, column = token.start
            fake = ast.Pass(
                lineno=line_number,
                col_offset=column,
                end_lineno=token.end[0],
                end_col_offset=token.end[1],
            )
            evidence_id = _add_evidence(evidence, module, fake)
            items.append(
                classified(
                    item_id=stable_id("TYPE", module.rel_path, line_number, "type-ignore"),
                    evidence_class=EvidenceClass.FACT,
                    area="type_architecture",
                    kind="type_ignore",
                    title=f"{module.rel_path}:{line_number} uses type: ignore",
                    subjects=[module.module],
                    evidence_ids=[evidence_id],
                    data={"owner": module.module, "signal": "type_ignore"},
                )
            )

    dynamic_targets = {
        "typing.cast": "cast_call",
        "typing_extensions.cast": "cast_call",
        "builtins.getattr": "getattr_call",
        "builtins.hasattr": "hasattr_call",
        "builtins.eval": "eval_call",
        "builtins.exec": "exec_call",
        "builtins.__import__": "dynamic_import",
        "importlib.import_module": "dynamic_import",
    }
    evidence_by_id = evidence
    for call in calls:
        expression = call["data"]["expression"]
        kind = next(
            (
                dynamic_targets[target]
                for target in call["data"]["targets"]
                if target in dynamic_targets
            ),
            None,
        )
        if not kind:
            continue
        items.append(
            classified(
                item_id=stable_id("TYPE", call["id"], kind),
                evidence_class=EvidenceClass.FACT,
                area="type_architecture",
                kind=kind,
                title=f"{call['data']['source_scope']} uses {expression}",
                subjects=[call["data"]["source_scope"]],
                evidence_ids=[value for value in call["evidence_ids"] if value in evidence_by_id],
                fact_ids=[call["id"]],
                data={
                    "owner": call["data"]["source_scope"],
                    "signal": kind,
                    "expression": expression,
                },
            )
        )

    symbol_by_name = {item["data"]["qualified_name"]: item for item in symbols}
    for used in sorted(used_cross_package):
        used_symbol = symbol_by_name.get(used)
        if not used_symbol or used_symbol["data"].get("symbol_category") not in {
            "function",
            "method",
        }:
            continue
        signature = used_symbol["data"]
        missing = [
            parameter["name"]
            for parameter in signature.get("parameters", [])
            if parameter["annotation"] is None
        ]
        if signature.get("returns") is None:
            missing.append("return")
        if not missing:
            continue
        items.append(
            classified(
                item_id=stable_id("TYPE", used, "missing-boundary-annotation", *missing),
                evidence_class=EvidenceClass.FACT,
                area="type_architecture",
                kind="missing_cross_package_annotation",
                title=f"{used} has unannotated cross-package boundary positions",
                subjects=[used],
                evidence_ids=used_symbol["evidence_ids"],
                fact_ids=[used_symbol["id"]],
                data={
                    "owner": used,
                    "signal": "missing_cross_package_annotation",
                    "positions": sorted(missing),
                },
            )
        )
    return sorted(items, key=lambda item: item["id"])


def _context_simple_name(annotation: str | None, context_names: dict[str, str]) -> str | None:
    if not annotation:
        return None
    normalized = annotation.replace('"', "").replace("'", "")
    for simple, qualified in context_names.items():
        if simple in normalized:
            return qualified
    return None


def _attribute_path(node: ast.Attribute) -> tuple[str, list[str]] | None:
    attributes: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        attributes.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    return current.id, list(reversed(attributes))


def _function_class_owners(tree: ast.Module, module_name: str) -> dict[int, str]:
    owners: dict[int, str] = {}

    class OwnerVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
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

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self._visit_function(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            self._visit_function(node)

    OwnerVisitor().visit(tree)
    return owners


def _collect_contexts(
    modules: Sequence[ParsedModule],
    symbols: Sequence[dict[str, Any]],
    symbol_nodes: dict[str, ast.AST],
    symbol_owners: dict[str, ParsedModule],
    imports: Sequence[dict[str, Any]],
    calls: Sequence[dict[str, Any]],
    declared_roots: Sequence[str],
    evidence: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    class_symbols = [item for item in symbols if item["kind"] == "class"]
    roots = set(declared_roots)
    for item in class_symbols:
        qualified = item["data"]["qualified_name"]
        if item["data"]["name"].endswith(("Context", "State")):
            roots.add(qualified)
    context_names = {name.rsplit(".", 1)[-1]: name for name in sorted(roots)}
    observations: dict[str, dict[str, list[dict[str, Any]]]] = {
        root: {"reads": [], "writes": [], "passes": [], "constructed_by": []} for root in roots
    }

    call_evidence = {call["id"]: call["evidence_ids"] for call in calls}
    for call in calls:
        for target in call["data"]["targets"]:
            if target in roots:
                observations[target]["constructed_by"].append(
                    {
                        "source": call["data"]["source_scope"],
                        "call_id": call["id"],
                        "evidence_ids": call_evidence[call["id"]],
                    }
                )

    for module in modules:
        class_owners = _function_class_owners(module.tree, module.module)
        functions = [
            node
            for node in ast.walk(module.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for function in functions:
            bindings: dict[str, str] = {}
            class_owner = class_owners.get(id(function))
            if class_owner in roots and function.args.args:
                bindings[function.args.args[0].arg] = class_owner
            for argument in [
                *function.args.posonlyargs,
                *function.args.args,
                *function.args.kwonlyargs,
            ]:
                argument_context = _context_simple_name(
                    _annotation(argument.annotation), context_names
                )
                if argument_context:
                    bindings[argument.arg] = argument_context
            scope = (
                f"{class_owner}.{function.name}"
                if class_owner
                else f"{module.module}.{function.name}"
            )
            parents = {
                id(child): parent
                for parent in ast.walk(function)
                for child in ast.iter_child_nodes(parent)
            }
            for node in ast.walk(function):
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    value = node.value
                    assigned_context: str | None = None
                    if isinstance(value, ast.Call):
                        called = _annotation(value.func)
                        assigned_context = _context_simple_name(called, context_names)
                    if isinstance(node, ast.AnnAssign):
                        assigned_context = assigned_context or _context_simple_name(
                            _annotation(node.annotation), context_names
                        )
                    if isinstance(value, ast.Name):
                        assigned_context = assigned_context or bindings.get(value.id)
                    if assigned_context:
                        for target in targets:
                            if isinstance(target, ast.Name):
                                bindings[target.id] = assigned_context
                if isinstance(node, ast.Attribute):
                    parent = parents.get(id(node))
                    if isinstance(parent, ast.Attribute) and parent.value is node:
                        continue
                    rooted = _attribute_path(node)
                    if rooted is None or rooted[0] not in bindings:
                        continue
                    binding, path = rooted
                    bound_context = bindings[binding]
                    access = "write" if isinstance(node.ctx, (ast.Store, ast.Del)) else "read"
                    field_path = path
                    if (
                        isinstance(parent, ast.Call)
                        and parent.func is node
                        and path[-1] in _MUTATING_METHODS
                        and len(path) > 1
                    ):
                        access = "mutation"
                        field_path = path[:-1]
                    kind = "writes" if access in {"write", "mutation"} else "reads"
                    rendered_path = ".".join(field_path)
                    evidence_node = (
                        parent if access == "mutation" and isinstance(parent, ast.Call) else node
                    )
                    evidence_id = _add_evidence(evidence, module, evidence_node)
                    observations[bound_context][kind].append(
                        {
                            "source": scope,
                            "field": field_path[0],
                            "path": rendered_path,
                            "access": access,
                            "evidence_ids": [evidence_id],
                        }
                    )
                if isinstance(node, ast.Call):
                    for call_argument in [
                        *node.args,
                        *(keyword.value for keyword in node.keywords),
                    ]:
                        if isinstance(call_argument, ast.Name) and call_argument.id in bindings:
                            passed_context = bindings[call_argument.id]
                            evidence_id = _add_evidence(evidence, module, node)
                            observations[passed_context]["passes"].append(
                                {
                                    "source": scope,
                                    "target": _annotation(node.func) or "<dynamic>",
                                    "evidence_ids": [evidence_id],
                                }
                            )

    result: list[dict[str, Any]] = []
    all_detail_records: list[dict[str, Any]] = []
    symbol_by_qname = {item["data"]["qualified_name"]: item for item in symbols}
    context_class_labels = {
        "declared_root": "DECLARED ROOT",
        "runtime_subscope": "RUNTIME SUB-SCOPE",
        "type_protocol_contract": "TYPE / PROTOCOL CONTRACT",
        "local_domain_state_candidate": "LOCAL / DOMAIN STATE CANDIDATE",
        "unknown_context_like_type": "UNKNOWN CONTEXT-LIKE TYPE",
    }
    for root in sorted(roots):
        symbol = symbol_by_qname.get(root)
        context_node = symbol_nodes.get(root)
        owner = symbol_owners.get(root)
        if root in declared_roots:
            context_class = "declared_root"
        elif symbol and symbol["data"].get("class_kind") == "protocol":
            context_class = "type_protocol_contract"
        else:
            context_class = "local_domain_state_candidate"
        fields: dict[str, dict[str, Any]] = {}
        methods: list[str] = []
        if isinstance(context_node, ast.ClassDef) and owner is not None:
            frozen = bool(symbol and symbol["data"].get("frozen_object"))
            properties: dict[str, bool] = {}
            assignments_after_init: set[str] = set()
            mutations: set[str] = set()
            for child in context_node.body:
                if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                    annotation = _annotation(child.annotation)
                    final_binding = bool(
                        annotation
                        and (
                            annotation in {"Final", "typing.Final"}
                            or annotation.startswith(("Final[", "typing.Final["))
                        )
                    )
                    referent = (
                        "mutable_container"
                        if annotation
                        and any(
                            token in annotation
                            for token in ("list[", "dict[", "set[", "List[", "Dict[", "Set[")
                        )
                        else "UNKNOWN"
                    )
                    fields[child.target.id] = {
                        "name": child.target.id,
                        "annotation": annotation,
                        "binding": "non_reassignable" if final_binding else "UNKNOWN",
                        "referent_mutability": referent,
                        "mutability": "object_immutable" if frozen else "UNKNOWN",
                        "evidence_ids": [_add_evidence(evidence, owner, child)],
                    }
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(f"{root}.{child.name}")
                    decorator_names = _decorator_names(child)
                    if "property" in decorator_names:
                        properties[child.name] = False
                    for decorator in decorator_names:
                        if decorator.endswith(".setter"):
                            properties[decorator.rsplit(".", 1)[0]] = True
                    for descendant in ast.walk(child):
                        if (
                            isinstance(descendant, ast.Attribute)
                            and isinstance(descendant.value, ast.Name)
                            and descendant.value.id == "self"
                        ):
                            field_data = fields.setdefault(
                                descendant.attr,
                                {
                                    "name": descendant.attr,
                                    "annotation": None,
                                    "binding": "UNKNOWN",
                                    "referent_mutability": "UNKNOWN",
                                    "mutability": "object_immutable" if frozen else "UNKNOWN",
                                    "evidence_ids": [],
                                },
                            )
                            if not field_data["evidence_ids"]:
                                field_data["evidence_ids"] = [
                                    _add_evidence(evidence, owner, descendant)
                                ]
                            parent = next(
                                (
                                    candidate
                                    for candidate in ast.walk(child)
                                    if isinstance(candidate, ast.AnnAssign)
                                    and candidate.target is descendant
                                ),
                                None,
                            )
                            if isinstance(parent, ast.AnnAssign):
                                annotation = _annotation(parent.annotation)
                                field_data["annotation"] = annotation
                                field_data["binding"] = (
                                    "non_reassignable"
                                    if annotation
                                    and (
                                        annotation in {"Final", "typing.Final"}
                                        or annotation.startswith(("Final[", "typing.Final["))
                                    )
                                    else field_data["binding"]
                                )
                                field_data["referent_mutability"] = (
                                    "mutable_container"
                                    if annotation
                                    and any(
                                        token in annotation
                                        for token in (
                                            "list[",
                                            "dict[",
                                            "set[",
                                            "List[",
                                            "Dict[",
                                            "Set[",
                                        )
                                    )
                                    else field_data["referent_mutability"]
                                )
                                field_data["evidence_ids"] = [
                                    _add_evidence(evidence, owner, parent)
                                ]
                            if isinstance(descendant.ctx, ast.Store) and child.name != "__init__":
                                assignments_after_init.add(descendant.attr)
                        if isinstance(descendant, ast.Call) and isinstance(
                            descendant.func, ast.Attribute
                        ):
                            receiver = descendant.func.value
                            if (
                                isinstance(receiver, ast.Attribute)
                                and isinstance(receiver.value, ast.Name)
                                and receiver.value.id == "self"
                                and descendant.func.attr in _MUTATING_METHODS
                            ):
                                mutations.add(receiver.attr)
            for name, has_setter in properties.items():
                field_data = fields.setdefault(
                    name,
                    {
                        "name": name,
                        "annotation": None,
                        "binding": "UNKNOWN",
                        "referent_mutability": "UNKNOWN",
                        "mutability": "UNKNOWN",
                        "evidence_ids": [],
                    },
                )
                field_data["property_assignment"] = "available" if has_setter else "unavailable"
                if not has_setter and field_data["referent_mutability"] == "UNKNOWN":
                    field_data["referent_mutability"] = "UNKNOWN"
            for name in assignments_after_init | mutations:
                fields[name]["mutability"] = "mutable"

        detail_records: list[dict[str, Any]] = []
        detail_ids: dict[str, list[str]] = {
            "fields": [],
            "reads": [],
            "writes": [],
            "passes": [],
            "constructed_by": [],
            "dependencies": [],
        }
        for field_data in sorted(fields.values(), key=lambda value: value["name"]):
            item = classified(
                item_id=stable_id("CONTEXT-FIELD", root, field_data["name"]),
                evidence_class=EvidenceClass.FACT,
                area="contexts_state",
                kind="context_field",
                title=f"{root}.{field_data['name']}",
                subjects=[root, field_data["name"]],
                evidence_ids=field_data["evidence_ids"],
                data={"context": root, **field_data},
            )
            detail_records.append(item)
            detail_ids["fields"].append(item["id"])
        access_kinds = {
            "reads": "context_read",
            "writes": "context_write",
            "passes": "context_pass",
            "constructed_by": "context_construction",
        }
        for category, kind in access_kinds.items():
            for entry in observations[root][category]:
                call_id = entry.get("call_id")
                item = classified(
                    item_id=stable_id(
                        "CONTEXT-ACCESS",
                        root,
                        category,
                        entry.get("source"),
                        entry.get("field"),
                        entry.get("path"),
                        entry.get("target"),
                        *(entry.get("evidence_ids") or []),
                    ),
                    evidence_class=EvidenceClass.FACT,
                    area="contexts_state",
                    kind=kind,
                    title=(
                        f"{entry.get('source')} {category.replace('_', ' ')} "
                        f"{entry.get('path') or entry.get('target') or root}"
                    ),
                    subjects=[root, entry.get("source", ""), entry.get("target", "")],
                    evidence_ids=entry.get("evidence_ids", []),
                    fact_ids=[call_id] if call_id else [],
                    data={"context": root, "category": category, **entry},
                )
                detail_records.append(item)
                detail_ids[category].append(item["id"])
        dependencies = sorted(
            {
                item["data"]["target_module"]
                for item in imports
                if owner is not None
                and item["data"]["source_module"] == owner.module
                and item["data"]["target_module"] != owner.module
            }
        )
        for dependency in dependencies:
            import_facts = [
                item["id"]
                for item in imports
                if owner is not None
                and item["data"]["source_module"] == owner.module
                and item["data"]["target_module"] == dependency
            ]
            item = classified(
                item_id=stable_id("CONTEXT-DEP", root, dependency),
                evidence_class=EvidenceClass.FACT,
                area="contexts_state",
                kind="context_dependency",
                title=f"{root} depends on {dependency}",
                subjects=[root, dependency],
                fact_ids=import_facts,
                data={"context": root, "target_module": dependency},
            )
            detail_records.append(item)
            detail_ids["dependencies"].append(item["id"])

        detail_records = sorted(
            {item["id"]: item for item in detail_records}.values(), key=lambda item: item["id"]
        )
        detail_ids = {key: sorted(set(value)) for key, value in detail_ids.items()}
        evidence_ids = symbol["evidence_ids"] if symbol else []
        all_detail_records.extend(detail_records)
        result.append(
            classified(
                item_id=stable_id("CONTEXT", root),
                evidence_class=EvidenceClass.FACT if symbol else EvidenceClass.UNKNOWN,
                area="contexts_state",
                kind="context_topology" if symbol else "declared_context_not_observed",
                title=root,
                subjects=[root],
                evidence_ids=evidence_ids,
                fact_ids=([symbol["id"]] if symbol else [])
                + [item["id"] for item in detail_records],
                data={
                    "qualified_name": root,
                    "declared_root": root in declared_roots,
                    "context_class": context_class,
                    "context_class_label": context_class_labels[context_class],
                    "methods": sorted(methods),
                    **{key: sorted(value) for key, value in detail_ids.items()},
                },
            )
        )
    return sorted(result, key=lambda item: item["id"]), sorted(
        all_detail_records, key=lambda item: item["id"]
    )


def _aggregate_edges(
    imports: Sequence[dict[str, Any]], *, level: str, internal_modules: set[str], namespace: str
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    type_checking_counts: Counter[tuple[str, str]] = Counter()
    for item in imports:
        data = item["data"]
        if level == "module":
            source = data["source_module"]
            target = data["target_module"]
            if target not in internal_modules or source == target:
                continue
        else:
            source = data["source_package"]
            target = data["target_package"]
            if not in_scope(target, namespace) or source == target:
                continue
        buckets[(source, target)].append(item["id"])
        if data["under_type_checking"]:
            type_checking_counts[(source, target)] += 1
    graph_edges = sorted(buckets)
    ranks = condensation_ranks({value for edge in graph_edges for value in edge}, graph_edges)
    edge_set = set(graph_edges)
    records = [
        classified(
            item_id=stable_id("EDGE", level, source, target),
            evidence_class=EvidenceClass.FACT,
            area=f"{level}_topology",
            kind=f"{level}_dependency",
            title=f"{source} → {target}",
            subjects=[source, target],
            fact_ids=sorted(buckets[(source, target)]),
            data={
                "level": level,
                "source": source,
                "target": target,
                "count": len(buckets[(source, target)]),
                "type_checking_count": type_checking_counts[(source, target)],
                "runtime_count": len(buckets[(source, target)])
                - type_checking_counts[(source, target)],
                "source_rank": ranks.get(source, 0),
                "target_rank": ranks.get(target, 0),
                "bidirectional": (target, source) in edge_set,
            },
        )
        for source, target in graph_edges
    ]
    return records, graph_edges


def _cycle_records(
    *,
    level: str,
    nodes: Iterable[str],
    edges: Sequence[tuple[str, str]],
    edge_records: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    edge_by_pair = {(item["data"]["source"], item["data"]["target"]): item for item in edge_records}
    records: list[dict[str, Any]] = []
    for component in strongly_connected_components(nodes, edges):
        self_loop = len(component) == 1 and (component[0], component[0]) in edge_by_pair
        if len(component) <= 1 and not self_loop:
            continue
        member_set = set(component)
        internal_edges = [
            edge_by_pair[(source, target)]
            for source, target in edges
            if source in member_set and target in member_set and (source, target) in edge_by_pair
        ]
        records.append(
            classified(
                item_id=stable_id("SCC", level, *component),
                evidence_class=EvidenceClass.FACT,
                area="cycles",
                kind=f"{level}_scc",
                title=f"{level.capitalize()} cycle with {len(component)} members",
                subjects=component,
                fact_ids=[item["id"] for item in internal_edges],
                data={
                    "level": level,
                    "members": component,
                    "internal_edges": [item["id"] for item in internal_edges],
                },
            )
        )
    return sorted(records, key=lambda item: item["id"])


def _declared_path_observations(
    paths: Sequence[ContractPath], package_edges: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    edges = {(item["data"]["source"], item["data"]["target"]): item for item in package_edges}
    records: list[dict[str, Any]] = []
    for declared_path in paths:
        steps = declared_path.steps
        for index, (source, target) in enumerate(zip(steps, steps[1:], strict=False)):
            edge = edges.get((source, target))
            if edge is None:
                records.append(
                    classified(
                        item_id=stable_id("UNKNOWN-PATH", declared_path.id, index, source, target),
                        evidence_class=EvidenceClass.UNKNOWN,
                        area="read_write_paths",
                        kind="path_segment_not_statically_observed",
                        title=f"{source} → {target} lacks direct static import evidence",
                        subjects=[source, target],
                        rule_ids=[declared_path.id],
                        data={
                            "path_id": declared_path.id,
                            "source": source,
                            "target": target,
                            "status": "UNKNOWN",
                            "reason": (
                                "Missing static proof does not prove that the runtime path "
                                "is absent"
                            ),
                        },
                    )
                )
                continue
            records.append(
                classified(
                    item_id=stable_id("PATH-OBS", declared_path.id, index, edge["id"]),
                    evidence_class=EvidenceClass.FACT,
                    area="read_write_paths",
                    kind="observed_path_segment",
                    title=f"{source} → {target} is statically observed",
                    subjects=[source, target],
                    rule_ids=[declared_path.id],
                    fact_ids=[edge["id"]],
                    data={
                        "path_id": declared_path.id,
                        "source": source,
                        "target": target,
                        "status": "observed",
                        "direct_import_count": edge["data"]["count"],
                    },
                )
            )
    return sorted(records, key=lambda item: item["id"])


def _component_scope_observations(
    *,
    components: Sequence[ContractComponent],
    modules: Sequence[dict[str, Any]],
    module_edges: Sequence[dict[str, Any]],
    coverage_failures: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate observed modules under accepted component prefixes.

    A prefix owns only its exact module and dot-delimited descendants. Coverage
    failures suppress absence-based assignment findings because the missing
    source may contain evidence that changes the result.
    """
    module_by_name = {item["data"]["qualified_name"]: item for item in modules}
    assigned_modules: set[str] = set()
    observations: list[dict[str, Any]] = []
    coverage_complete = not coverage_failures

    for component in sorted(components, key=lambda item: item.id):
        scopes = sorted(component.packages)
        matched_names = sorted(
            name for name in module_by_name if any(in_scope(name, scope) for scope in scopes)
        )
        assigned_modules.update(matched_names)
        matched_set = set(matched_names)
        outgoing_edges = sorted(
            (
                edge
                for edge in module_edges
                if edge["data"]["source"] in matched_set
                and edge["data"]["target"] not in matched_set
            ),
            key=lambda item: item["id"],
        )
        outgoing_modules = sorted({edge["data"]["target"] for edge in outgoing_edges})
        outgoing_scopes = sorted(
            {scope for name in outgoing_modules if (scope := _top_level_scope(name)) is not None}
        )
        module_facts = [module_by_name[name] for name in matched_names]
        observations.append(
            classified(
                item_id=stable_id("SCOPE", "declared_component", component.id),
                evidence_class=EvidenceClass.FACT,
                area="components",
                kind="declared_component_scope_observation",
                title=f"Observed source scope for {component.label}",
                subjects=scopes,
                evidence_ids=[
                    evidence_id for item in module_facts for evidence_id in item["evidence_ids"]
                ],
                rule_ids=[component.id],
                fact_ids=[
                    *[item["id"] for item in module_facts],
                    *[item["id"] for item in outgoing_edges],
                ],
                data={
                    "component_id": component.id,
                    "scopes": scopes,
                    "scope_module_counts": [
                        {
                            "scope": scope,
                            "observed_module_count": sum(
                                1 for name in matched_names if in_scope(name, scope)
                            ),
                        }
                        for scope in scopes
                    ],
                    "coverage_complete": coverage_complete,
                    "module_count": len(matched_names) if coverage_complete else None,
                    "observed_module_count": len(matched_names),
                    "modules": matched_names,
                    "files": sorted(module_by_name[name]["data"]["file"] for name in matched_names),
                    "fan_out": len(outgoing_scopes) if coverage_complete else None,
                    "outgoing_scopes": outgoing_scopes,
                    "outgoing_modules": outgoing_modules,
                },
            )
        )

    if coverage_failures:
        observations.append(
            classified(
                item_id="UNKNOWN-COMPONENT-SCOPE-COVERAGE",
                evidence_class=EvidenceClass.UNKNOWN,
                area="components",
                kind="component_scope_assignment_incomplete",
                title="Component scope assignment cannot be completed safely",
                subjects=sorted(
                    subject
                    for failure in coverage_failures
                    for subject in failure.get("subjects", [])
                ),
                data={
                    "reason": "Source coverage failed; unassigned-scope conclusions are suppressed",
                    "coverage_failure_ids": sorted(failure["id"] for failure in coverage_failures),
                },
            )
        )
        return sorted(observations, key=lambda item: item["id"])

    unassigned_by_scope: dict[str, list[str]] = defaultdict(list)
    for name in sorted(module_by_name):
        scope = _top_level_scope(name)
        if scope is not None and name not in assigned_modules:
            unassigned_by_scope[scope].append(name)

    for scope, names in sorted(unassigned_by_scope.items()):
        module_facts = [module_by_name[name] for name in names]
        scope_modules = sorted(name for name in module_by_name if in_scope(name, scope))
        observations.append(
            classified(
                item_id=stable_id("UNKNOWN-SCOPE", scope),
                evidence_class=EvidenceClass.UNKNOWN,
                area="components",
                kind="unassigned_component_scope",
                title=f"Accepted component ownership is undecided for {scope}",
                subjects=[scope, *names],
                evidence_ids=[
                    evidence_id for item in module_facts for evidence_id in item["evidence_ids"]
                ],
                fact_ids=[item["id"] for item in module_facts],
                data={
                    "scope": scope,
                    "module_count": len(names),
                    "modules": names,
                    "files": sorted(module_by_name[name]["data"]["file"] for name in names),
                    "partially_assigned": any(name in assigned_modules for name in scope_modules),
                    "reason": "No accepted component declaration covers these observed modules",
                },
            )
        )
    return sorted(observations, key=lambda item: item["id"])


def scan_repository(
    root: Path,
    contract: ArchitectureContract,
    *,
    source_paths: Sequence[Path] | None = None,
    roots: tuple[str, ...],
    namespace: str,
) -> ScanResult:
    """Scan production Python and return the deterministic observed model sections."""
    paths = (
        tuple(source_paths) if source_paths is not None else iter_source_paths(root, roots=roots)
    )
    paths = tuple(sorted(paths, key=lambda path: path.relative_to(root).as_posix()))
    parsed: list[ParsedModule] = []
    failures: list[dict[str, Any]] = []
    evidence: dict[str, dict[str, Any]] = {}
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
            module_name = _module_for(path, root=root, namespace=namespace)
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
        parsed.append(
            ParsedModule(
                path=path,
                rel_path=rel,
                module=module_name,
                package=_package_for(module_name),
                source=source,
                source_bytes=raw,
                lines=source.splitlines(),
                tree=tree,
            )
        )

    module_names = {module.module for module in parsed}
    rule_failures = []
    for rule in contract.rules:
        scopes = rule_scopes(rule)
        matches = {
            side: sum(
                any(in_scope(module, scope) for scope in side_scopes) for module in module_names
            )
            for side, side_scopes in scopes.items()
        }
        missing = [side for side, count in matches.items() if count == 0]
        if missing:
            rule_failures.append(
                classified(
                    item_id=stable_id("UNKNOWN-RULE-SUBJECTS", rule.id),
                    evidence_class=EvidenceClass.UNKNOWN,
                    area="analysis_coverage",
                    kind="rule-without-subjects",
                    title=f"{rule.id}: no scanned modules for {', '.join(missing)}",
                    subjects=[scope for side in missing for scope in scopes[side]],
                    rule_ids=[rule.id],
                    data={
                        "missing": missing,
                        **{f"{side}_matches": count for side, count in matches.items()},
                    },
                )
            )
    module_evidence = {
        module.module: _add_evidence(evidence, module, module.tree) for module in parsed
    }
    imports: list[dict[str, Any]] = []
    for module in parsed:
        module.all_exports = _literal_all_exports(module.tree)
        collector = _ImportCollector(module, module_names, evidence, namespace=namespace)
        collector.visit(module.tree)
        imports.extend(collector.items)
    imports.sort(key=lambda item: item["id"])

    reexports: dict[str, str] = {}
    exports_by_module = {module.module: module.all_exports for module in parsed}
    for item in imports:
        data = item["data"]
        if not data["reexport"] or not data["symbol"]:
            continue
        reexports[f"{data['source_module']}.{data['binding']}"] = (
            f"{data['target_module']}.{data['symbol']}"
        )
    for item in imports:
        data = item["data"]
        if not data["symbol"]:
            data["reexport_chain"] = []
            data["origin_definition"] = None
            data["symbol_visibility"] = None
            data["declared_in_all"] = False
            continue
        current = f"{data['target_module']}.{data['symbol']}"
        chain = [current]
        seen = {current}
        while current in reexports and reexports[current] not in seen:
            current = reexports[current]
            seen.add(current)
            chain.append(current)
        data["reexport_chain"] = chain
        data["origin_definition"] = chain[-1]
        data["symbol_visibility"] = "private" if data["symbol"].startswith("_") else "public_name"
        data["declared_in_all"] = data["binding"] in exports_by_module.get(
            data["source_module"], set()
        )

    symbols, symbol_nodes, symbol_owners = _collect_symbols(parsed, evidence)
    symbol_names = {item["data"]["qualified_name"] for item in symbols}
    by_tail: dict[str, list[str]] = defaultdict(list)
    for name in sorted(symbol_names):
        by_tail[name.rsplit(".", 1)[-1]].append(name)

    calls: list[dict[str, Any]] = []
    symbol_evidence = {item["data"]["qualified_name"]: item["evidence_ids"] for item in symbols}
    for module in parsed:
        call_collector = _CallCollector(module, symbol_names, by_tail, symbol_evidence, evidence)
        call_collector.visit(module.tree)
        calls.extend(call_collector.items)
    calls.sort(key=lambda item: item["id"])

    typing_signals = _collect_typing_signals(parsed, calls, symbols, imports, evidence)
    declarations = contract.declarations or ContractDeclarations()
    contexts, context_evidence = _collect_contexts(
        parsed,
        symbols,
        symbol_nodes,
        symbol_owners,
        imports,
        calls,
        declarations.context_roots,
        evidence,
    )

    module_edges, module_edge_pairs = _aggregate_edges(
        imports, level="module", internal_modules=module_names, namespace=namespace
    )
    package_edges, package_edge_pairs = _aggregate_edges(
        imports, level="package", internal_modules=module_names, namespace=namespace
    )
    dependency_edges = sorted([*package_edges, *module_edges], key=lambda item: item["id"])
    path_observations = _declared_path_observations(declarations.paths, package_edges)

    packages = sorted({module.package for module in parsed})
    package_fan_in = Counter(target for source, target in package_edge_pairs)
    package_fan_out = Counter(source for source, target in package_edge_pairs)
    package_records = [
        classified(
            item_id=stable_id("PKG", package),
            evidence_class=EvidenceClass.FACT,
            area="package_topology",
            kind="package",
            title=package,
            subjects=[package],
            fact_ids=sorted(
                stable_id("MOD", module.module) for module in parsed if module.package == package
            ),
            data={
                "qualified_name": package,
                "module_count": sum(1 for module in parsed if module.package == package),
                "fan_in": package_fan_in[package],
                "fan_out": package_fan_out[package],
                "rank": condensation_ranks(packages, package_edge_pairs).get(package, 0),
                "dependencies": sorted(
                    target for source, target in package_edge_pairs if source == package
                ),
            },
        )
        for package in packages
    ]

    module_fan_in = Counter(target for source, target in module_edge_pairs)
    module_fan_out = Counter(source for source, target in module_edge_pairs)
    module_ranks = condensation_ranks(module_names, module_edge_pairs)
    symbols_by_module = Counter(item["data"]["module"] for item in symbols)
    module_records = [
        classified(
            item_id=stable_id("MOD", module.module),
            evidence_class=EvidenceClass.FACT,
            area="module_topology",
            kind="module",
            title=module.module,
            subjects=[module.module, module.package],
            evidence_ids=[module_evidence[module.module]],
            data={
                "qualified_name": module.module,
                "package": module.package,
                "file": module.rel_path,
                "symbol_count": symbols_by_module[module.module],
                "fan_in": module_fan_in[module.module],
                "fan_out": module_fan_out[module.module],
                "rank": module_ranks.get(module.module, 0),
                "all_exports": sorted(module.all_exports),
            },
        )
        for module in parsed
    ]
    scope_observations = _component_scope_observations(
        components=contract.components,
        modules=module_records,
        module_edges=module_edges,
        coverage_failures=failures,
    )

    transitive_records = [
        classified(
            item_id=stable_id("PATH", "package", *path),
            evidence_class=EvidenceClass.FACT,
            area="package_topology",
            kind="transitive_package_dependency",
            title=" → ".join(path),
            subjects=path,
            fact_ids=[
                stable_id("EDGE", "package", source, target)
                for source, target in zip(path, path[1:], strict=False)
            ],
            data={"level": "package", "source": path[0], "target": path[-1], "path": path},
        )
        for path in transitive_paths(packages, package_edge_pairs)
    ]
    cycles = sorted(
        [
            *_cycle_records(
                level="package",
                nodes=packages,
                edges=package_edge_pairs,
                edge_records=package_edges,
            ),
            *_cycle_records(
                level="module",
                nodes=module_names,
                edges=module_edge_pairs,
                edge_records=module_edges,
            ),
        ],
        key=lambda item: item["id"],
    )
    violations = rule_violations(
        imports=imports,
        typing_signals=typing_signals,
        modules=module_records,
        blank_modules=frozenset(module.module for module in parsed if not module.source.strip()),
        contract=contract,
    )

    unknowns = [
        classified(
            item_id="UNKNOWN-PYTHON-DYNAMIC-CALLS",
            evidence_class=EvidenceClass.UNKNOWN,
            area="call_hierarchy",
            kind="dynamic_call_limit",
            title="Python dynamic behavior prevents a complete call graph",
            subjects=[namespace],
            data={
                "unresolved_calls": sum(
                    1 for call in calls if call["data"]["status"] == "unresolved"
                )
            },
        ),
        classified(
            item_id="UNKNOWN-CONTEXT-DATAFLOW",
            evidence_class=EvidenceClass.UNKNOWN,
            area="contexts_state",
            kind="context_alias_limit",
            title="Context read/write topology excludes unproven dynamic aliases",
            subjects=sorted(declarations.context_roots),
            data={
                "reason": (
                    "The scanner follows direct annotations, constructor bindings, "
                    "and self-field access only"
                )
            },
        ),
        *failures,
        *rule_failures,
    ]

    calls_analyzed = len(calls)
    calls_resolved = sum(1 for call in calls if call["data"]["status"] == "resolved")
    calls_partially_resolved = sum(
        1 for call in calls if call["data"]["status"] == "partially_resolved"
    )
    calls_unresolved = sum(1 for call in calls if call["data"]["status"] == "unresolved")
    coverage = {
        "status": "FAIL" if failures or rule_failures or not paths else "PASS",
        "rules": "FAIL" if rule_failures else "PASS",
        "files_discovered": len(paths),
        "files_read": read_count,
        "files_parsed": len(parsed),
        "ast_coverage_percent": round((len(parsed) / len(paths) * 100), 2) if paths else 0.0,
        "failures": [
            *sorted(
                failures,
                key=lambda item: (item["data"]["file"], item["data"]["line"], item["kind"]),
            ),
            *sorted(rule_failures, key=lambda item: item["id"]),
        ],
        "calls_analyzed": calls_analyzed,
        "calls_resolved": calls_resolved,
        "calls_partially_resolved": calls_partially_resolved,
        "calls_unresolved": calls_unresolved,
        "call_resolution_percent": round(calls_resolved / calls_analyzed * 100, 2)
        if calls_analyzed
        else 0.0,
    }

    return ScanResult(
        source_digest=digest.hexdigest(),
        coverage=coverage,
        evidence=sorted(evidence.values(), key=lambda item: item["id"]),
        scope_observations=scope_observations,
        packages=sorted(package_records, key=lambda item: item["id"]),
        modules=sorted(module_records, key=lambda item: item["id"]),
        symbols=symbols,
        imports=imports,
        dependency_edges=dependency_edges,
        transitive_paths=sorted(transitive_records, key=lambda item: item["id"]),
        path_observations=path_observations,
        cycles=cycles,
        calls=calls,
        typing_signals=typing_signals,
        contexts=contexts,
        context_evidence=context_evidence,
        violations=violations,
        unknowns=sorted(unknowns, key=lambda item: item["id"]),
    )
