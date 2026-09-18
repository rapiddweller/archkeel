# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from archkeel.ir.codec import parse_measurements
from archkeel.ir.measurements import Measurements, RatchetScalars


def test_source_has_no_product_namespace() -> None:
    """Where `Any` may appear is the contract's `CONSTRUCT-NO-ANY` rule (AD-41), not a test."""
    source = Path(__file__).parents[1] / "src"
    namespace_hits = []
    for path in sorted(source.rglob("*.py")):
        for line, text in enumerate(path.read_text().splitlines(), 1):
            if "datamimic" in text.lower():
                namespace_hits.append(f"{path}:{line}:{text}")
    assert namespace_hits == []


def test_measurements_are_frozen_at_both_levels() -> None:
    value = Measurements(RatchetScalars(0, 0, 0, 0, 0, 0), 0, "n/a")
    with pytest.raises(FrozenInstanceError):
        value.calls_total = 1
    with pytest.raises(FrozenInstanceError):
        value.scalars.calls_unresolved = 1
    assert (
        parse_measurements(
            {"scalars": dict(value.scalars.items()), "calls_total": 0, "resolution": "n/a"},
            "accepted",
        )
        == value
    )
