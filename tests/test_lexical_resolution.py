# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A lexical name must not borrow an unrelated module binding."""

import pytest
from test_analyzer import _parsed_module

from archkeel.analyzer.python.calls import collect_calls
from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.references import collect_references
from archkeel.analyzer.python.resolve import build_symbol_index
from archkeel.analyzer.python.symbols import collect_symbols


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
