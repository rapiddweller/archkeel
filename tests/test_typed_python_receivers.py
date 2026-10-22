# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Receiver origins retain legacy inputs and conservative call evidence."""

import ast
import copy
import inspect
import json
import sys
from dataclasses import FrozenInstanceError
from enum import Enum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_analyzer import _observe_one_rule, _parsed_module
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.analyzer.python import receiver_types
from archkeel.analyzer.python.calls import _bind_receiver, _local_receiver_types, collect_calls
from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.receiver_types import ReceiverType
from archkeel.analyzer.python.resolve import _resolve_receiver_bound_call, build_symbol_index
from archkeel.analyzer.python.scopes import LexicalScopes
from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
ORIGINS = ("literal", "annotation", "documented")


def _origin_type():
    annotation = get_type_hints(ReceiverType)["origin"]
    assert isinstance(annotation, type) and issubclass(annotation, Enum), annotation
    assert not issubclass(annotation, str)
    return annotation


def test_receiver_origin_field_and_existing_alias_are_nominal():
    assert receiver_types.Origin is _origin_type()


@pytest.mark.parametrize("raw", ORIGINS)
def test_receiver_constructor_normalizes_valid_legacy_origins(raw):
    value = ReceiverType("arbitrary.QualifiedType", raw)
    assert isinstance(value.origin, _origin_type())
    assert value.origin.value == raw and value.type_name == "arbitrary.QualifiedType"


@pytest.mark.parametrize("raw", ORIGINS)
def test_receiver_constructor_preserves_nominal_identity_and_immutability(raw):
    origin = _origin_type()(raw)
    value = ReceiverType("list", origin)
    assert value.origin is origin
    with pytest.raises(FrozenInstanceError):
        value.origin = origin


@pytest.mark.parametrize("raw", ["", "unknown", None, 7])
def test_receiver_constructor_rejects_invalid_origin(raw):
    with pytest.raises(ValueError):
        ReceiverType("list", raw)


def test_receiver_constructor_keeps_required_origin_parameter():
    assert inspect.signature(ReceiverType).parameters["origin"].default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        ReceiverType("list")


def test_actual_receiver_producers_publish_all_three_nominal_origins():
    module = _parsed_module(
        "from pathlib import Path\n"
        "def use(annotated: list[str]):\n"
        "    literal = []\n"
        "    documented = Path('value')\n"
    )
    collect_imports([module], set(), {}, namespace="sample")
    node = next(item for item in module.tree.body if isinstance(item, ast.FunctionDef))
    actual = _local_receiver_types(node, LexicalScopes(module))
    assert set(actual) == {"annotated", "literal", "documented"}
    assert all(isinstance(value.origin, _origin_type()) for value in actual.values())
    assert {name: value.origin.value for name, value in actual.items()} == {
        "annotated": "annotation",
        "literal": "literal",
        "documented": "documented",
    }


@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            "literal",
            ("resolved", ["builtins.list.append"], "literal-bound receiver of known type", 1),
        ),
        (
            "annotation",
            (
                "partially_resolved",
                ["builtins.list.append"],
                "annotated receiver of known type, unproven at runtime",
                1,
            ),
        ),
        (
            "documented",
            (
                "partially_resolved",
                ["builtins.list.append"],
                "receiver bound to a call result of documented type, unproven at runtime",
                1,
            ),
        ),
    ],
)
def test_legacy_origin_keeps_real_resolver_verdict_and_wire_values(raw, expected):
    assert (
        _resolve_receiver_bound_call(["items", "append"], {"items": ReceiverType("list", raw)})
        == expected
    )


@pytest.mark.parametrize(
    "first,second,expected",
    [
        ("literal", "literal", "literal"),
        ("literal", "annotation", "annotation"),
        ("literal", "documented", "documented"),
        ("annotation", "literal", "annotation"),
        ("annotation", "annotation", "annotation"),
        ("annotation", "documented", "annotation"),
        ("documented", "literal", "documented"),
        ("documented", "annotation", "documented"),
        ("documented", "documented", "documented"),
    ],
)
def test_receiver_merge_never_upgrades_an_unproven_binding(first, second, expected):
    values = {"items": ReceiverType("list", first)}
    _bind_receiver(values, "items", ReceiverType("list", second))
    result = values["items"]
    assert result is not None
    origin = result.origin.value if isinstance(result.origin, Enum) else result.origin
    assert origin == expected


