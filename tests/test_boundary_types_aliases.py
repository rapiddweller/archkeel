# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Static annotation forms used by boundary_types."""

from __future__ import annotations

import ast
from pathlib import Path

from archkeel.analyzer.embedded.source import AliasBinding, ParsedModule
from archkeel.analyzer.embedded.symbols import collect_symbols
from archkeel.analyzer.embedded.violations import (
    _AMBIGUOUS,
    _boundary_type_verdict,
    _typing_wrapper_inner,
    boundary_type_indexes,
)


def _module(source: str) -> ParsedModule:
    parsed = ParsedModule(
        path=Path("sample.py"),
        rel_path="sample.py",
        module="sample",
        package="sample",
        source=source,
        source_bytes=source.encode(),
        lines=source.splitlines(),
        tree=ast.parse(source),
    )
    parsed.aliases["TypeAlias"] = AliasBinding("typing.TypeAlias", "import", "TypeAlias")
    parsed.aliases["Annotated"] = AliasBinding("typing.Annotated", "import", "Annotated")
    return parsed


def test_explicit_type_alias_and_static_literal_constants_are_recorded() -> None:
    symbols, _, _ = collect_symbols(
        [
            _module(
                "from typing import Annotated, TypeAlias\n"
                "Payload: TypeAlias = dict\n"
                "Reference = Annotated[Payload, object()]\n"
                "Reference = factory()\n"
                'STATUS = "ready"\n'
                "DYNAMIC = factory()\n"
            )
        ],
        {},
    )
    aliases = {
        item["data"]["name"]: item["data"]["alias"]
        for item in symbols
        if item["kind"] == "type_alias"
    }
    constants = [item["data"]["constant"] for item in symbols if item["kind"] == "static_constant"]
    assert aliases == {"Payload": "dict", "Reference": "Annotated[Payload, object()]"}
    assert constants == ["ready"]
    _, by_name = boundary_type_indexes(symbols, [])
    assert by_name[("sample", "Reference")] is _AMBIGUOUS


def test_annotated_reads_only_its_type_argument() -> None:
    imports = {("sample", "Annotated"): {"target_module": "typing", "symbol": "Annotated"}}
    assert (
        _typing_wrapper_inner(
            "Annotated[dict, MustNotExecute()]", "sample", imports, {}, "Annotated"
        )
        == "dict"
    )


def test_literal_accepts_a_statically_recorded_constant() -> None:
    imports = {("sample", "Literal"): {"target_module": "typing", "symbol": "Literal"}}
    constants = {
        ("sample", "STATUS"): {
            "record_kind": "static_constant",
            "constant": "ready",
        }
    }
    assert _typing_wrapper_inner("Literal[STATUS]", "sample", imports, constants, "Literal") == (
        "STATUS",
    )


def test_literal_does_not_guess_an_enum_member_or_dynamic_constant() -> None:
    imports = {("sample", "Literal"): {"target_module": "typing", "symbol": "Literal"}}
    assert _typing_wrapper_inner("Literal[State.READY]", "sample", imports, {}, "Literal") is None
    unknown = _boundary_type_verdict("Literal[STATUS]", "sample", None, {}, imports, {})
    assert unknown.undecidable == "other"
    builtin = _boundary_type_verdict("Literal[str]", "sample", None, {}, imports, {})
    assert builtin.undecidable == "other"


def test_literal_rejects_unsupported_static_expression_shapes_as_unknown() -> None:
    imports = {("sample", "Literal"): {"target_module": "typing", "symbol": "Literal"}}
    for annotation in ("Literal[-1]", "Literal[b'payload']"):
        verdict = _boundary_type_verdict(annotation, "sample", None, {}, imports, {})
        assert verdict.violation is None and verdict.undecidable is not None


def test_ambiguous_typing_wrapper_binding_stays_unknown() -> None:
    imports = {("sample", "Annotated"): {"target_module": "typing", "symbol": "Annotated"}}
    local = {("sample", "Annotated"): {"record_kind": "static_constant"}}
    assert (
        _typing_wrapper_inner("Annotated[dict, metadata]", "sample", imports, local, "Annotated")
        is None
    )


def test_annotated_alias_cycle_is_unknown_and_wrapper_does_not_hide_violation() -> None:
    module = "sample.app.impl"
    imports = {
        (module, "Annotated"): {"target_module": "typing", "symbol": "Annotated"},
    }
    cyclic_alias = {
        (module, "Alias"): {
            "record_kind": "type_alias",
            "module": module,
            "name": "Alias",
            "alias": "Annotated[Alias, object()]",
        }
    }
    cycle = _boundary_type_verdict("Alias", module, None, {}, imports, cyclic_alias)
    assert cycle.undecidable == "other"

    wrapped_union = {
        (module, "Alias"): {
            "record_kind": "type_alias",
            "module": module,
            "name": "Alias",
            "alias": "Annotated[dict | Missing, object()]",
        }
    }
    violation = _boundary_type_verdict("Alias", module, None, {}, imports, wrapped_union)
    assert violation.violation is not None and "instead of a typed model" in violation.violation
