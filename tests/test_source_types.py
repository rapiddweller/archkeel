import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from pledge.ir.codec import parse_measurements
from pledge.ir.measurements import Measurements, RatchetScalars


def test_source_has_no_untyped_module_boundaries_or_product_namespace() -> None:
    source = Path(__file__).parents[1] / "src"
    pattern = re.compile(r"dict\[str, Any\]|Mapping\[str, Any\]|: Any\b")
    hits = []
    namespace_hits = []
    for path in sorted(source.rglob("*.py")):
        for line, text in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(text) and path.relative_to(source).as_posix() != "pledge/ir/codec.py":
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