def test_actual_receiver_merge_has_no_raw_origin_dispatch(tmp_path):
    result = _observe_one_rule(
        tmp_path,
        {
            "kind": "forbidden_construct",
            "source": "sample.core",
            "constructs": ["string_literal_compare"],
        },
        {"core.py": (ROOT / "src/archkeel/analyzer/python/calls.py").read_text()},
    )
    assert result.diagnostics == () and result.observation is not None
    assert not [
        row
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
        and row.data.get("owner") == "sample.core._bind_receiver"
    ]


@pytest.mark.parametrize(
    "source",
    [
        "def use():\n    items = []\n    items = {}\n    items.append(1)\n",
        "def use(list):\n    items = list()\n    items.append(1)\n",
        "def use():\n    items = []\n    for items in (): pass\n    items.append(1)\n",
    ],
)
def test_ambiguous_and_shadowed_receivers_stay_unresolved(source):
    rows = collect_calls([_parsed_module(source)], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "items.append")
    assert call["status"] == "unresolved" and call["targets"] == []


@pytest.mark.parametrize(
    "source,expression,target",
    [
        (
            "from subprocess import Popen as Child\n"
            "def use(process: Child[bytes]): process.poll()\n",
            "process.poll",
            "subprocess.Popen.poll",
        ),
        (
            "import subprocess as sp\n"
            "def use(process: sp.Popen[bytes]): process.wait()\n",
            "process.wait",
            "subprocess.Popen.wait",
        ),
        (
            "from threading import Thread as Worker, Event as Ready\n"
            "def use(worker: Worker, ready: Ready):\n"
            " worker.join()\n"
            " ready.set()\n",
            "worker.join",
            "threading.Thread.join",
        ),
        (
            "from subprocess import Popen as Child\n"
            "def use():\n process = Child(['tool'])\n process.kill()\n",
            "process.kill",
            "subprocess.Popen.kill",
        ),
        (
            "from threading import Thread as Worker\n"
            "def use():\n worker = Worker(target=work)\n worker.start()\n",
            "worker.start",
            "threading.Thread.start",
        ),
        (
            "import threading as th\n"
            "def use():\n ready = th.Event()\n ready.is_set()\n",
            "ready.is_set",
            "threading.Event.is_set",
        ),
        (
            "from threading import Event as Ready\n"
            "def use(ready: Ready): ready.set()\n",
            "ready.set",
            "threading.Event.set",
        ),
    ],
)
def test_import_bound_external_receiver_calls_are_partial(source, expression, target):
    module = _parsed_module(source)
    collect_imports([module], set(), {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == expression)
    assert call["status"] == "partially_resolved" and call["targets"] == [target]


@pytest.mark.parametrize(
    "source,expression",
    [
        ("def use(process: Popen): process.poll()\n", "process.poll"),
        ("def use(process: subprocess.Popen[bytes]): process.poll()\n", "process.poll"),
        (
            "from subprocess import Popen as Child\n"
            "def use(process: Child[str]): process.poll()\n",
            "process.poll",
        ),
        (
            "from threading import Event as Ready\n"
            "def use(ready: Ready[int]): ready.set()\n",
            "ready.set",
        ),
        (
            "from subprocess import Popen as Child\n"
            "bytes = object\n"
            "def use(process: Child[bytes]): process.poll()\n",
            "process.poll",
        ),
        (
            "from subprocess import Popen as Child\n"
            "Child = object\n"
            "def use(process: Child[bytes]): process.poll()\n",
            "process.poll",
        ),
        (
            "from subprocess import Popen as Child\n"
            "def use(Child):\n def nested(process: Child[bytes]): process.poll()\n",
            "process.poll",
        ),
        (
            "from subprocess import Popen as Child\n"
            "def use(process: Child[bytes] | object): process.poll()\n",
            "process.poll",
        ),
        (
            "from threading import Thread as Worker\n"
            "def use(worker: Worker | None): worker.join()\n",
            "worker.join",
        ),
    ],
)
def test_unproven_external_receiver_annotations_stay_unresolved(source, expression):
    module = _parsed_module(source)
    collect_imports([module], set(), {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == expression)
    assert call["status"] == "unresolved" and call["targets"] == []


def test_external_receiver_annotation_needs_its_compiler_scope():
    module = _parsed_module(
        "from subprocess import Popen as Child\n"
        "def use(process: Child[bytes]): process.poll()\n"
    )
    collect_imports([module], set(), {}, namespace="sample")
    module.source = "def incomplete("
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "process.poll")
    assert call["status"] == "unresolved" and call["targets"] == []


@pytest.mark.parametrize(
    "source,expression,target",
    [
        (
            "def use(): return ''.join(['x']).encode()\n",
            "''.join(['x']).encode",
            "builtins.str.encode",
        ),
        (
            "def use(value: str): return value.strip().casefold()\n",
            "value.strip().casefold",
            "builtins.str.casefold",
        ),
        (
            "def use():\n value = ''.join(['x'])\n value.encode()\n",
            "value.encode",
            "builtins.str.encode",
        ),
    ],
)
def test_string_return_methods_reuse_documented_receiver_evidence(source, expression, target):
    rows = collect_calls([_parsed_module(source)], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == expression)
    assert call["status"] == "partially_resolved" and call["targets"] == [target]


@pytest.mark.parametrize(
    "source,expression",
    [
        ("def use(value): return value.strip().casefold()\n", "value.strip().casefold"),
        ("def use(value: dict): return value.strip().casefold()\n", "value.strip().casefold"),
        ("def use(value: str): return value.opaque().casefold()\n", "value.opaque().casefold"),
        (
            "def use():\n value = ''.join(['x'])\n value = other\n value.encode()\n",
            "value.encode",
        ),
        (
            "def use(value: str):\n return (lambda value: value.strip().casefold())([])\n",
            "value.strip().casefold",
        ),
    ],
)
def test_unproven_string_method_results_keep_unknown_receiver(source, expression):
    rows = collect_calls([_parsed_module(source)], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == expression)
    assert call["status"] == "unresolved" and call["targets"] == []


def test_documented_string_result_needs_its_compiler_owner_for_named_receiver():
    module = _parsed_module("def use():\n value = ''.join(['x'])\n value.encode()\n")
    module.source = "def incomplete("
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "value.encode")
    assert call["status"] == "unresolved" and call["targets"] == []


