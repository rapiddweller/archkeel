# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Import statement collection for the Python architecture scanner."""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Sequence

from archkeel.ir.model import EvidenceClass, in_scope, stable_id

from .records import RawEvidence, RawRecord, classified
from .source import (
    AliasBinding,
    ParsedModule,
    add_evidence,
    location,
    package_for,
    unique_direct_module_bindings,
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
    unique_bindings = {module.module: unique_direct_module_bindings(module) for module in parsed}
    alias_targets: dict[str, set[str]] = {}
    uncertain_bindings: set[str] = set()
    for item in imports:
        data = item["data"]
        if not data["symbol"] or not (data["reexport"] or data.get("reexport_candidate")):
            continue
        binding = f"{data['source_module']}.{data['binding']}"
        target = f"{data['target_module']}.{data['symbol']}"
        alias_targets.setdefault(binding, set()).add(target)
        source_unique = data["source_module"] not in unique_bindings or (
            data["binding"] in unique_bindings[data["source_module"]]
        )
        target_unique = data["target_module"] not in unique_bindings or (
            data["symbol"] in unique_bindings[data["target_module"]]
        )
        if data.get("reexport_candidate") is True or not source_unique or not target_unique:
            uncertain_bindings.add(binding)
            data["reexport_candidate"] = True
            data["reexport"] = False

    def route_is_proven(binding: str) -> bool:
        current = binding
        visited: set[str] = set()
        while current in alias_targets:
            if current in visited or current in uncertain_bindings:
                return False
            targets = alias_targets[current]
            if len(targets) != 1:
                return False
            visited.add(current)
            current = next(iter(targets))
        return True

    reexports: dict[str, str] = {}
    for item in imports:
        data = item["data"]
        if not data["reexport"] or not data["symbol"]:
            continue
        binding = f"{data['source_module']}.{data['binding']}"
        if not route_is_proven(binding):
            uncertain_bindings.add(binding)
            data["reexport_candidate"] = True
            data["reexport"] = False
            continue
        reexports[binding] = f"{data['target_module']}.{data['symbol']}"
    for item in imports:
        data = item["data"]
        if not data["symbol"]:
            data["reexport_chain"] = []
            data["origin_definition"] = None
            data["symbol_visibility"] = None
            data["declared_in_all"] = False
            continue
        source_binding_unique = data["source_module"] not in unique_bindings or (
            data["binding"] in unique_bindings[data["source_module"]]
        )
        current = f"{data['target_module']}.{data['symbol']}"
        chain = [current]
        seen = {current}
        while current in reexports and reexports[current] not in seen:
            current = reexports[current]
            seen.add(current)
            chain.append(current)
        data["reexport_chain"] = chain
        data["origin_definition"] = chain[-1]
        origin_module, _, origin_name = chain[-1].rpartition(".")
        data["origin_binding_unique"] = (
            origin_module not in unique_bindings or origin_name in unique_bindings[origin_module]
        )
        if data["reexport"] and (
            not source_binding_unique
            or (data.get("ordinary_module") and not data["origin_binding_unique"])
        ):
            data["reexport_candidate"] = True
            data["reexport"] = False
        data["symbol_visibility"] = "private" if data["symbol"].startswith("_") else "public_name"
        data["declared_in_all"] = data["binding"] in exports_by_module.get(
            data["source_module"], set()
        )

    def terminal_origins(binding: str) -> frozenset[str]:
        pending = [binding]
        visited: set[str] = set()
        terminals: set[str] = set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            targets = alias_targets.get(current)
            if targets:
                pending.extend(targets - visited)
            else:
                terminals.add(current)
        return frozenset(terminals)

    return {binding: terminal_origins(binding) for binding in uncertain_bindings}


def strip_internal_reexport_facts(imports: Sequence[RawRecord]) -> None:
    """Keep proof bookkeeping out of serialized IR import records."""
    for item in imports:
        data = item["data"]
        data.pop("ordinary_module", None)
        data.pop("origin_binding_unique", None)
        data.pop("reexport_candidate", None)


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
