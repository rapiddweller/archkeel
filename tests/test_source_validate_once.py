# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-338: the host validates a decoded collection once and keeps no proof for other facts."""

import ast
import dataclasses
import enum
import re
import types
import typing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from test_source_evaluation import _facts

from archkeel.check.evaluation.evaluate import evaluate_source
from archkeel.ir import facts_validation, reference_context, validated_facts
from archkeel.ir.codec import parse_contract
from archkeel.ir.facts import SourceFacts, SourceReferenceContext
from archkeel.ir.facts_codec import ProtocolError

_EMPTY_CONTRACT = {"schema_version": "2.1.0", "components": [], "rules": []}


def _evaluate(facts: SourceFacts) -> None:
    evaluate_source(facts, parse_contract(_EMPTY_CONTRACT), roots=("src",), namespace="project")


def _counted():
    return patch.object(
        validated_facts, "validate_source_facts", wraps=facts_validation.validate_source_facts
    )


def _invalid(facts: SourceFacts) -> SourceFacts:
    return replace(facts, coverage=replace(facts.coverage, files_parsed=999))


def test_decoded_facts_are_validated_once_for_any_number_of_evaluations() -> None:
    with _counted() as counted:
        facts = _facts()
        for _ in range(3):
            _evaluate(facts)
    assert counted.call_count == 1


def test_facts_that_a_caller_builds_are_validated_at_each_evaluation() -> None:
    built = replace(_facts())
    with _counted() as counted:
        _evaluate(built)
        _evaluate(built)
    assert counted.call_count == 2


def test_an_invalid_caller_built_fact_fails_each_time() -> None:
    bad = _invalid(_facts())
    for _ in range(2):
        with pytest.raises(ProtocolError, match="impossible collection coverage counts"):
            _evaluate(bad)


def test_a_changed_copy_of_decoded_facts_has_no_proof() -> None:
    facts = _facts()
    _evaluate(facts)
    assert validated_facts.is_decoded(facts)
    changed = _invalid(facts)
    assert not validated_facts.is_decoded(changed)
    # The copy shares every other part with the proven object: sharing proves nothing.
    assert changed.files is facts.files
    with pytest.raises(ProtocolError, match="impossible collection coverage counts"):
        _evaluate(changed)


def test_the_proof_is_dropped_with_the_facts() -> None:
    facts = _facts()
    key = id(facts)
    assert key in validated_facts._DECODED
    del facts
    assert key not in validated_facts._DECODED


def test_only_the_decoder_records_a_proof() -> None:
    src = Path(__file__).parents[1] / "src" / "archkeel"
    users = {
        path.relative_to(src).as_posix()
        for path in src.rglob("*.py")
        if re.search(r"\bvalidate_decoded_facts\b", path.read_text("utf-8"))
    }
    assert users == {"ir/facts_codec.py", "ir/validated_facts.py", "analyzer/process.py"}
    # AD-394: the process decoder validates the new object after it attaches host metadata.
    tree = ast.parse((src / "analyzer/process.py").read_text("utf-8"))
    owners = {
        function.name
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef)
        and any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "validate_decoded_facts"
            for node in ast.walk(function)
        )
    }
    assert owners == {"_decode_response"}


_SCALARS = (str, int, float, bool, bytes, type(None))
_FROZEN_CONTAINERS = (tuple, frozenset)


def _assert_frozen_type(hint: object, seen: set[type]) -> None:
    """Accept only scalars, enums, tuples, frozensets and frozen dataclasses, all the way down."""
    if hint is Ellipsis or isinstance(hint, str):
        return  # tuple[X, ...] marker, and a Literal value
    if isinstance(hint, typing.ForwardRef):
        # The one recursive alias: JsonValue = str | ... | tuple[JsonValue, ...] | RecordData.
        assert hint.__forward_arg__ == "JsonValue", f"unknown reference {hint}"
        return
    origin = typing.get_origin(hint)
    if origin is typing.Literal:
        return
    if origin is not None:
        assert origin in {*_FROZEN_CONTAINERS, typing.Union, types.UnionType}, f"mutable {hint}"
        for argument in typing.get_args(hint):
            _assert_frozen_type(argument, seen)
        return
    assert isinstance(hint, type), f"unknown annotation {hint!r}"
    if hint in _SCALARS or issubclass(hint, enum.Enum):
        return
    assert dataclasses.is_dataclass(hint), f"not an allowed type: {hint}"
    assert hint.__dataclass_params__.frozen, f"not frozen: {hint}"  # type: ignore[attr-defined]
    if hint in seen:
        return
    seen.add(hint)
    for field_hint in typing.get_type_hints(hint).values():
        _assert_frozen_type(field_hint, seen)


