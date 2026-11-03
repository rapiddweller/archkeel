# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

import pytest
from test_analyzer import _parsed_module

from archkeel.analyzer.python.imports import collect_imports, resolve_reexports
from archkeel.analyzer.python.source import ParsedModule, unproven_member_bindings
from archkeel.analyzer.python.symbols import collect_symbols


def _resolve(modules: list[ParsedModule]) -> None:
    imports = collect_imports(
        modules, {module.module for module in modules}, {}, namespace="sample"
    )
    resolve_reexports(imports, {module.module: module.all_exports for module in modules}, modules)


@pytest.mark.parametrize(
    ("provider", "annotation"),
    [
        ("from collections.abc import Mapping", "Mapping[SexKey, float]"),
        ("from collections.abc import Sequence", "Sequence[SexKey]"),
        ("from typing import Mapping", "Mapping[SexKey, float]"),
        ("from typing import Sequence as S", "S[SexKey]"),
        ("from collections.abc import Mapping as M", "M[SexKey, float]"),
        ("import collections.abc as abc", "abc.Mapping[SexKey, float]"),
        ("import collections.abc", "collections.abc.Sequence[SexKey]"),
        ("import typing as t", "t.Sequence[SexKey]"),
        ("from collections.abc import Mapping", "dict[str, Mapping[SexKey, float]]"),
        ("from collections.abc import Mapping", "Mapping[SexKey, float] | None"),
    ],
)
@pytest.mark.parametrize("future", ["", "from __future__ import annotations\n"])
def test_proven_carriers_preserve_declared_alias_references(provider, annotation, future) -> None:
    module = _parsed_module(
        future + provider + "\nSexKey = str | None\ndef f(x: " + annotation + "): pass\n"
    )
    _resolve([module])
    assert "SexKey" not in unproven_member_bindings(module)
    symbols, _, _ = collect_symbols([module], {})
    alias = next(item for item in symbols if item["data"].get("name") == "SexKey")
    assert alias["data"]["source_member_binding_static"] is True


@pytest.mark.parametrize(
    "extra",
    [
        "Mapping = factory()\n",
        "def g(Mapping): pass\n",
        "Mapping.__class_getitem__ = unknown\n",
        "unknown(Mapping)\n",
        "unknown(SexKey)\n",
        "value = Mapping[SexKey, float]\n",
        "CarrierAlias = Mapping[SexKey, float]\n",
        "def g(x=unknown(SexKey)): pass\n",
        "@unknown(SexKey)\ndef g(): pass\n",
        "def g():\n global Mapping\n Mapping = unknown\n",
        "def g():\n Mapping = unknown\n def h():\n  nonlocal Mapping\n  Mapping = unknown\n",
        "from collections.abc import Mapping\n",
        "unknown(globals())\n",
    ],
)
def test_benign_annotation_does_not_hide_runtime_or_provider_uncertainty(extra) -> None:
    module = _parsed_module(
        "from collections.abc import Mapping\nSexKey = str | None\n"
        "def f(x: Mapping[SexKey, float]): pass\n" + extra
    )
    _resolve([module])
    assert "SexKey" in unproven_member_bindings(module)
    symbols, _, _ = collect_symbols([module], {})
    assert not any(
        item["kind"] == "type_alias" and item["title"] == "CarrierAlias" for item in symbols
    )


@pytest.mark.parametrize(
    "annotation",
    [
        "Mapping[mutate(SexKey), float]",
        "Mapping[Unknown[SexKey], float]",
        "Unknown[Mapping[SexKey, float]]",
    ],
)
def test_unknown_slice_operands_remain_executable(annotation) -> None:
    module = _parsed_module(
        "from collections.abc import Mapping\nSexKey = str | None\ndef f(x: "
        + annotation
        + "): pass\n"
    )
    _resolve([module])
    assert "SexKey" in unproven_member_bindings(module)


