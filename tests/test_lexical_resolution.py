# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A lexical name must not borrow an unrelated module binding."""

import ast
import symtable
import sys
from pathlib import Path

import pytest
from test_analyzer import _observe, _parsed_module

from archkeel.analyzer.python.binding_types import BindingKind
from archkeel.analyzer.python.calls import collect_calls
from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.references import collect_references
from archkeel.analyzer.python.resolve import build_symbol_index
from archkeel.analyzer.python.scopes import LexicalScopes
from archkeel.analyzer.python.symbols import collect_symbols
from archkeel.ir.references import unreferenced_symbols


@pytest.mark.parametrize(
    "star_import,expected",
    [
        ("", BindingKind.UNBOUND),
        ("from other import *\n", BindingKind.UNKNOWN),
        ("if flag:\n from other import *\n", BindingKind.UNKNOWN),
    ],
)
def test_unbound_lookup_uses_star_binding_index(star_import, expected):
    module = _parsed_module(
        "".join(f"name_{index} = {index}\n" for index in range(100))
        + "import other as alias\ndel name_0\n(value := 1)\n"
        + star_import
        + "missing()\n"
    )
    scopes = LexicalScopes(module)
    [site] = [node for node in module.all_nodes if isinstance(node, ast.Call)]
    visited_sites = 0
    star_sites = 0

    class CountedBindings(dict):
        def get(self, key, default=None):
            nonlocal star_sites
            sites = super().get(key, default)
            if key == "*":
                star_sites += len(sites)
            return sites

        def values(self):
            nonlocal visited_sites
            for sites in super().values():
                visited_sites += len(sites)
                yield sites

    scopes.root.bindings = CountedBindings(scopes.root.bindings)
    for _ in range(50):
        assert scopes.lookup(site.func, "missing").kind is expected
    assert visited_sites == 0
    assert star_sites == (50 if star_import else 0)


def _facts(source):
    module = _parsed_module(source, module="sample.core")
    evidence = {}
    imports = collect_imports([module], {module.module}, evidence, namespace="sample")
    symbols, _, _ = collect_symbols([module], evidence)
    index = build_symbol_index(symbols)
    return (
        module,
        imports,
        collect_calls([module], index, evidence),
        collect_references([module], index, evidence),
    )


@pytest.mark.parametrize(
    "body",
    [
        "def use(Service): Service(); return Service\n",
        "def use():\n Service(); Service = value; return Service\n",
        "def use():\n Service = value; Service(); return Service\n",
        "def use(*Service): Service(); return Service\n",
        "def use(**Service): Service(); return Service\n",
        "def use():\n for Service in values: Service()\n return Service\n",
        "def use():\n with resource as Service: Service()\n return Service\n",
        "def use():\n try: pass\n except Exception as Service: Service()\n return Service\n",
        "def use():\n match value:\n  case Service: Service()\n return Service\n",
        "def use():\n def nested(Service): Service(); return Service\n return nested\n",
        "def use(Service):\n def nested(): Service(); return Service\n return nested\n",
        "use = lambda Service: (Service(), Service)\n",
        "use = [Service() for Service in values]\n",
        "use = {Service() for Service in values}\n",
        "use = {Service(): Service for Service in values}\n",
        "use = (Service() for Service in values)\n",
    ],
)
def test_shadowed_names_do_not_resolve_module_declarations(body):
    _, _, calls, references = _facts("class Service: pass\n" + body)
    [call] = [item["data"] for item in calls if item["data"]["expression"] == "Service"]
    assert call["status"] == "unresolved" and call["targets"] == []
    assert not [item for item in references if "sample.core.Service" in item["data"]["targets"]]


def test_function_imports_do_not_leak_to_module_or_other_functions():
    module, _, calls, _ = _facts(
        "def first():\n from other import Service\n Service()\ndef second(): Service()\nService()\n"
    )
    assert "Service" not in module.aliases
    by_scope = {item["data"]["source_scope"]: item["data"] for item in calls}
    assert by_scope["sample.core.first"]["targets"] == ["other.Service"]
    assert by_scope["sample.core.second"]["targets"] == []
    assert by_scope["sample.core"]["targets"] == []