def test_string_method_return_does_not_claim_subclass_runtime_behavior():
    source = (
        "class Special(str):\n def strip(self): return 42\n"
        "def use(value: str): return value.strip().casefold()\n"
    )
    rows = collect_calls([_parsed_module(source)], build_symbol_index([]), {})
    call = next(
        row["data"] for row in rows if row["data"]["expression"] == "value.strip().casefold"
    )
    assert call["status"] == "partially_resolved"
    namespace = {}
    exec(source, namespace)
    with pytest.raises(AttributeError):
        namespace["use"](namespace["Special"]("value"))


@pytest.mark.parametrize(
    "source, expression, target",
    [
        (
            "def make() -> list[str]: return []\n"
            "def use():\n values = make()\n values.append('x')\n",
            "values.append",
            "builtins.list.append",
        ),
        (
            "def make() -> str:\n opaque()\n return 'x'\ndef use(): return make().strip()\n",
            "make().strip",
            "builtins.str.strip",
        ),
        (
            "def use():\n def make() -> dict[str, str]: return {}\n"
            " values = make()\n values.keys()\n",
            "values.keys",
            "builtins.dict.keys",
        ),
    ],
)
def test_unique_local_helper_return_keeps_documented_receiver_origin(source, expression, target):
    rows = collect_calls([_parsed_module(source)], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == expression)
    assert call["status"] == "partially_resolved" and call["targets"] == [target]


