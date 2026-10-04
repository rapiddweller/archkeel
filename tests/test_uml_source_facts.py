# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Static UML facts come from source syntax, without contract or layout policy."""

from test_analyzer import _parsed_module

from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.symbols import collect_symbols


def _symbols(source: str) -> dict:
    module = _parsed_module(source)
    collect_imports([module], {module.module}, {}, namespace="sample")
    items, _, _ = collect_symbols([module], {})
    return {item["data"]["name"]: item["data"] for item in items}


def test_operation_parameters_keep_source_order_kinds_and_defaults() -> None:
    symbols = _symbols(
        "def run(a: int, /, b=None, *values: str, flag: bool=True, required, **options): pass"
    )
    assert symbols["run"]["parameters"] == [
        {
            "name": "a",
            "annotation": "int",
            "kind": "positional_only",
            "default": None,
            "default_known": True,
        },
        {
            "name": "b",
            "annotation": None,
            "kind": "positional",
            "default": "None",
            "default_known": True,
        },
        {
            "name": "*values",
            "annotation": "str",
            "kind": "varargs",
            "default": None,
            "default_known": True,
        },
        {
            "name": "flag",
            "annotation": "bool",
            "kind": "keyword_only",
            "default": "True",
            "default_known": True,
        },
        {
            "name": "required",
            "annotation": None,
            "kind": "keyword_only",
            "default": None,
            "default_known": True,
        },
        {
            "name": "**options",
            "annotation": None,
            "kind": "kwargs",
            "default": None,
            "default_known": True,
        },
    ]


def test_static_defaults_are_recorded_without_execution() -> None:
    symbols = _symbols("def run(value=raise_if_executed()): pass")
    [parameter] = symbols["run"]["parameters"]
    assert parameter["default"] == "raise_if_executed()"
    assert parameter["default_known"] is True


def test_python_visibility_distinguishes_conventions_from_special_methods() -> None:
    symbols = _symbols(
        "class Service:\n def __init__(self): pass\n def _internal(self): pass\n"
        " def __secret(self): pass\n def run(self): pass\n"
    )
    assert {
        name: symbols[name]["visibility_detail"]
        for name in ("__init__", "_internal", "__secret", "run")
    } == {
        "__init__": {"kind": "public", "basis": "convention", "spelling": "__init__"},
        "_internal": {"kind": "private", "basis": "convention", "spelling": "_internal"},
        "__secret": {"kind": "private", "basis": "convention", "spelling": "__secret"},
        "run": {"kind": "public", "basis": "convention", "spelling": "run"},
    }
    # The legacy name filter is not the structured language visibility.
    assert symbols["__init__"]["visibility"] == "private"


def test_private_attribute_inventory_does_not_expand_the_public_api() -> None:
    symbols = _symbols("class Service:\n _token: str\n count: int = 1\n")
    assert symbols["Service"]["fields"] == [{"name": "count", "annotation": "int"}]
    attributes = symbols["Service"]["attribute_declarations"]
    assert all(item["definition_id"] and item["evidence_ids"] for item in attributes)
    assert [
        {key: item[key] for key in ("name", "annotation", "visibility")} for item in attributes
    ] == [
        {
            "name": "_token",
            "annotation": "str",
            "visibility": {"kind": "private", "basis": "convention", "spelling": "_token"},
        },
        {
            "name": "count",
            "annotation": "int",
            "visibility": {"kind": "public", "basis": "convention", "spelling": "count"},
        },
    ]


def test_protocol_implementation_is_a_class_and_extension_is_an_interface() -> None:
    symbols = _symbols(
        "from typing import Protocol\n"
        "class Port(Protocol):\n def run(self): ...\n"
        "class Client(Port):\n def run(self): pass\n"
        "class Extended(Port, Protocol): pass\n"
    )
    assert symbols["Port"]["class_kind"] == "protocol"
    assert symbols["Client"]["class_kind"] == "class"
    assert symbols["Extended"]["class_kind"] == "protocol"


def test_redefined_classifiers_keep_each_definitions_own_kind() -> None:
    module = _parsed_module(
        "from typing import Protocol\nclass Port(Protocol): pass\nclass Port: pass\n"
    )
    collect_imports([module], {module.module}, {}, namespace="sample")
    symbols, _, _ = collect_symbols([module], {})
    ports = [item for item in symbols if item["data"]["name"] == "Port"]
    assert len(ports) == 2
    assert {item["data"].get("class_kind") for item in ports} == {"protocol", "class"}
