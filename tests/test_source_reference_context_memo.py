# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One validation run parses each reference excerpt once, and no run shares a memo with another."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import archkeel.ir.reference_contexts as reference_contexts
from archkeel.ir.facts import SourceProfile, SourceReferenceContext
from archkeel.ir.reference_contexts import (
    _reference_annotation_excerpt,
    _validate_reference_contexts,
    source_reference_context,
)

EXCERPT = "def f(a: X, b=X): pass"
ANNOTATION_COLUMN = EXCERPT.index("X")
VALUE_COLUMN = EXCERPT.rindex("X")


def _evidence(name: str, excerpt: str, column: int) -> Any:
    return SimpleNamespace(id=name, excerpt=excerpt, column=column)


def _reference(context: SourceReferenceContext, *evidence_ids: str, expression: str = "X") -> Any:
    return SimpleNamespace(
        kind="value_reference",
        evidence_ids=evidence_ids,
        data={"reference_context": context, "expression": expression},
    )


def _outcome(records: list[Any], evidence: dict[str, Any]) -> str:
    try:
        _validate_reference_contexts(records, evidence, SourceProfile.PYTHON)
    except ValueError as error:
        return str(error)
    return "ok"


def _count_parses(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    original = reference_contexts._reference_excerpt_tree

    def counting(excerpt: str) -> Any:
        calls.append(excerpt)
        return original(excerpt)

    monkeypatch.setattr(reference_contexts, "_reference_excerpt_tree", counting)
    return calls


def test_a_repeated_excerpt_parses_once_in_one_run(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = {"e1": _evidence("e1", EXCERPT, VALUE_COLUMN)}
    records = [_reference(SourceReferenceContext.VALUE, "e1") for _ in range(5)]
    calls = _count_parses(monkeypatch)
    assert _outcome(records, evidence) == "ok"
    assert calls == [EXCERPT]


def test_a_second_run_parses_again_so_no_memo_outlives_a_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = {"e1": _evidence("e1", EXCERPT, VALUE_COLUMN)}
    records = [_reference(SourceReferenceContext.VALUE, "e1")]
    calls = _count_parses(monkeypatch)
    _outcome(records, evidence)
    _outcome(records, evidence)
    assert calls == [EXCERPT, EXCERPT]


def test_the_memo_key_holds_excerpt_column_and_expression() -> None:
    memo: dict[Any, Any] = {}
    annotation = _evidence("a", EXCERPT, ANNOTATION_COLUMN)
    value = _evidence("v", EXCERPT, VALUE_COLUMN)
    reference = _reference(SourceReferenceContext.VALUE, "a")
    assert _reference_annotation_excerpt(reference, annotation, memo) is True
    assert _reference_annotation_excerpt(reference, value, memo) is False
    other = _reference(SourceReferenceContext.VALUE, "a", expression="Y")
    assert _reference_annotation_excerpt(other, annotation, memo) is None
    assert len(memo) == 3


def test_the_memo_keeps_only_immutable_verdicts() -> None:
    memo: dict[Any, Any] = {}
    for column in (ANNOTATION_COLUMN, VALUE_COLUMN, 0):
        _reference_annotation_excerpt(
            _reference(SourceReferenceContext.VALUE, "e"), _evidence("e", EXCERPT, column), memo
        )
    assert {type(value) for value in memo.values()} <= {SourceReferenceContext, type(None)}


CASES = (
    (SourceReferenceContext.ANNOTATION, ANNOTATION_COLUMN, "ok"),
    (SourceReferenceContext.ANNOTATION, VALUE_COLUMN, "annotation reference contradicts"),
    (SourceReferenceContext.VALUE, VALUE_COLUMN, "ok"),
    (SourceReferenceContext.VALUE, ANNOTATION_COLUMN, "value reference contradicts"),
    (SourceReferenceContext.VALUE, 0, "value reference lacks"),
    (SourceReferenceContext.ANNOTATION, 0, "annotation reference lacks"),
)


@pytest.mark.parametrize(("context", "column", "message"), CASES)
def test_a_memoized_run_gives_the_verdict_of_the_unmemoized_check(
    context: SourceReferenceContext, column: int, message: str
) -> None:
    evidence = {"e1": _evidence("e1", EXCERPT, column)}
    records = [_reference(context, "e1")]
    assert _outcome(records, evidence).startswith(message)
    plain = [_reference_annotation_excerpt(records[0], evidence["e1"]) for _ in range(2)]  # no memo
    memoized: dict[Any, Any] = {}
    shared = [_reference_annotation_excerpt(records[0], evidence["e1"], memoized) for _ in range(2)]
    assert plain == shared


def test_a_repeated_excerpt_does_not_hide_a_contradiction_after_a_good_record() -> None:
    evidence = {
        "good": _evidence("good", EXCERPT, VALUE_COLUMN),
        "bad": _evidence("bad", EXCERPT, ANNOTATION_COLUMN),
    }
    records = [
        _reference(SourceReferenceContext.VALUE, "good"),
        _reference(SourceReferenceContext.VALUE, "good"),
        _reference(SourceReferenceContext.VALUE, "bad"),
    ]
    assert (
        _outcome(records, evidence) == "value reference contradicts its annotated source occurrence"
    )


def test_the_collector_function_stays_a_pure_call_without_a_memo() -> None:
    assert source_reference_context(EXCERPT, VALUE_COLUMN, "X") is SourceReferenceContext.VALUE
    assert (
        source_reference_context(EXCERPT, ANNOTATION_COLUMN, "X")
        is SourceReferenceContext.ANNOTATION
    )