def test_two_function_imports_keep_their_own_aliases():
    _, _, calls, _ = _facts(
        "def first():\n import one as dependency\n dependency.run()\n"
        "def second():\n import two as dependency\n dependency.run()\n"
    )
    assert {item["data"]["source_scope"]: item["data"]["targets"] for item in calls} == {
        "sample.core.first": ["one.run"],
        "sample.core.second": ["two.run"],
    }


def test_class_namespace_is_not_a_method_closure():
    _, _, calls, _ = _facts(
        "from one import Service\nclass Owner:\n from two import Service\n"
        " Service()\n def use(self): Service()\n"
    )
    assert {item["data"]["source_scope"]: item["data"]["targets"] for item in calls} == {
        "sample.core.Owner": ["two.Service"],
        "sample.core.Owner.use": ["one.Service"],
    }


def test_explicit_global_and_nonlocal_keep_their_owner():
    _, _, calls, _ = _facts(
        "from one import Service\ndef outer():\n from two import Service\n"
        " def closure():\n  nonlocal Service\n  Service()\n"
        " def global_use():\n  global Service\n  Service()\n"
    )
    assert {item["data"]["source_scope"]: item["data"]["targets"] for item in calls} == {
        "sample.core.outer.closure": ["two.Service"],
        "sample.core.outer.global_use": ["one.Service"],
    }


def test_headers_are_evaluated_in_the_enclosing_scope():
    _, _, calls, references = _facts(
        "def factory(): pass\n@factory()\n"
        "def use(factory=factory()): return factory\n"
        "class Child(factory()): pass\n"
    )
    assert len(calls) == 3
    assert all(item["data"]["source_scope"] == "sample.core" for item in calls)
    assert not [item for item in references if item["data"]["source_scope"] == "sample.core.use"]


def test_comprehension_outer_iterator_uses_the_enclosing_scope():
    _, _, calls, _ = _facts("def Service(): pass\nuse = [Service() for Service in Service()]\n")
    assert sorted(item["data"]["status"] for item in calls) == ["resolved", "unresolved"]


@pytest.mark.parametrize(
    "expression,inlined_comprehension",
    [
        ("helper(items)", False),
        ("any(helper(name) for name in items) or any(item for item in items)", False),
        ("[helper(name) for name in items] or [item for item in items]", True),
        ("{helper(name) for name in items} or {item for item in items}", True),
        ("{name: helper(name) for name in items} or {item: item for item in items}", True),
    ],
    ids=["direct", "generator", "list", "set", "dict"],
)
def test_deferred_calls_follow_available_compiler_scope(expression, inlined_comprehension):
    source = f"def caller(items):\n return {expression}\ndef helper(item): return True\n"
    _, _, calls, _ = _facts(source)
    [call] = [item["data"] for item in calls if item["data"]["expression"] == "helper"]
    if inlined_comprehension and sys.version_info >= (3, 12):
        # PEP 709 removes the child table, but the inlined scope preserves its parent binding.
        caller = symtable.symtable(source, "sample.py", "exec").get_children()[0]
        assert caller.get_children() == []
    assert call["status"] == "resolved" and call["targets"] == ["sample.core.helper"]


def test_provider_parent_helper_is_referenced_from_both_actual_call_sites(tmp_path: Path):
    from test_dependency_api_target import _source_members

    package = tmp_path / "sample"
    package.mkdir()
    (package / "core.py").write_text(
        _source_members(
            "src/archkeel/analyzer/python/collect.py",
            {"_provider_bindings", "_provider_parents_static"},
        )
    )
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    observation = result.observation
    target = "sample.core._provider_parents_static"
    calls = [
        item
        for item in observation.records("calls") or ()
        if item.data.get("expression") == "_provider_parents_static"
    ]
    assert len(calls) == 2
    assert {
        (item.data.get("source_scope"), item.data.get("status"), item.data.get("targets"))
        for item in calls
    } == {("sample.core._provider_bindings", "resolved", (target,))}
    evidence = {item.id: item for item in observation.evidence}
    assert {evidence[item.evidence_ids[0]].excerpt.strip() for item in calls} == {
        "runtime_parent = _provider_parents_static(module.module, by_module)",
        "if not runtime_parent and not _provider_parents_static(",
    }
    assert target not in {item.name for item in unreferenced_symbols(observation).candidates}


