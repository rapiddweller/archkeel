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
