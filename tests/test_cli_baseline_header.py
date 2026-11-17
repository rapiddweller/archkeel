# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1620: with a baseline, the header, `Next:` and the violation list say the same thing."""

import json

import pytest
from test_cli_core_only_boundary import frame
from test_cli_text_output import _baseline, _run, environment  # noqa: F401

from archkeel.cli.core_frame import Status


def _violations(count: int) -> dict:
    document = json.loads(frame(Status.FAIL))
    row = document["details"]["R1"][0]
    document["details"]["R1"] = [dict(row, source=f"app.m{n}") for n in range(count)]
    document["violations"] = {"R1": count}
    return document


def test_accepted_violations_are_not_asked_to_be_removed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = _violations(3)
    document["baseline"] = _baseline("current", 2, unknowns=5)
    _, text = _run(document, ["validate", "--baseline", "b.json", "--text"], capsys)
    first = text.splitlines()[0]
    assert "3 violations accepted by the baseline; 5 accepted items stay UNKNOWN" in first
    assert "remove the 3 violations" not in text
    assert "Violations accepted by the baseline (3):" in text


def test_new_violations_are_counted_apart_from_the_accepted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = _violations(3)
    document["baseline"] = _baseline("drift", 1, new=1)
    _, text = _run(document, ["validate", "--baseline", "b.json", "--text"], capsys)
    assert "remove the 1 new violations that the baseline does not accept" in text
    assert "Violations (3: 1 new, 2 accepted by the baseline):" in text


def test_without_a_baseline_the_old_words_stay(capsys: pytest.CaptureFixture[str]) -> None:
    _, text = _run(_violations(2), ["validate", "--text"], capsys)
    assert "remove the 2 violations" in text and "Violations (2):" in text


def test_a_repeated_line_is_one_line_with_a_count(capsys: pytest.CaptureFixture[str]) -> None:
    document = _violations(2)
    document["details"]["R1"][1] = dict(document["details"]["R1"][0])
    _, text = _run(document, ["validate", "--text"], capsys)
    assert text.count("R1: forbidden dependency: app.m0 -> app.b") == 1 and "(x2)" in text