@pytest.mark.parametrize(
    "source",
    [
        "def caller(items):\n"
        " return any(helper(name) for name in items) or any(name for name in items)\n"
        "def helper(item): return True\n",
        "def helper(): return True\ndef caller(helper, items):\n"
        " return any(helper() for name in items) or any(item for item in items)\n",
        "def helper(): return True\ndef caller(items):\n"
        " return any(helper() for helper in items) or any(item for item in items)\n",
        "def helper(): return True\ndef caller(items):\n"
        " return any((helper := name) for name in items) or any(helper() for item in items)\n",
        "value = any(helper(name) for name in items) or any(item for item in items)\n"
        "def helper(item): return True\n",
        "class Owner:\n"
        " value = any(helper(name) for name in items) or any(item for item in items)\n"
        "def helper(item): return True\n",
    ],
    ids=["same-targets", "free-parameter", "target-shadow", "walrus", "eager", "class-body"],
)
def test_same_line_comprehension_matching_keeps_unproven_bindings_unknown(source):
    _, _, calls, _ = _facts(source)
    [call] = [item["data"] for item in calls if item["data"]["expression"] == "helper"]
    assert call["status"] == "unresolved" and call["targets"] == []


def test_comprehension_matching_needs_a_real_compiler_table(monkeypatch):
    def unavailable(*_args):
        raise SyntaxError("compiler table unavailable")

    monkeypatch.setattr("archkeel.analyzer.python.scopes.symtable.symtable", unavailable)
    _, _, calls, _ = _facts(
        "def caller(items):\n"
        " return any(helper(name) for name in items) or any(item for item in items)\n"
        "def helper(item): return True\n"
    )
    [call] = [item["data"] for item in calls if item["data"]["expression"] == "helper"]
    assert call["status"] == "unresolved" and call["targets"] == []


def test_lambda_parameters_do_not_borrow_outer_receiver_types():
    _, _, calls, _ = _facts(
        "def use(value: str):\n value.strip()\n return lambda value: value.strip()\n"
    )
    assert sorted(item["data"]["status"] for item in calls) == [
        "partially_resolved",
        "unresolved",
    ]


def test_self_named_parameter_outside_method_is_not_a_class_receiver():
    _, _, calls, _ = _facts(
        "class Owner:\n def run(self): pass\n"
        " def use(self):\n  def nested(self): self.run()\n  return nested\n"
    )
    [call] = [item["data"] for item in calls]
    assert call["status"] != "resolved"


@pytest.mark.parametrize("body", ["def use(list): list()\n", "use = lambda list: list()\n"])
def test_shadowed_builtins_are_not_builtin_calls(body):
    _, _, calls, _ = _facts(body)
    [call] = [item["data"] for item in calls]
    assert call["status"] == "unresolved" and call["targets"] == []


def test_local_declarations_and_closures_are_not_module_attributes():
    _, _, calls, references = _facts(
        "def run(): pass\ndef outer():\n def run(): pass\n"
        " run()\n def closure():\n  run()\n  return run\n"
        " return closure\nouter.run()\n"
    )
    lexical = [item["data"] for item in calls if item["data"]["expression"] == "run"]
    assert len(lexical) == 2
    assert all(item["targets"] == ["sample.core.outer.run"] for item in lexical)
    assert all(item["status"] == "resolved" for item in lexical)
    [attribute] = [item["data"] for item in calls if item["data"]["expression"] == "outer.run"]
    assert attribute["status"] != "resolved"
    assert any(item["data"]["targets"] == ["sample.core.outer.run"] for item in references)


@pytest.mark.parametrize("prefix", ["if flag:", "try:"])
def test_conditional_imports_are_candidates(prefix):
    suffix = "except Exception: pass\n" if prefix == "try:" else ""
    _, _, calls, _ = _facts(f"{prefix}\n from one import Service\n{suffix}Service()\n")
    [call] = [item["data"] for item in calls]
    assert call["status"] == "partially_resolved" and call["targets"] == ["one.Service"]


def test_rebinding_an_import_cannot_leave_a_confirmed_call():
    _, _, calls, _ = _facts("import one as dependency\ndependency = value\ndependency.run()\n")
    [call] = [item["data"] for item in calls]
    assert call["status"] == "partially_resolved"


