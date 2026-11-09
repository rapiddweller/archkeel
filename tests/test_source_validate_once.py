# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-338: the host validates a decoded collection once and keeps no proof for other facts."""

import dataclasses
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
    assert users == {"ir/facts_codec.py", "ir/validated_facts.py"}


def _reachable_types(root: type) -> set[type]:
    seen: set[type] = set()
    todo = [root]
    while todo:
        current = todo.pop()
        if current in seen or not dataclasses.is_dataclass(current):
            continue
        seen.add(current)
        for hint in typing.get_type_hints(current).values():
            todo.extend(_leaf_types(hint))
    return seen


def _leaf_types(hint: object) -> list[type]:
    origin = typing.get_origin(hint)
    if origin is None:
        return [hint] if isinstance(hint, type) else []
    assert origin in {tuple, frozenset, typing.Literal, typing.Union, types.UnionType}, (
        f"mutable {hint}"
    )
    return [leaf for argument in typing.get_args(hint) for leaf in _leaf_types(argument)]


def test_source_facts_are_frozen_all_the_way_down() -> None:
    reachable = _reachable_types(SourceFacts)
    assert len(reachable) > 20
    for kind in reachable:
        assert kind.__dataclass_params__.frozen, kind  # type: ignore[attr-defined]


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
    function = reference_context.source_reference_context
    function.cache_clear()
    column = _ANNOTATED.index("Foo")
    first = function("".join(_ANNOTATED), column, "Foo")
    second = function("".join(_ANNOTATED), column, "Foo")
    assert first is second
    assert function.cache_info().hits == 1
    assert isinstance(first, SourceReferenceContext)
    assert function.cache_info().maxsize == reference_context.REFERENCE_CONTEXT_CACHE_SIZE
    assert function(_ANNOTATED, 10_000, "Foo") is None
