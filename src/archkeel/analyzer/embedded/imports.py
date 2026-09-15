# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Import statement collection for the Python architecture scanner."""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Sequence

from archkeel.ir.model import EvidenceClass, in_scope

from .records import RawEvidence, RawRecord, classified, stable_id
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


class ImportCollector(ast.NodeVisitor):
    def __init__(
        self,
        module: ParsedModule,
        module_names: set[str],
        evidence: dict[str, RawEvidence],
        *,
        namespace: str,
    ) -> None:
        self.module = module
        self.module_names = module_names
        self.evidence = evidence
        self.namespace = namespace
        self.under_type_checking = False
        self.items: list[RawRecord] = []

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