def test_shadowed_builtin_constructor_does_not_prove_a_literal_receiver():
    _, _, calls, _ = _facts("def use(list):\n value = list()\n value.append(1)\n")
    [call] = [item["data"] for item in calls if item["data"]["expression"] == "value.append"]
    assert call["status"] == "unresolved"


def test_a_closure_can_use_the_enclosing_method_receiver():
    _, _, calls, _ = _facts(
        "class Owner:\n def run(self): pass\n def use(self):\n"
        "  def nested(): self.run()\n  return nested\n"
    )
    [call] = [item["data"] for item in calls]
    assert call["status"] == "resolved" and call["targets"] == ["sample.core.Owner.run"]


def test_static_method_self_spelling_has_no_instance_proof():
    _, _, calls, _ = _facts(
        "class Owner:\n def run(self): pass\n @staticmethod\n def use(self): self.run()\n"
    )
    [call] = [item["data"] for item in calls]
    assert call["status"] != "resolved"


def test_ambiguous_same_line_lambda_tables_do_not_guess_which_parameter_binds():
    _, _, calls, _ = _facts(
        "class Service: pass\na = lambda Service: Service(); b = lambda other: Service()\n"
    )
    assert len(calls) == 2
    assert all(item["data"]["status"] == "unresolved" for item in calls)


def test_compiler_invalid_scope_cannot_authorize_module_fallback():
    _, _, calls, _ = _facts("class Service: pass\ndef use():\n nonlocal Service\n Service()\n")
    [call] = [item["data"] for item in calls]
    assert call["status"] == "unresolved"


def test_class_body_before_its_local_import_uses_globals():
    _, _, calls, _ = _facts(
        "from one import Service\nclass Owner:\n Service()\n from two import Service\n Service()\n"
    )
    assert {tuple(item["data"]["targets"]) for item in calls} == {
        ("one.Service",),
        ("two.Service",),
    }


def test_a_local_class_namespace_can_supply_a_declared_method():
    _, _, calls, _ = _facts(
        "def outer():\n class Service:\n  def run(self): pass\n Service.run()\n"
    )
    [call] = [item["data"] for item in calls]
    assert call["status"] == "resolved" and call["targets"] == ["sample.core.outer.Service.run"]


def test_namespace_values_are_referenced_without_proving_them_callable():
    _, _, calls, references = _facts(
        "from typing import TypeAlias\nLimit: TypeAlias = int\nTIMEOUT = 3\n"
        "def use(value: Limit): return TIMEOUT\nTIMEOUT()\n"
    )
    targets = {target for item in references for target in item["data"]["targets"]}
    assert {"sample.core.Limit", "sample.core.TIMEOUT"} <= targets
    [call] = [item["data"] for item in calls]
    assert call["status"] == "unresolved" and call["targets"] == []


@pytest.mark.parametrize(
    "prefix", ["VALUE = 1\nif flag:\n VALUE = 2\n", "VALUE = 1\nVALUE = other\n"]
)
def test_conditional_or_rebound_values_keep_uncertain_references(prefix):
    _, _, _, references = _facts(prefix + "def use(): return VALUE\n")
    [reference] = [item["data"] for item in references if item["data"]["expression"] == "VALUE"]
    assert reference["targets"] == ["sample.core.VALUE"]
    assert reference["status"] == "partially_resolved"


@pytest.mark.parametrize(
    "body",
    [
        "def use(VALUE): return VALUE\n",
        "def use():\n VALUE = 2\n return VALUE\n",
        "def use():\n VALUE = 2\n def inner(): return VALUE\n return inner\n",
    ],
)
def test_local_values_do_not_borrow_namespace_constants(body):
    _, _, _, references = _facts("VALUE = 1\n" + body)
    assert not [item for item in references if "sample.core.VALUE" in item["data"]["targets"]]


def test_class_values_do_not_borrow_globals_but_method_reads_use_globals():
    _, _, _, references = _facts(
        "VALUE = 1\nclass Owner:\n VALUE = 2\n local = VALUE\n def use(self): return VALUE\n"
    )
    assert {
        item["data"]["source_scope"]: item["data"]["targets"]
        for item in references
        if item["data"]["expression"] == "VALUE"
    } == {
        "sample.core.Owner.use": ["sample.core.VALUE"],
    }
