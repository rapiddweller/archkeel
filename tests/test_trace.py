# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# DATAMIMIC
# Copyright (c) 2023-2026 Rapiddweller Asia Co., Ltd.

from __future__ import annotations

import pytest
from test_model import _model as _base_model

from archkeel.ir.codec import parse_observation
from archkeel.ir.trace import trace_valid_violations


def _model(trace_valid: bool) -> dict[str, object]:
    model = _base_model()
    if not trace_valid:
        model["imports"][0]["evidence_ids"] = []
    return model


@pytest.mark.parametrize(
    ("trace_valid", "expected_exit"),
    [(True, 1), (False, 2)],
)
def test_report_enforce_fails_closed_before_enforcing_trace_valid_violations(
    trace_valid: bool, expected_exit: int
) -> None:
    actual = len(trace_valid_violations(parse_observation(_model(trace_valid))))
    assert actual == (1 if expected_exit == 1 else 0)


@pytest.mark.parametrize(
    ("position", "excerpt", "traced"),
    [
        ((1, 1, 0), "import sample", True),
        # A cited line must show its text: an import line with nothing on it proves nothing.
        ((1, 1, 0), "", False),
        ((3, 3, 4), "", False),
        # AD-107: line 0 cites the file itself, what a module's existence rests on.
        ((0, 0, 0), "", True),
        ((0, 0, 0), "import sample", False),
        ((0, 1, 0), "", False),
    ],
)
def test_only_a_cited_file_may_have_no_excerpt(
    position: tuple[int, int, int], excerpt: str, traced: bool
) -> None:
    model = _model(trace_valid=True)
    line, end_line, column = position
    model["evidence"][0].update(line=line, end_line=end_line, column=column, excerpt=excerpt)
    assert len(trace_valid_violations(parse_observation(model))) == int(traced)
