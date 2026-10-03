# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Static annotation forms used by boundary_types."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from archkeel.analyzer.python.source import AliasBinding, ParsedModule
from archkeel.analyzer.python.symbols import collect_symbols
from archkeel.analyzer.python.type_shapes import collect_type_shapes
from archkeel.check.evaluation.rules import (
    _AMBIGUOUS,
    BindingIndex,
    _bare_type_verdict,
    _boundary_type_verdict,
    _typing_wrapper_inner,
    boundary_type_indexes,
)
from archkeel.ir.model import ArchitectureContract, ComponentRole, ContractComponent
from archkeel.ir.type_shapes import TypeShapeIndex


def _shape_facts(annotation: str, bindings: BindingIndex) -> TypeShapeIndex:
    expressions = [annotation]
    for binding in bindings.values():
        if not isinstance(binding, dict):
            continue
        if "alias" in binding:
            expressions.append(binding["alias"])
        expressions.extend(field["annotation"] for field in binding.get("fields", ()))
    return collect_type_shapes(expressions)


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


def test_builtin_rebinding_emits_one_symbol_record() -> None:
    symbols, _, _ = collect_symbols([_module("Exception = factory()\n")], {})

    bindings = [item for item in symbols if item["data"].get("name") == "Exception"]
    assert len(bindings) == 1
    assert bindings[0]["data"].get("record_kind") == "dynamic_binding"


def test_repeated_builtin_target_in_one_statement_emits_one_symbol_record() -> None:
    symbols, _, _ = collect_symbols([_module("dict, dict = object, object\n")], {})

    bindings = [item for item in symbols if item["data"].get("name") == "dict"]
    assert len(bindings) == 1
    assert bindings[0]["data"].get("record_kind") == "dynamic_binding"


def test_match_capture_binding_keeps_its_source_location() -> None:
    evidence = {}
    symbols, _, _ = collect_symbols(
        [_module('match subject:\n    case {"value": dict}:\n        pass\n')], evidence
    )

    [binding] = [item for item in symbols if item["data"].get("name") == "dict"]
    [evidence_id] = binding["evidence_ids"]
    assert evidence[evidence_id]["line"] == 2


def test_conditional_builtin_type_alias_is_a_dynamic_binding() -> None:
    symbols, _, _ = collect_symbols([_module("if condition:\n    dict: TypeAlias = str\n")], {})

    [binding] = [item for item in symbols if item["data"].get("name") == "dict"]
    assert binding["data"].get("record_kind") == "dynamic_binding"


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 requires Python 3.12")
def test_pep695_builtin_type_aliases_keep_direct_and_conditional_bindings_distinct() -> None:
    symbols, _, _ = collect_symbols(
        [_module("type dict = Hidden\nif condition:\n    type int = Hidden\n")], {}
    )

    bindings = {item["data"]["name"]: item["data"]["record_kind"] for item in symbols}
    assert bindings["dict"] == "type_alias"
    assert bindings["int"] == "dynamic_binding"


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 requires Python 3.12")
@pytest.mark.parametrize(
    ("source", "annotation", "record_kind"),
    (
        ("type dict = Hidden\n", "dict[str, str]", "type_alias"),
        ("if condition:\n    type dict = Hidden\n", "dict[str, str]", "dynamic_binding"),
        ("if condition:\n    type int = Hidden\n", "int", "dynamic_binding"),
    ),
)
def test_pep695_builtin_aliases_are_unknown_not_builtin_proof(
    source: str, annotation: str, record_kind: str
) -> None:
    symbols, _, _ = collect_symbols([_module(source)], {})
    imports, bindings = boundary_type_indexes(symbols, [])

    [binding] = [item for item in symbols if item["data"].get("name") in {"dict", "int"}]
    verdict = _boundary_type_verdict(
        annotation,
        "sample",
        None,
        {},
        imports,
        bindings,
        type_shapes=_shape_facts(annotation, bindings),
    )
    assert binding["data"].get("record_kind") == record_kind
    assert verdict.violation is None
    assert verdict.undecidable is not None


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 requires Python 3.12")
@pytest.mark.parametrize(
    ("source", "annotation"),
    (
        ("type Payload[T] = int\n", "Payload"),
        ("type dict[T] = Hidden\n", "dict[str, str]"),
    ),
    ids=("non-builtin-alias", "builtin-shadow"),
)
def test_parameterized_pep695_aliases_are_unknown_without_a_type_parameter_resolver(
    source: str, annotation: str
) -> None:
    symbols, _, _ = collect_symbols([_module(source)], {})
    imports, bindings = boundary_type_indexes(symbols, [])

    [binding] = symbols
    verdict = _boundary_type_verdict(
        annotation,
        "sample",
        None,
        {},
        imports,
        bindings,
        type_shapes=_shape_facts(annotation, bindings),
    )
    assert binding["data"].get("record_kind") == "dynamic_binding"
    assert verdict.violation is None
    assert verdict.undecidable is not None


