# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The source value readers accept their shape, treat None as empty and refuse any other shape."""

import pytest

from archkeel.ir.facts import RecordData
from archkeel.ir.source_values import optional_text, record_array, text_array, vocabulary_text


def test_optional_text_reads_text_and_none_and_refuses_other_shapes() -> None:
    assert optional_text("a") == "a"
    assert optional_text(None) is None
    with pytest.raises(ValueError, match="source graph expected text"):
        optional_text(("a",))


def test_vocabulary_text_uses_the_default_for_none() -> None:
    assert vocabulary_text("a") == "a"
    assert vocabulary_text(None) == ""
    assert vocabulary_text(None, default="d") == "d"
    with pytest.raises(ValueError, match="source graph expected text"):
        vocabulary_text(("a",))


@pytest.mark.parametrize("wrong", ["a", ("a", RecordData(())), (1,)])
def test_text_array_refuses_a_wrong_shape(wrong: object) -> None:
    with pytest.raises(ValueError, match="source graph expected text array"):
        text_array(wrong)  # type: ignore[arg-type]


def test_text_array_reads_a_tuple_of_text_and_none_as_empty() -> None:
    assert text_array(("a", "b")) == ("a", "b")
    assert text_array(None) == ()
    assert text_array(()) == ()


@pytest.mark.parametrize("wrong", ["a", ("a",), (RecordData(()), "a")])
def test_record_array_refuses_a_wrong_shape(wrong: object) -> None:
    with pytest.raises(ValueError, match="source graph expected record array"):
        record_array(wrong)  # type: ignore[arg-type]


def test_record_array_reads_a_tuple_of_records_and_none_as_empty() -> None:
    row = RecordData((("k", "v"),))
    assert record_array((row,)) == (row,)
    assert record_array(None) == ()
    assert record_array(()) == ()