@pytest.mark.parametrize(
    ("provider", "annotation", "extra"),
    [
        ("from unknown import Mapping", "Mapping[SexKey, float]", ""),
        ("if flag:\n from collections.abc import Mapping", "Mapping[SexKey, float]", ""),
        (
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n from typing import Mapping",
            "Mapping[SexKey,float]",
            "",
        ),
        ("class Mapping: pass", "Mapping[SexKey, float]", ""),
        ("import collections.abc as abc", "abc.Mapping[SexKey, float]", "abc.Mapping = unknown\n"),
        ("import collections.abc as abc", "abc.Mapping[SexKey, float]", "unknown(abc)\n"),
        ("import collections.abc as abc", "abc.Mapping[SexKey, float]", "def g(abc): pass\n"),
    ],
)
def test_opaque_or_conditional_provider_keeps_alias_uncertain(provider, annotation, extra) -> None:
    module = _parsed_module(
        provider + "\nSexKey = str | None\ndef f(x: " + annotation + "): pass\n" + extra
    )
    _resolve([module])
    assert "SexKey" in unproven_member_bindings(module)


@pytest.mark.parametrize("provider", ["collections", "collections.abc", "typing"])
def test_scanned_provider_spelling_is_not_stdlib_identity(provider) -> None:
    modules = [
        _parsed_module("class Mapping: pass\n", module=provider),
        _parsed_module(
            "from "
            + provider
            + " import Mapping\nSexKey=str|None\ndef f(x:Mapping[SexKey,float]):pass\n"
        ),
    ]
    _resolve(modules)
    assert "SexKey" in unproven_member_bindings(modules[1])


@pytest.mark.parametrize("escape", ["Mapping", "SexKey"])
def test_incoming_escape_revokes_carrier_protection(escape) -> None:
    module = _parsed_module(
        "from collections.abc import Mapping\nSexKey=str|None\n"
        "def f(x:Mapping[SexKey,float]):pass\n"
    )
    module.incoming_member_escapes.add(escape)
    _resolve([module])
    assert "SexKey" in unproven_member_bindings(module)


@pytest.mark.parametrize("escape", ["", "SexKey", "Mapping", "mutated_Mapping"])
def test_cross_module_escape_revokes_original_and_consumer_protection(escape) -> None:
    modules = [
        _parsed_module(
            "from collections.abc import Mapping\nSexKey=str|None\n"
            "def f(x:Mapping[SexKey,float]):pass\n",
            module="sample.profile",
        ),
        _parsed_module("from .profile import SexKey\n", module="sample.facade"),
        _parsed_module(
            "from .facade import SexKey\nfrom collections.abc import Sequence\n"
            "def f(x:Sequence[SexKey]):pass\n",
            module="sample.consumer",
        ),
    ]
    if escape:
        provider = ".profile" if escape == "SexKey" else "collections.abc"
        binding = "Mapping" if escape == "mutated_Mapping" else escape
        usage = (
            "Mapping.__class_getitem__ = unknown"
            if escape == "mutated_Mapping"
            else "unknown(" + binding + ")"
        )
        modules.append(
            _parsed_module(
                "from " + provider + " import " + binding + "\n" + usage + "\n",
                module="sample.escape",
            )
        )
    _resolve(modules)
    assert ("SexKey" in unproven_member_bindings(modules[0])) is bool(escape)


def test_origin_refresh_replaces_occurrence_protection() -> None:
    module = _parsed_module(
        "from collections.abc import Mapping\nSexKey=str|None\n"
        "def f(x:Mapping[SexKey,float]):pass\n"
    )
    _resolve([module])
    assert "SexKey" not in unproven_member_bindings(module)
    module.incoming_member_escapes.add("Mapping")
    _resolve([module])
    assert "SexKey" in unproven_member_bindings(module)


@pytest.mark.requires_python(12)
def test_pep695_carrier_value_is_not_a_new_annotation_site() -> None:
    module = _parsed_module(
        "from collections.abc import Mapping\nSexKey=str|None\n"
        "type Carrier = Mapping[SexKey,float]\n"
    )
    _resolve([module])
    assert "SexKey" in unproven_member_bindings(module)