def test_annotated_reads_only_its_type_argument() -> None:
    imports = {("sample", "Annotated"): {"target_module": "typing", "symbol": "Annotated"}}
    assert (
        _typing_wrapper_inner(
            "Annotated[dict, MustNotExecute()]",
            "sample",
            imports,
            {},
            "Annotated",
            type_shapes=collect_type_shapes(["Annotated[dict, MustNotExecute()]"]),
        )
        == "dict"
    )


def test_bare_dict_is_broad_only_when_its_builtin_binding_is_unshadowed() -> None:
    builtin = _bare_type_verdict(
        "dict", "sample", BindingIndex(), BindingIndex(), type_shapes=collect_type_shapes(["dict"])
    )
    assert builtin is not None and builtin.violation == "instead of a typed model"

    local_class = BindingIndex()
    local_class[("sample", "dict")] = {"record_kind": "class"}
    assert (
        _bare_type_verdict(
            "dict", "sample", BindingIndex(), local_class, type_shapes=collect_type_shapes(["dict"])
        )
        is None
    )

    import_alias = BindingIndex()
    import_alias[("sample", "dict")] = {
        "target_module": "sample.types",
        "symbol": "Payload",
    }
    assert (
        _bare_type_verdict(
            "dict",
            "sample",
            import_alias,
            BindingIndex(),
            type_shapes=collect_type_shapes(["dict"]),
        )
        is None
    )

    rebound = BindingIndex()
    rebound[("sample", "dict")] = {"record_kind": "dynamic_binding"}
    ambiguous = _bare_type_verdict(
        "dict", "sample", import_alias, rebound, type_shapes=collect_type_shapes(["dict"])
    )
    assert ambiguous is not None and ambiguous.undecidable == "ambiguous_binding"


def test_required_wrappers_resolve_only_proven_typing_imports() -> None:
    imports = {
        ("sample", "Required"): {
            "target_module": "typing_extensions",
            "symbol": "Required",
        },
        ("sample", "te"): {
            "target_module": "typing_extensions",
            "symbol": None,
        },
        ("sample", "NotRequired"): {
            "target_module": "typing",
            "symbol": "NotRequired",
        },
        ("sample", "NR"): {
            "target_module": "typing_extensions",
            "symbol": "NotRequired",
        },
    }
    for annotation in (
        "Required[int]",
        "NotRequired[int]",
        "te.Required[int]",
        "te.NotRequired[int]",
        "NR[int]",
    ):
        verdict = _boundary_type_verdict(
            annotation, "sample", None, {}, imports, {}, type_shapes=_shape_facts(annotation, {})
        )
        assert verdict.violation is None and verdict.undecidable is None

    broad = _boundary_type_verdict(
        "Required[dict]",
        "sample",
        None,
        {},
        imports,
        {},
        type_shapes=_shape_facts("Required[dict]", {}),
    )
    assert broad.violation == "instead of a typed model"
    any_type = _boundary_type_verdict(
        "Required[Any]",
        "sample",
        None,
        {},
        imports,
        {},
        type_shapes=_shape_facts("Required[Any]", {}),
    )
    assert any_type.violation is None and any_type.undecidable is not None
    unresolved = _boundary_type_verdict(
        "Required[Missing]",
        "sample",
        None,
        {},
        imports,
        {},
        type_shapes=_shape_facts("Required[Missing]", {}),
    )
    assert unresolved.violation is None and unresolved.undecidable is not None
    malformed = _boundary_type_verdict(
        "Required[int, str]",
        "sample",
        None,
        {},
        imports,
        {},
        type_shapes=_shape_facts("Required[int, str]", {}),
    )
    assert malformed.violation is None and malformed.undecidable is not None
    for annotation in ("Required[int,]", "NotRequired[(int,)]"):
        tuple_slice = _boundary_type_verdict(
            annotation, "sample", None, {}, imports, {}, type_shapes=_shape_facts(annotation, {})
        )
        assert tuple_slice.violation is None and tuple_slice.undecidable is not None


