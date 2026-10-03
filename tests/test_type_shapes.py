# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Type syntax crosses the adapter boundary without executable parser callbacks."""

import inspect

import pytest

from archkeel.analyzer.embedded import violations


def test_rule_evaluation_does_not_import_a_python_parser() -> None:
    source = inspect.getsource(violations)
    assert "import ast" not in source
    assert "analyzer.python" not in source


def test_collected_type_facts_retain_nested_syntax() -> None:
    from archkeel.analyzer.python.type_shapes import collect_type_shapes
    from archkeel.ir.type_shapes import (
        LiteralKind,
        TypeApplication,
        TypeLiteral,
        TypeMember,
        TypeName,
        TypeUnion,
        TypeUnpack,
        UnresolvedType,
    )

    facts = collect_type_shapes(
        [
            "typing.Mapping[ str , list[Payload | None]]",
            "Required[(int,)]",
            "tuple[*Ts, ...]",
            "str |",
            "f().member",
        ]
    )
    mapping = facts["typing.Mapping[ str , list[Payload | None]]"]
    assert isinstance(mapping, TypeApplication)
    assert mapping.head == TypeMember("typing.Mapping", TypeName("typing", "typing"), "Mapping")
    assert mapping.arguments[1].text == "list[Payload | None]"
    assert isinstance(facts["Payload | None"], TypeUnion)
    assert facts["None"] == TypeLiteral("None", LiteralKind.NONE)
    required = facts["Required[(int,)]"]
    assert isinstance(required, TypeApplication) and required.tuple_arguments
    assert isinstance(facts["*Ts"], TypeUnpack)
    assert facts["..."] == TypeLiteral("...", LiteralKind.ELLIPSIS)
    assert facts["str |"] == UnresolvedType("str |", valid_syntax=False)
    member = facts["f().member"]
    assert isinstance(member, TypeMember)
    assert member.owner == UnresolvedType("f()", valid_syntax=True)


def test_evaluation_uses_supplied_mapping_wrapper_union_and_generic_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ast

    from archkeel.analyzer.python.type_shapes import collect_type_shapes
    from archkeel.ir.model import ArchitectureContract
    from archkeel.ir.type_shapes import TypeApplication

    facts = collect_type_shapes(
        ["dict[str, list[int | None]]", "Required[dict[str, int]]", "int | str", "Base[int]"]
    )
    imports = violations.BindingIndex()
    imports[("sample", "Required")] = {"target_module": "typing", "symbol": "Required"}
    classes = violations.BindingIndex()

    def forbidden_parse(*args: object, **kwargs: object) -> None:
        raise AssertionError("Rule evaluation must not parse Python syntax")

    monkeypatch.setattr(ast, "parse", forbidden_parse)
    assert violations._mapping_parameters(
        "dict[str, list[int | None]]", "sample", imports, classes, type_shapes=facts
    ) == ["str", "list[int | None]"]
    assert (
        violations._typing_wrapper_inner(
            "Required[dict[str, int]]", "sample", imports, classes, "Required", type_shapes=facts
        )
        == "dict[str, int]"
    )
    assert violations._union_parameters("int | str", "sample", imports, type_shapes=facts) == [
        "int",
        "str",
    ]
    expression = facts["Base[int]"]
    assert isinstance(expression, TypeApplication)
    base = {"data": {"module": "sample", "generic_parameters": ["T"], "class_members": []}}
    contract = ArchitectureContract(schema_version="2.1.0", components=(), rules=())
    substituted = violations._public_api_generic_bindings(
        base, expression, "sample", contract, {}, imports, classes, type_shapes=facts
    )
    assert substituted is not None
    assert substituted[0][("sample", "T")]["target_module"] == "builtins"
    assert substituted[0][("sample", "T")]["symbol"] == "int"


@pytest.mark.parametrize(
    "annotation", ["list[(int | str)]", "list[ ((int | str)) ]", "list[(\n int | str \n)]"]
)
def test_parenthesized_collection_argument_keeps_its_union_fact(annotation: str) -> None:
    from archkeel.analyzer.python.type_shapes import collect_type_shapes
    from archkeel.ir.model import ArchitectureContract

    verdict = violations._boundary_type_verdict(
        annotation,
        "sample",
        ArchitectureContract(schema_version="2.1.0", components=(), rules=()),
        {},
        violations.BindingIndex(),
        violations.BindingIndex(),
        type_shapes=collect_type_shapes([annotation]),
    )
    assert verdict.undecidable is None
    assert verdict.violation is None
