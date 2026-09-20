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
from .source import AliasBinding, ParsedModule, add_evidence, location, package_for


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
        self.under_type_checking = False
        self.items: list[RawRecord] = []

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
                    "reexport": self.module.path.name == "__init__.py",
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
        collector = ImportCollector(
            module, module_names, evidence, package_bindings, namespace=namespace
        )
        collector.visit(module.tree)
        imports.extend(collector.items)
    imports.sort(key=lambda item: item["id"])
    return imports


def resolve_reexports(imports: Sequence[RawRecord], exports_by_module: dict[str, set[str]]) -> None:
    """Follow re-export chains in place so each import records its origin definition."""
    reexports: dict[str, str] = {}
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