def test_source_facts_are_frozen_all_the_way_down() -> None:
    seen: set[type] = set()
    _assert_frozen_type(SourceFacts, seen)
    assert len(seen) > 20


@dataclasses.dataclass(frozen=True)
class _ListProbe:
    items: list[int]


@dataclasses.dataclass(frozen=True)
class _ObjectProbe:
    item: object


@dataclasses.dataclass(frozen=True)
class _DictInTupleProbe:
    items: tuple[dict[str, int], ...]


@dataclasses.dataclass
class _ThawedProbe:
    item: int


@pytest.mark.parametrize("probe", [_ListProbe, _ObjectProbe, _DictInTupleProbe, _ThawedProbe])
def test_the_frozen_type_check_rejects_a_mutable_field(probe: type) -> None:
    with pytest.raises(AssertionError):
        _assert_frozen_type(probe, set())


_ANNOTATED = "def f(x: Foo, y=Foo): pass"


def test_reference_context_depends_on_each_input() -> None:
    annotation = reference_context.source_reference_context(
        _ANNOTATED, _ANNOTATED.index("Foo"), "Foo"
    )
    value = reference_context.source_reference_context(_ANNOTATED, _ANNOTATED.rindex("Foo"), "Foo")
    other = reference_context.source_reference_context(_ANNOTATED, _ANNOTATED.index("Foo"), "Bar")
    assert annotation is SourceReferenceContext.ANNOTATION
    assert value is SourceReferenceContext.VALUE
    assert other is None


def test_reference_context_is_remembered_by_value_and_returns_only_an_enum_or_none() -> None:
    function = reference_context._remembered_context
    function.cache_clear()
    column = _ANNOTATED.index("Foo")
    # "".join(...) builds a new string object with the same value: the cache must key on value.
    first = function("".join(_ANNOTATED), column, "Foo")
    second = function("".join(_ANNOTATED), column, "Foo")
    assert first is second
    assert function.cache_info().hits == 1
    assert isinstance(first, SourceReferenceContext)
    assert function.cache_info().maxsize == reference_context.REFERENCE_CONTEXT_CACHE_SIZE
    assert function(_ANNOTATED, 10_000, "Foo") is None


def test_a_long_excerpt_is_computed_and_never_pinned() -> None:
    function = reference_context._remembered_context
    function.cache_clear()
    limit = reference_context.REFERENCE_CONTEXT_CACHE_MAX_CHARS
    excerpt = f"def f(x: Foo, y={'0 + ' * limit}0): pass"
    assert len(excerpt) > limit
    column = excerpt.index("Foo")
    verdict = reference_context.source_reference_context(excerpt, column, "Foo")
    assert verdict is SourceReferenceContext.ANNOTATION
    long_name = "N" * (limit + 1)
    reference_context.source_reference_context(f"x: {long_name}", 3, long_name)
    assert function.cache_info().currsize == 0


def test_a_verdict_that_came_from_a_recursion_error_is_not_remembered() -> None:
    function = reference_context._remembered_context
    function.cache_clear()
    column = _ANNOTATED.index("Foo")
    real_parse = ast.parse
    calls = []

    def deep_once(source, *args, **kwargs):
        calls.append(source)
        if len(calls) == 1:
            raise RecursionError("the caller is deep")
        return real_parse(source, *args, **kwargs)

    with patch.object(reference_context.ast, "parse", deep_once):
        first = reference_context.source_reference_context(_ANNOTATED, column, "Foo")
    assert first is SourceReferenceContext.ANNOTATION  # the verdict is returned, not kept
    assert function.cache_info().currsize == 0
    # The same call at a shallow depth gives the true verdict and is then remembered.
    second = reference_context.source_reference_context(_ANNOTATED, column, "Foo")
    assert second is SourceReferenceContext.ANNOTATION
    assert function.cache_info().currsize == 1
    assert reference_context.source_reference_context(_ANNOTATED, column, "Foo") is second
    assert function.cache_info().hits == 1
