# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Lexical reuse belongs to one exact parsed snapshot, never to binding proofs."""

import ast
import sys
from dataclasses import fields, replace

import pytest
from test_analyzer import _parsed_module

from archkeel.analyzer.python.binding_types import AliasBinding, ImportKind
from archkeel.analyzer.python.calls import collect_calls
from archkeel.analyzer.python.constructs import collect_constructs
from archkeel.analyzer.python.imports import collect_dynamic_imports, collect_imports
from archkeel.analyzer.python.references import collect_references
from archkeel.analyzer.python.resolve import build_symbol_index
from archkeel.analyzer.python.scopes import LexicalScopes


def test_index_reuse_preserves_fresh_constructor_and_instance_isolation():
    source = "def use(value): return value\n"
    first, second = _parsed_module(source), _parsed_module(source)
    shared = LexicalScopes.for_module(first)
    assert LexicalScopes.for_module(first) is shared
    assert LexicalScopes(first) is not shared
    assert LexicalScopes.for_module(second) is not shared
    uncached = replace(first)
    assert uncached._lexical_scopes is None and first == uncached
    field = next(item for item in fields(first) if item.name == "_lexical_scopes")
    assert not field.init and not field.repr and not field.compare


@pytest.mark.parametrize("change", ["source", "tree", "rel_path", "module"])
def test_index_rebuilds_for_each_fixed_input_change(change):
    module = _parsed_module("def use(): pass\n")
    previous = LexicalScopes.for_module(module)
    if change == "source":
        module.source = "def broken("
    elif change == "tree":
        module.tree = ast.parse(module.source)
    elif change == "rel_path":
        module.rel_path = "other.py"
    else:
        module.module = "other"
    current = LexicalScopes.for_module(module)
    assert current is not previous
    assert LexicalScopes.for_module(module) is current
    if change == "source":
        assert current.root.table is None


def test_invalid_compiler_source_after_reuse_cannot_authorize_receiver():
    module = _parsed_module("def use():\n value = ''.join(['x'])\n value.encode()\n")
    LexicalScopes.for_module(module)
    module.source = "def incomplete("
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "value.encode")
    assert call["status"] == "unresolved" and call["targets"] == []


def test_index_reads_current_import_aliases_without_caching_resolution():
    module = _parsed_module("from before import value\nvalue()\n")
    collect_imports([module], {module.module}, {}, namespace="sample")
    index = LexicalScopes.for_module(module)
    call = next(node for node in module.all_nodes if isinstance(node, ast.Call))
    assert index.lookup(call.func, "value").targets == ("before.value",)
    statement = module.tree.body[0]
    module.import_aliases[statement]["value"] = AliasBinding("after.value", ImportKind.SYMBOL)
    assert LexicalScopes.for_module(module) is index
    assert index.lookup(call.func, "value").targets == ("after.value",)


def test_another_ast_visitor_cannot_supply_lexical_proof():
    module = _parsed_module("value = 1\n")
    module._lexical_scopes = (
        module.tree,
        module.source,
        module.rel_path,
        module.module,
        ast.NodeVisitor(),
    )
    index = LexicalScopes.for_module(module)
    assert isinstance(index, LexicalScopes)
    assert LexicalScopes.for_module(module) is index


def test_failed_index_construction_is_not_published(monkeypatch):
    module = _parsed_module("value = 1\n")

    def fail(_self, _module):
        raise RuntimeError("construction failed")

    monkeypatch.setattr(LexicalScopes, "__init__", fail)
    with pytest.raises(RuntimeError, match="construction failed"):
        LexicalScopes.for_module(module)
    assert module._lexical_scopes is None


def test_five_collectors_share_one_index(monkeypatch):
    module = _parsed_module("import importlib\nimportlib.import_module('json')\n")
    constructions = []
    original = LexicalScopes.__init__

    def count(self, parsed):
        constructions.append(parsed)
        original(self, parsed)

    monkeypatch.setattr(LexicalScopes, "__init__", count)
    evidence = {}
    imports = collect_imports([module], {module.module}, evidence, namespace="sample")
    symbols = build_symbol_index([])
    calls = collect_calls([module], symbols, evidence)
    collect_dynamic_imports([module], calls, imports, evidence, namespace="sample")
    collect_references([module], symbols, evidence, imports=())
    collect_constructs([module], evidence, imports=imports)
    assert constructions == [module]


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP695 requires Python3.12")
def test_pep695_scope_remains_unproven_after_reuse():
    module = _parsed_module("def use[T](value: T): return value\n")
    index = LexicalScopes.for_module(module)
    value = next(
        node for node in module.all_nodes if isinstance(node, ast.Name) and node.id == "value"
    )
    assert index.lookup(value, "value").owner is None
    assert LexicalScopes.for_module(module) is index