def test_annotation_does_not_hide_class_base_owner_exposure() -> None:
    module = _parsed_module(
        "from collections.abc import Mapping\nSexKey=str|None\n"
        "def f(x:Mapping[SexKey,float]):pass\n"
        "class C(Mapping): pass\n"
    )
    _resolve([module])
    assert "C" in unproven_member_bindings(module)


def test_annotated_alias_value_does_not_gain_carrier_protection() -> None:
    module = _parsed_module(
        "from typing import TypeAlias\nfrom collections.abc import Mapping\n"
        "SexKey=str|None\nCarrier: TypeAlias = Mapping[SexKey,float]\n"
    )
    _resolve([module])
    assert "SexKey" in unproven_member_bindings(module)


@pytest.mark.parametrize(
    "annotation", ["Mapping[SexKey]", "Mapping[SexKey, float, int]", "Sequence[SexKey, float]"]
)
def test_wrong_carrier_arity_keeps_alias_uncertain(annotation) -> None:
    module = _parsed_module(
        "from collections.abc import Mapping, Sequence\nSexKey=str|None\ndef f(x:"
        + annotation
        + "):pass\n"
    )
    _resolve([module])
    assert "SexKey" in unproven_member_bindings(module)


@pytest.mark.parametrize(
    "changed",
    [
        {"source_binding_unique": False},
        {"origin_binding_unique": False},
        {"reexport_chain": ["sample.facade.Mapping", "collections.abc.Mapping"]},
        {"reexport_candidate": True},
        {"reexport_candidates": ["unknown.Mapping"]},
    ],
)
def test_uncertain_import_evidence_cannot_waive_opaque_member_uncertainty(changed) -> None:
    from archkeel.analyzer.python.imports import _opaque_import_member_escapes

    module = _parsed_module(
        "from collections.abc import Mapping\nSexKey=str|None\n"
        "def f(x:Mapping[SexKey,float]):pass\n"
    )
    imports = collect_imports([module], {module.module}, {}, namespace="sample")
    resolve_reexports(imports, {module.module: module.all_exports}, [module])
    data = imports[0]["data"] | changed
    assert _opaque_import_member_escapes(
        data, module, owner_exposure_only=False, unsafe_providers=frozenset()
    ) == {"Mapping"}


@pytest.mark.parametrize(
    "head",
    ["collections.abc.Mapping", "collections.abc.Sequence", "typing.Mapping", "typing.Sequence"],
)
@pytest.mark.parametrize("scanned", [False, True])
def test_module_import_cannot_prove_a_native_carrier_class(head, scanned) -> None:
    binding = head.rpartition(".")[2]
    args = "SexKey, float" if binding == "Mapping" else "SexKey"
    modules = [
        _parsed_module(
            "import "
            + head
            + " as "
            + binding
            + "\nSexKey=str|None\ndef f(x:"
            + binding
            + "["
            + args
            + "]):pass\n"
        )
    ]
    if scanned:
        modules.append(_parsed_module("class Other: pass\n", module=head))
    _resolve(modules)
    assert "SexKey" in unproven_member_bindings(modules[0])


@pytest.mark.parametrize(
    "head",
    ["collections.abc.Mapping", "collections.abc.Sequence", "typing.Mapping", "typing.Sequence"],
)
def test_scanned_exact_carrier_head_invalidates_symbol_import_identity(head) -> None:
    provider, _, binding = head.rpartition(".")
    args = "SexKey, float" if binding == "Mapping" else "SexKey"
    modules = [
        _parsed_module("class Other: pass\n", module=head),
        _parsed_module(
            "from "
            + provider
            + " import "
            + binding
            + "\nSexKey=str|None\ndef f(x:"
            + binding
            + "["
            + args
            + "]):pass\n"
        ),
    ]
    _resolve(modules)
    assert "SexKey" in unproven_member_bindings(modules[1])