def test_required_lookalike_local_name_is_not_trusted() -> None:
    imports = {
        ("sample", "Required"): {
            "target_module": "typing_extensions",
            "symbol": "Required",
        }
    }
    local = {("sample", "Required"): {"record_kind": "static_constant"}}
    verdict = _boundary_type_verdict(
        "Required[int]",
        "sample",
        None,
        {},
        imports,
        local,
        type_shapes=_shape_facts("Required[int]", local),
    )
    assert verdict.violation is None and verdict.undecidable is not None


def test_literal_accepts_a_statically_recorded_constant() -> None:
    imports = {("sample", "Literal"): {"target_module": "typing", "symbol": "Literal"}}
    constants = {
        ("sample", "STATUS"): {
            "record_kind": "static_constant",
            "constant": "ready",
        }
    }
    assert _typing_wrapper_inner(
        "Literal[STATUS]",
        "sample",
        imports,
        constants,
        "Literal",
        type_shapes=collect_type_shapes(["Literal[STATUS]"]),
    ) == ("STATUS",)


def test_literal_does_not_guess_an_enum_member_or_dynamic_constant() -> None:
    imports = {("sample", "Literal"): {"target_module": "typing", "symbol": "Literal"}}
    assert _typing_wrapper_inner(
        "Literal[State.READY]",
        "sample",
        imports,
        {},
        "Literal",
        type_shapes=collect_type_shapes(["Literal[State.READY]"]),
    ) == ("State.READY",)
    member = _boundary_type_verdict(
        "Literal[State.READY]",
        "sample",
        None,
        {},
        imports,
        {},
        type_shapes=_shape_facts("Literal[State.READY]", {}),
    )
    assert member.violation is None and member.undecidable is not None
    unknown = _boundary_type_verdict(
        "Literal[STATUS]",
        "sample",
        None,
        {},
        imports,
        {},
        type_shapes=_shape_facts("Literal[STATUS]", {}),
    )
    assert unknown.undecidable == "other"
    builtin = _boundary_type_verdict(
        "Literal[str]",
        "sample",
        None,
        {},
        imports,
        {},
        type_shapes=_shape_facts("Literal[str]", {}),
    )
    assert builtin.undecidable == "other"


def test_literal_rejects_unsupported_static_expression_shapes_as_unknown() -> None:
    imports = {("sample", "Literal"): {"target_module": "typing", "symbol": "Literal"}}
    for annotation in ("Literal[-1]", "Literal[b'payload']"):
        verdict = _boundary_type_verdict(
            annotation, "sample", None, {}, imports, {}, type_shapes=_shape_facts(annotation, {})
        )
        assert verdict.violation is None and verdict.undecidable is not None


def test_ambiguous_typing_wrapper_binding_stays_unknown() -> None:
    imports = {("sample", "Annotated"): {"target_module": "typing", "symbol": "Annotated"}}
    local = {("sample", "Annotated"): {"record_kind": "static_constant"}}
    assert (
        _typing_wrapper_inner(
            "Annotated[dict, metadata]",
            "sample",
            imports,
            local,
            "Annotated",
            type_shapes=collect_type_shapes(["Annotated[dict, metadata]"]),
        )
        is None
    )