@pytest.mark.parametrize(
    "definition",
    [
        "async def make() -> list[str]: return []\n",
        "def make() -> list[str]: yield 'x'\n",
        "@opaque\ndef make() -> list[str]: return []\n",
        "def make() -> list[str]: return []\nmake = other\n",
        "if flag:\n def make() -> list[str]: return []\n",
        "def make() -> list[str]: return []\ndef make() -> list[str]: return []\n",
        "list = Other\ndef make() -> list[str]: return []\n",
        "def make() -> 'list[str]': return []\n",
        "Alias = list[str]\ndef make() -> Alias: return []\n",
        "class Payload: pass\ndef make() -> Payload: return Payload()\n",
        "def make(): return []\n",
        "def make() -> list[str]: return []\ndel make\n",
        "from builtins import list\ndef make() -> list[str]: return []\n",
        "def make() -> list[str]: return []\ndef replace():\n global make\n make = other\n",
        "from opaque import make\n",
        "from opaque import *\ndef make() -> list[str]: return []\n",
        "",
    ],
)
def test_uncertain_helper_declarations_do_not_prove_returned_receiver(definition):
    module = _parsed_module(definition + "def use():\n values = make()\n values.append('x')\n")
    collect_imports([module], {module.module}, {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "values.append")
    assert call["status"] == "unresolved" and call["targets"] == []


@pytest.mark.parametrize(
    "body",
    [
        " values = []\n values = make()\n values.append('x')\n",
        " values = make()\n values = []\n values.append('x')\n",
        " values = other = make()\n values.append('x')\n",
        " if flag:\n  values = make()\n values.append('x')\n",
    ],
)
def test_helper_result_does_not_inherit_another_assignment_literal_origin(body):
    source = "def make() -> list[str]: return []\ndef use():\n" + body
    rows = collect_calls([_parsed_module(source)], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "values.append")
    assert call["status"] == "unresolved" and call["targets"] == []


def test_local_helper_return_needs_a_matching_compiler_scope():
    module = _parsed_module(
        "def make() -> list[str]: return []\ndef use():\n values = make()\n values.append('x')\n"
    )
    module.source = "def incomplete("
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "values.append")
    assert call["status"] == "unresolved" and call["targets"] == []


@pytest.mark.parametrize(
    "source",
    [
        "def use():\n values = {1, 2}\n values.copy()\n",
        "def use(items):\n values = {item for item in items}\n values.copy()\n",
        "def use(set):\n values = {1}\n values.copy()\n",
        "set = other\ndef use(items):\n values = {item for item in items}\n values.copy()\n",
    ],
)
def test_set_syntax_proves_the_builtin_receiver_even_when_set_name_is_shadowed(source):
    rows = collect_calls([_parsed_module(source)], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "values.copy")
    assert call["status"] == "resolved"
    assert call["targets"] == ["builtins.set.copy"]


@pytest.mark.parametrize(
    "source",
    [
        "def use(set):\n values = set()\n values.copy()\n",
        "def use():\n values = {1}\n values = []\n values.copy()\n",
        "def use(items):\n values = {item for item in items}\n values = other\n values.copy()\n",
    ],
)
def test_set_receiver_does_not_absolve_shadowed_constructors_or_conflicting_bindings(source):
    rows = collect_calls([_parsed_module(source)], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "values.copy")
    assert call["status"] == "unresolved" and call["targets"] == []


@pytest.mark.parametrize("literal", ["{2}", "{item for item in [2]}", "set()"])
def test_later_set_literal_does_not_prove_an_earlier_annotated_receiver(literal):
    source = (
        "class Special(set):\n def add(self, value): return 'custom'\n"
        "def use(values: set):\n result = values.add(1)\n"
        f" values = {literal}\n return result\n"
    )
    rows = collect_calls([_parsed_module(source)], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "values.add")
    assert call["status"] == "partially_resolved"
    assert call["targets"] == ["builtins.set.add"]
    namespace = {}
    exec(source, namespace)
    assert namespace["use"](namespace["Special"]()) == "custom"


@pytest.mark.parametrize("method", ["split", "rsplit", "splitlines"])
@pytest.mark.parametrize(
    "expression",
    [
        "(part.isidentifier() for part in module.METHOD())",
        "[part.isidentifier() for part in module.METHOD()]",
        "{part.isidentifier() for part in module.METHOD()}",
        "{part: part.isidentifier() for part in module.METHOD()}",
    ],
)
def test_string_method_elements_keep_documented_receiver_proof(method, expression):
    module = _parsed_module(
        "def use(module: str):\n    return " + expression.replace("METHOD", method) + "\n"
    )
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "part.isidentifier")
    # PEP 709 removes these compiler scopes; their element binding stays unproven.
    status = (
        "unresolved"
        if sys.version_info >= (3, 12) and not expression.startswith("(")
        else "partially_resolved"
    )
    assert call["status"] == status
    assert call["targets"] == ([] if status == "unresolved" else ["builtins.str.isidentifier"])


