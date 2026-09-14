# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from codekeel.ir.codec import parse_measurements
from codekeel.ir.measurements import Measurements, RatchetScalars


def test_source_has_no_untyped_module_boundaries_or_product_namespace() -> None:
    source = Path(__file__).parents[1] / "src"
    pattern = re.compile(r"dict\[str, Any\]|Mapping\[str, Any\]|: Any\b")
    raw_record_owners = ("codekeel/ir/codec.py", "codekeel/producer/embedded/")
    hits = []
    namespace_hits = []
    for path in sorted(source.rglob("*.py")):
        for line, text in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(text) and not path.relative_to(source).as_posix().startswith(
                raw_record_owners
            ):
                hits.append(f"{path}:{line}:{text}")
            if "datamimic" in text.lower():
                namespace_hits.append(f"{path}:{line}:{text}")
    assert hits == []
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