def test_rebound_typing_dict_is_unknown_not_a_broad_type_violation() -> None:
    imports = {("sample", "Dict"): {"target_module": "typing", "symbol": "Dict"}}
    rebinding = {
        ("sample", "Dict"): {
            "record_kind": "dynamic_binding",
            "module": "sample",
            "name": "Dict",
        }
    }
    verdict = _boundary_type_verdict(
        "Dict[str, str]",
        "sample",
        None,
        {},
        imports,
        rebinding,
        type_shapes=_shape_facts("Dict[str, str]", rebinding),
    )
    assert verdict.violation is None and verdict.undecidable == "ambiguous_binding"


def test_static_constant_is_not_a_type_alias() -> None:
    constants = {
        ("sample", "READY"): {
            "record_kind": "static_constant",
            "constant": "ready",
        }
    }
    verdict = _boundary_type_verdict(
        "READY", "sample", None, {}, {}, constants, type_shapes=_shape_facts("READY", constants)
    )
    assert verdict.violation is None and verdict.undecidable == "other"


def test_alias_preserves_nested_violation_and_unknown_coordinates() -> None:
    contract = ArchitectureContract(
        schema_version="2.1.0",
        components=(
            ContractComponent(
                id="app",
                label="app",
                role=ComponentRole.COMPONENT,
                packages=("sample",),
                responsibilities=(),
                forbidden_responsibilities=(),
                provenance=(),
                public=("sample:Request",),
            ),
        ),
        rules=(),
    )
    alias = BindingIndex()
    alias.update(
        {
            ("sample", "RequestAlias"): {
                "record_kind": "type_alias",
                "alias": "Request",
            },
            ("sample", "Request"): {
                "record_kind": "class",
                "class_kind": "model",
                "fields": [{"name": "payload", "annotation": "dict[str, str]"}],
            },
        }
    )
    violation = _boundary_type_verdict(
        "RequestAlias",
        "sample",
        contract,
        {},
        BindingIndex(),
        alias,
        type_shapes=_shape_facts("RequestAlias", alias),
    )
    assert violation.violation == "instead of a typed model"
    assert violation.path == ("payload",)
    assert violation.nested_annotation == "dict[str, str]"
    assert violation.violations == (
        ("instead of a typed model", ("payload",), "dict[str, str]", 0),
    )

    alias[("sample", "Request")]["fields"] = [{"name": "payload", "annotation": "Unresolved"}]
    unknown = _boundary_type_verdict(
        "RequestAlias",
        "sample",
        contract,
        {},
        BindingIndex(),
        alias,
        type_shapes=_shape_facts("RequestAlias", alias),
    )
    assert unknown.undecidable == "unresolved_name"
    assert unknown.path == ("payload",)
    assert unknown.nested_annotation == "Unresolved"


def test_annotated_alias_cycle_is_unknown_and_wrapper_does_not_hide_violation() -> None:
    module = "sample.app.impl"
    imports = {
        (module, "Annotated"): {"target_module": "typing", "symbol": "Annotated"},
    }
    cyclic_alias = BindingIndex()
    cyclic_alias.update(
        {
            (module, "Alias"): {
                "record_kind": "type_alias",
                "module": module,
                "name": "Alias",
                "alias": "Annotated[Alias, object()]",
            }
        }
    )
    cycle = _boundary_type_verdict(
        "Alias",
        module,
        None,
        {},
        imports,
        cyclic_alias,
        type_shapes=_shape_facts("Alias", cyclic_alias),
    )
    assert cycle.undecidable == "other"

    wrapped_union = BindingIndex()
    wrapped_union.update(
        {
            (module, "Alias"): {
                "record_kind": "type_alias",
                "module": module,
                "name": "Alias",
                "alias": "Annotated[dict | Missing, object()]",
            }
        }
    )
    violation = _boundary_type_verdict(
        "Alias",
        module,
        None,
        {},
        imports,
        wrapped_union,
        type_shapes=_shape_facts("Alias", wrapped_union),
    )
    assert violation.violation is not None and "instead of a typed model" in violation.violation
