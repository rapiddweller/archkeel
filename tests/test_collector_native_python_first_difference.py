# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The helper that compares two replies shows the first difference and stays short."""

from __future__ import annotations

import pytest
from first_difference import same


def test_a_difference_at_the_start_shows_the_start_of_both_texts() -> None:
    with pytest.raises(pytest.fail.Exception) as failed:
        same("a" + "x" * 5000, "b" + "x" * 5000, "label")
    message = str(failed.value)
    assert "native 'a" in message
    assert "python 'b" in message


def test_two_texts_of_several_megabytes_give_a_short_message() -> None:
    text = "y" * 4_000_000
    with pytest.raises(pytest.fail.Exception) as failed:
        same(text + "1", text + "2", "label")
    assert len(str(failed.value)) < 500


def test_equal_texts_pass() -> None:
    same("z" * 100, "z" * 100, "label")
