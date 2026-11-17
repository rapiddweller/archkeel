# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1614: gaps of one kind with different causes show each cause with its count and one example.

A group that names the example of its first gap misleads the reader when the members have
different causes. The text groups by cause, shows the three largest, and counts the rest.
"""

import pytest
from test_cli_text_output import _many_gaps, _run, environment  # noqa: F401


def _by_causes(counts: dict[str, int]) -> dict:
    """A frame whose source gaps have the given reasons, in the given numbers."""
    document = _many_gaps(sum(counts.values()))
    reasons = [reason for reason, number in counts.items() for _ in range(number)]
    for gap, reason in zip(document["collection_gaps"], reasons, strict=True):
        gap["kind"] = "source_resolution_gap"
        gap["reason"] = reason
    return document


def test_a_kind_with_several_causes_names_the_three_largest_with_one_example_each(
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = _by_causes(
        {
            "Local alias runtime conditions are not proven: @app/core": 30,
            "Unresolved module: react": 20,
            "dynamic_import: importlib.util": 5,
            "A form that can write any global keeps every free standard name": 3,
            "A fifth cause": 1,
        }
    )
    _, text = _run(document, ["validate", "--text"], capsys)
    assert "59 x a name or import that the scan cannot resolve, in 5 causes:" in text
    assert "30 x Local alias runtime conditions are not proven" in text
    assert "e.g. Local alias runtime conditions are not proven: @app/core (src/m1.py:1)" in text
    assert "20 x Unresolved module" in text and "5 x " in text
    # the fourth and fifth cause are counted, not listed
    assert "and 2 more causes (--all lists them)" in text
    assert "3 x A form that can write any global" not in text
    # the title never takes the example of the first gap for the whole group
    assert "cannot resolve: Local alias" not in text


def test_next_names_the_causes_and_not_the_kind(capsys: pytest.CaptureFixture[str]) -> None:
    document = _by_causes({"Unresolved module: a": 40, "dynamic_import: b": 10})
    _, text = _run(document, ["validate", "--text"], capsys)
    next_line = next(line for line in text.splitlines() if line.startswith("Next:"))
    assert "40 x Unresolved module" in next_line and "10 x dynamic_import" in next_line


def test_all_lists_every_cause_with_every_place(capsys: pytest.CaptureFixture[str]) -> None:
    document = _by_causes({"Unresolved module: a": 5, "dynamic_import: b": 4, "other": 1})
    _, text = _run(document, ["validate", "--text", "--all"], capsys)
    assert "more causes" not in text and "src/m10.py:10" in text and "1 x other" in text


def test_one_cause_keeps_the_known_form(capsys: pytest.CaptureFixture[str]) -> None:
    document = _by_causes({"Unresolved module: a": 8})
    _, text = _run(document, ["validate", "--text"], capsys)
    assert "8 x a name or import that the scan cannot resolve: Unresolved module: a" in text
    assert "causes:" not in text