@pytest.mark.parametrize(
    "source",
    [
        "def use(module):\n return [part.isidentifier() for part in module.split()]\n",
        "def use(module: str):\n module = other()\n"
        " return [part.isidentifier() for part in module.split()]\n",
        "class str: pass\ndef use(module: str):\n"
        " return [part.isidentifier() for part in module.split()]\n",
        "def use(module: str):\n return [part.isidentifier() for part, other in module.split()]\n",
        "def use(module: str):\n"
        " return [part.isidentifier() for part in module.split() for part in unknown()]\n",
        "def use(module: str):\n"
        " return [(lambda part: part.isidentifier())(1) for part in module.split()]\n",
        "def use(module: str):\n return [part.isidentifier() for part in module.custom()]\n",
        "async def use(module: str):\n"
        " return [part.isidentifier() async for part in module.split()]\n",
    ],
)
def test_unproven_or_shadowed_comprehension_elements_stay_unresolved(source):
    module = _parsed_module(source)
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "part.isidentifier")
    assert call["status"] == "unresolved" and call["targets"] == []


def test_comprehension_receiver_proof_does_not_escape_its_owner():
    module = _parsed_module(
        "def use(module: str):\n"
        " part = []\n"
        " result = [part.isidentifier() for part in module.split()]\n"
        " part.append(result)\n"
        " part.isidentifier()\n"
    )
    rows = collect_calls([module], build_symbol_index([]), {})
    calls = [row["data"] for row in rows if row["data"]["expression"] == "part.isidentifier"]
    inner_status = "unresolved" if sys.version_info >= (3, 12) else "partially_resolved"
    assert sorted(call["status"] for call in calls) == [inner_status, "unresolved"]
    assert all(call["targets"] == [] for call in calls if call["status"] == "unresolved")
    append = next(row["data"] for row in rows if row["data"]["expression"] == "part.append")
    assert append["status"] == "resolved" and append["targets"] == ["builtins.list.append"]


@pytest.mark.parametrize("annotation,status", [(": str", "partially_resolved"), ("", "unresolved")])
def test_nested_comprehensions_reuse_only_their_own_proven_elements(annotation, status):
    module = _parsed_module(
        f"def use(module{annotation}):\n"
        " return [[part.isidentifier() for part in line.split()]\n"
        "         for line in module.splitlines()]\n"
    )
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "part.isidentifier")
    if sys.version_info >= (3, 12):
        status = "unresolved"
    assert call["status"] == status
    assert call["targets"] == ([] if status == "unresolved" else ["builtins.str.isidentifier"])


