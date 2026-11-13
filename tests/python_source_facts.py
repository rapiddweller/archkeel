# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Unchanged Python function outputs at explicit native source-fact boundaries."""

from __future__ import annotations

import ast
from dataclasses import asdict
from pathlib import Path
from typing import Any

from archkeel.analyzer.python import source as s
from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.scopes import LexicalScopes
from archkeel.analyzer.python.typing_signals import collect_typing_signals
from archkeel.analyzer.python.state import collect_state
from archkeel.ir.facts import EvidenceClass
from archkeel.ir.facts_codec import classified, parse_record, thaw_data
from archkeel.ir.state_codec import state_data


def parsed(root: Path, rel: str) -> s.ParsedModule | None:
    namespace = Path(rel).parts[0].removesuffix(".py")
    modules = s.parse_sources([root / rel], root=root, namespace=namespace).modules
    return modules[0] if modules else None


def aliases(module: s.ParsedModule) -> list[dict[str, Any]]:
    collect_imports([module], {module.module}, {}, namespace=module.module.split(".")[0])
    return [
        {"line": node.lineno, "column": node.col_offset, "name": name,
         "target": alias.target, "kind": alias.kind.value}
        for node, names in module.import_aliases.items()
        for name, alias in names.items()
    ]


def site(node: ast.AST) -> list[Any]:
    return [type(node).__name__, *s.location(node)]


def lexical(module: s.ParsedModule, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    index = LexicalScopes.for_module(module)
    scopes = {id(scope): scope for scope in index.by_node.values()}
    scopes[id(index.root)] = index.root
    for scope in tuple(scopes.values()):
        while scope.parent is not None:
            scope = scope.parent
            scopes[id(scope)] = scope
    ordered=sorted(scopes.values(),key=lambda scope:(scope.qualified_name,s.location(scope.node)[0],s.location(scope.node)[2]))
    references={id(scope):position for position,scope in enumerate(ordered)}
    rows = [
        {"qualified_name": scope.qualified_name, "definition_id": scope.definition_id,
         "parent": references[id(scope.parent)] if scope.parent else None,
         "table": scope.table is not None, "inlined": scope.inlined,
         "local_names": sorted(scope.local_names), "blocked_names": sorted(scope.blocked_names),
         "node": site(scope.node),
         "bindings": {name: [site(n) for n in nodes] for name, nodes in scope.bindings.items()}}
        for scope in ordered
    ]
    names = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Name):
            continue
        binding = index.lookup(node, node.id)
        names.append({
            "line": node.lineno, "column": node.col_offset, "name": node.id,
            "scope": references[id(index.by_node[node])],
            "binding": {"owner": references[id(binding.owner)] if binding.owner else None,
                        "targets": list(binding.targets), "kind": binding.kind.value,
                        "uncertain": binding.uncertain},
            "receiver": index.receiver_class(binding, node.id),
        })
    by_node = []
    by_site = {}
    for node,scope in index.by_node.items():
        if not source_node(node,index.parents):
            continue
        by_node.append([site(node),references[id(scope)]])
        by_site[(type(node).__name__,*s.location(node)[::2])] = node
    queries = []
    for query in (inputs or {}).get("queries",[]):
        node=by_site[(query["kind"],query["line"],query["column"])]
        binding=index.lookup(node,query["name"])
        queries.append({**query,"binding":{"owner":references[id(binding.owner)] if binding.owner else None,
                         "targets":list(binding.targets),"kind":binding.kind.value,"uncertain":binding.uncertain},
                        "receiver":index.receiver_class(binding,query["name"])})
    return {"scopes": rows,
            "names": sorted(names, key=lambda row: (row["line"], row["column"])),
            "by_node":sorted(by_node,key=lambda row:row[0]),"queries":queries,
            "generic_header_numeric_lines": sorted(index.generic_header_numeric_lines)}


def source_node(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    parent=parents.get(node)
    kind=type(node).__name__
    if kind in {"FormattedValue","Interpolation"}:
        return False
    if kind=="Constant" and type(parent).__name__ in {"JoinedStr","TemplateStr"}:
        return False
    if kind=="JoinedStr" and type(parent).__name__ in {"FormattedValue","Interpolation"}:
        return False
    return isinstance(node,(ast.Module,ast.stmt,ast.expr,ast.excepthandler,ast.arg,ast.keyword,ast.pattern))


def query_inputs(module: s.ParsedModule) -> dict[str, Any]:
    index=LexicalScopes.for_module(module)
    queries=[]
    for node in index.by_node:
        if source_node(node,index.parents):
            line,_,column=s.location(node)
            queries.extend({"kind":type(node).__name__,"line":line,"column":column,"name":name}
                           for name in ("x","str","bytes","self","T","absent"))
    return {"file":module.rel_path,"queries":queries}


def typing_signals(module: s.ParsedModule, inputs: dict[str, Any]) -> dict[str, Any]:
    evidence = {item["id"]: item for item in inputs.get("evidence", [])}
    records = collect_typing_signals([module], inputs.get("calls", []),
                                     inputs.get("symbols", []), inputs.get("imports", []), evidence)
    return {"typing_signals": records, "evidence": [evidence[key] for key in sorted(evidence)]}


def state_inputs(module: s.ParsedModule, frozen: bool = False, protocol: bool = False) -> dict[str, Any]:
    names: dict[ast.AST, str] = {}
    nodes = {}
    for node, parent, _ in s.definition_sites(module.tree):
        name = f"{names[parent] if parent else module.module}.{node.name}"
        names[node] = name
        nodes[name] = node
    return {"file": module.rel_path,
            "symbol_sites": [{"qualified_name": name, "line": node.lineno, "column": node.col_offset}
                             for name, node in nodes.items()],
            "symbols": [classified(item_id=f"SYM-{index:016x}", evidence_class=EvidenceClass.FACT,
                                   area="repository_topology", kind="class", title=name,
                                   subjects=[name], evidence_ids=[],
                                   data={"qualified_name": name, "frozen_object": frozen,
                                         "class_kind": "protocol" if protocol else "class"})
                        for index, name in enumerate(nodes)]}


def state(module: s.ParsedModule, inputs: dict[str, Any]) -> dict[str, Any]:
    by_location = {(node.lineno, node.col_offset): node for node in ast.walk(module.tree)
                   if isinstance(node, ast.stmt)}
    nodes = {site["qualified_name"]: by_location[(site["line"], site["column"])]
             for site in inputs.get("symbol_sites", [])}
    facts, evidence = collect_state([module], [parse_record(s) for s in inputs.get("symbols", [])],
                                    nodes, {node: module for node in nodes.values()})
    return {"state": thaw_data(state_data(facts)), "evidence": [asdict(item) for item in evidence]}
