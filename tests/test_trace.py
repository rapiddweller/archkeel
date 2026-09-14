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