@pytest.mark.parametrize(
    "source, status",
    [
        ("def use(path: Path):\n    path.is_relative_to('root')\n", "partially_resolved"),
        (
            "def use():\n    path = Path('child')\n    path.is_relative_to('root')\n",
            "partially_resolved",
        ),
        (
            "def use(Path):\n    path = Path('child')\n    path.is_relative_to('root')\n",
            "unresolved",
        ),
    ],
)
def test_path_containment_retains_partial_evidence_and_shadowing(source, status):
    module = _parsed_module("from pathlib import Path\n" + source)
    collect_imports([module], set(), {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "path.is_relative_to")
    assert call["status"] == status
    assert call["targets"] == ([] if status == "unresolved" else ["pathlib.Path.is_relative_to"])


@pytest.mark.parametrize(
    "source", ["dict.fromkeys(('x',))", "def use(): return dict.fromkeys(('x',))"]
)
def test_unshadowed_builtin_dict_classmethod_keeps_partial_evidence(source):
    rows = collect_calls([_parsed_module(source)], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "dict.fromkeys")
    assert call["status"] == "partially_resolved"
    assert call["targets"] == ["builtins.dict.fromkeys"]


@pytest.mark.parametrize("source", ["str.split('a,b', ',')", "def use(): return str.split('a')"])
def test_unshadowed_builtin_str_method_keeps_partial_evidence(source):
    rows = collect_calls([_parsed_module(source)], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "str.split")
    assert call["status"] == "partially_resolved"
    assert call["targets"] == ["builtins.str.split"]


@pytest.mark.parametrize(
    "source,expression",
    [
        ("def use(dict): return dict.fromkeys(('x',))", "dict.fromkeys"),
        ("def use():\n dict = other\n return dict.fromkeys(('x',))", "dict.fromkeys"),
        ("def use():\n dict.fromkeys(('x',))\n dict = other", "dict.fromkeys"),
        ("if enabled: dict = other\ndict.fromkeys(('x',))", "dict.fromkeys"),
        ("dict = other\ndef use():\n global dict\n return dict.fromkeys(('x',))", "dict.fromkeys"),
        (
            "def overwrite():\n global dict\n dict = other\n"
            "def use(): return dict.fromkeys(('x',))",
            "dict.fromkeys",
        ),
        ("D = dict\nD.fromkeys(('x',))", "D.fromkeys"),
        ("class D(dict): pass\nD.fromkeys(('x',))", "D.fromkeys"),
        ("from custom import dict\ndict.fromkeys(('x',))", "dict.fromkeys"),
        ("dict.madeup(('x',))", "dict.madeup"),
    ],
)
def test_builtin_dict_classmethod_does_not_escape_its_exact_binding(source, expression):
    module = _parsed_module(source)
    collect_imports([module], set(), {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == expression)
    assert "builtins.dict.fromkeys" not in call["targets"]
    if "from custom" not in source:
        assert call["status"] == "unresolved" and call["targets"] == []


@pytest.mark.parametrize(
    "source",
    [
        "def use(str): return str.split('value')",
        "def use():\n str = other\n return str.split('value')",
        "if enabled: str = other\nstr.split('value')",
        "from custom import str\nstr.split('value')",
        "class str:\n def split(self): pass\n def use(self): return str.split(self)",
        "str.madeup('value')",
    ],
)
def test_builtin_class_method_resolution_keeps_shadowing_and_method_table_boundaries(source):
    module = _parsed_module(source)
    collect_imports([module], {module.module}, {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(
        row["data"] for row in rows if row["data"]["expression"] in {"str.split", "str.madeup"}
    )
    assert "builtins.str.split" not in call["targets"]
    assert "builtins.str.madeup" not in call["targets"]
    if source == "str.madeup('value')":
        assert call["status"] == "unresolved" and call["targets"] == []


def _receiver_repository(tmp_path):
    contract = copy.deepcopy(
        json.loads((ROOT / "docs/architecture/contracts/python.json").read_text())
    )
    contract.pop("$schema", None)
    root_contract = json.loads((ROOT / "architecture-contract.json").read_text())
    contract["rules"] = [
        rule for rule in root_contract["rules"] if rule["id"] == "PYTHON-RECEIVERS-TYPED-CONTROL"
    ]
    contract["declarations"]["uml"]["entities"] = [
        item
        for item in contract["declarations"]["uml"]["entities"]
        if item["id"].startswith("PYTHON-RECEIVER-")
    ]
    files = {
        "archkeel/__init__.py": "",
        "archkeel/analyzer/__init__.py": "",
        "archkeel/analyzer/python/__init__.py": "",
        "archkeel/analyzer/python/receiver_types.py": (
            ROOT / "src/archkeel/analyzer/python/receiver_types.py"
        ).read_text(),
        "contract.json": json.dumps(contract),
        "docs/architecture/typed-python-receivers.md": "Owned receiver origins.\n",
    }
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_native_receiver_api_fulfils_owned_origin_target_and_module_guard(tmp_path):
    root, config = _receiver_repository(tmp_path)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assessment = next(
        row
        for row in rule_assessments(model, undecided_by_rule={})
        if row.id == "PYTHON-RECEIVERS-TYPED-CONTROL"
    )
    assert assessment.status == "PASS" and assessment.evaluation_proven
    assert not trace_valid_violations(model)


def test_native_receiver_origin_widening_fails_unchanged_target(tmp_path):
    root, config = _receiver_repository(tmp_path)
    path = root / "archkeel/analyzer/python/receiver_types.py"
    source = path.read_text()
    assert "origin: ReceiverOrigin" in source
    path.write_text(source.replace("origin: ReceiverOrigin", "origin: str", 1))
    contract = (root / "contract.json").read_bytes()
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None
    assert any(
        item.aspect == "annotation" and item.status == "FAIL" for item in comparison.assessments
    )
    assert trace_valid_violations(model)
    assert (root / "contract.json").read_bytes() == contract


@pytest.mark.parametrize(
    "probe",
    [
        'def _probe(value):\n    return value == "literal"\n',
        'def _probe(value):\n    return value in ("literal", "annotation")\n',
        "def _probe(value):\n    return value == ReceiverOrigin.LITERAL.value\n",
    ],
)
def test_native_receiver_model_rejects_raw_origin_dispatch(tmp_path, probe):
    root, config = _receiver_repository(tmp_path)
    path = root / "archkeel/analyzer/python/receiver_types.py"
    path.write_text(path.read_text() + "\n" + probe)
    model = _model(root, config)
    assert [
        row
        for row in trace_valid_violations(model)
        if "PYTHON-RECEIVERS-TYPED-CONTROL" in row.rule_ids
    ]
