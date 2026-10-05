# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import ast
from unittest.mock import patch

import pytest
from test_analyzer import _parsed_module

from archkeel.analyzer.python import source
from archkeel.analyzer.python.source import (
    AliasBinding,
    stable_direct_module_bindings,
    unique_direct_module_bindings,
    unproven_member_bindings,
)


def test_unique_proof_does_not_repeat_ast_walks() -> None:
    with patch.object(ast, "iter_fields", wraps=ast.iter_fields) as visits:
        module = _parsed_module("class Api: pass\nclass Other: pass\n")
        assert unique_direct_module_bindings(module) == frozenset({"Api", "Other"})
        first_visits = visits.call_count
        assert unique_direct_module_bindings(module) == frozenset({"Api", "Other"})
        assert visits.call_count == first_visits


def test_stable_proof_does_not_repeat_namespace_scans() -> None:
    module = _parsed_module("class Api: pass\nclass Other: pass\nalias = Api\n")
    with patch.object(
        source, "exposes_dynamic_namespace", wraps=source.exposes_dynamic_namespace
    ) as visits:
        assert stable_direct_module_bindings(module) == frozenset({"Api", "Other", "alias"})
        first_visits = visits.call_count
        assert first_visits > 0
        assert stable_direct_module_bindings(module) == frozenset({"Api", "Other", "alias"})
        assert visits.call_count == first_visits


def test_alias_changes_invalidate_even_an_empty_stable_proof() -> None:
    module = _parsed_module("from builtins import exec as run\nclass C: pass\nrun('x')\n")
    original = frozenset({"C", "run"})
    assert stable_direct_module_bindings(module) == original
    module.aliases["run"] = AliasBinding("builtins.exec", "symbol", "exec")
    assert stable_direct_module_bindings(module) == frozenset()
    assert stable_direct_module_bindings(module) == frozenset()
    module.aliases["run"] = AliasBinding("safe.run", "symbol", "run")
    assert stable_direct_module_bindings(module) == original
    del module.aliases["run"]
    assert stable_direct_module_bindings(module) == original


def test_alias_kind_change_invalidates_import_origin_proof() -> None:
    module = _parsed_module(
        "import pkg as route\nfrom pkg import X as second\nroute.attr = 1\nclass C: pass\n"
    )
    assert "second" in stable_direct_module_bindings(module)
    module.aliases.update(
        route=AliasBinding("pkg", "module"), second=AliasBinding("pkg.X", "symbol", "X")
    )
    assert "second" not in stable_direct_module_bindings(module)
    module.aliases["second"] = AliasBinding("pkg.X", "module", "X")
    assert "second" in stable_direct_module_bindings(module)


def test_incoming_member_proofs_remain_live() -> None:
    module = _parsed_module("class C: pass\n")
    assert stable_direct_module_bindings(module) == frozenset({"C"})
    assert unproven_member_bindings(module) == frozenset()
    module.incoming_member_escapes.add("C")
    assert stable_direct_module_bindings(module) == frozenset({"C"})
    assert unproven_member_bindings(module) == frozenset({"C"})


def test_same_path_snapshots_have_separate_proofs() -> None:
    original = _parsed_module("class C: pass\n")
    changed = _parsed_module("class C: pass\nclass C: pass\n")
    assert original.path == changed.path
    for module, expected in (
        (original, frozenset({"C"})),
        (changed, frozenset()),
        (original, frozenset({"C"})),
    ):
        assert unique_direct_module_bindings(module) == expected
        assert stable_direct_module_bindings(module) == expected


@pytest.mark.parametrize(
    "expression", ["vars()", "vars(C)", "vars", "locals()", "locals(C)", "exec(C)", "eval(C)"]
)
def test_namespace_access_remains_unproven(expression: str) -> None:
    module = _parsed_module("class C: pass\n" + expression + "\n")
    assert stable_direct_module_bindings(module) == frozenset()
    assert stable_direct_module_bindings(module) == frozenset()


def test_absent_global_does_not_rescan_class_bodies() -> None:
    module = _parsed_module("class Service:\n class Nested:\n  staticmethod = 1\n")
    with patch.object(ast, "walk", wraps=ast.walk) as walks:
        for _ in range(3):
            assert not source.binding_may_exist_before(
                module, module.tree.body, None, "staticmethod"
            )
        assert walks.call_count == 0


def test_global_elsewhere_does_not_bind_inside_a_different_class() -> None:
    module = _parsed_module(
        "class First:\n global property\n property = None\nclass Second: pass\n"
    )
    second = module.tree.body[1]
    assert isinstance(second, ast.ClassDef)
    assert not source.binding_may_exist_before(module, second.body, None, "property")
    assert source.binding_may_exist_before(module, module.tree.body, second, "property")


def test_absent_binding_does_not_repeat_statement_scans() -> None:
    module = _parsed_module("def service(value=factory('x')): pass\n")
    with patch.object(ast, "iter_child_nodes", wraps=ast.iter_child_nodes) as visits:
        for _ in range(3):
            assert not source.binding_may_exist_before(
                module, module.tree.body, None, "staticmethod"
            )
        assert visits.call_count == 0


def test_wildcard_import_retains_arbitrary_binding_uncertainty() -> None:
    module = _parsed_module("from unknown import *\n")
    assert source.binding_may_exist_before(module, module.tree.body, None, "staticmethod")


@pytest.mark.parametrize(
    "declaration",
    [
        "del property",
        "property: object",
        "import unknown as property",
        "from unknown import value as property",
        "class property: pass",
        "def property(): pass",
        "async def property(): pass",
        "try:\n pass\nexcept Exception as property:\n pass",
        'match value:\n case {"x": property}: pass',
        "match value:\n case [*property]: pass",
        "match value:\n case {**property}: pass",
        "class First:\n global property",
        "def service(value=(property := 1)): pass",
    ],
)
def test_binding_index_preserves_every_binding_form(declaration: str) -> None:
    module = _parsed_module(declaration + "\n")
    assert source.binding_may_exist_before(module, module.tree.body, None, "property")
