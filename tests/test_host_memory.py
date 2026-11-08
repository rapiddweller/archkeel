# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-324: the host writes large JSON in pieces and frees each copy as soon as it is made."""

import json
import tracemalloc
from io import BytesIO

import pytest

from archkeel.ir import codec_wire
from archkeel.ir.codec import (
    canonical_json_bytes,
    write_json,
)
from archkeel.ir.codec_strings import StringTablePolicy, intern_strings

_COMPACT = (",", ":")
_DEFAULT = (", ", ": ")


def _dumps(value: object, separators: tuple[str, str]) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=separators).encode()


def test_a_repeated_string_has_one_reference_object() -> None:
    text = "a repeated string that is long enough to be worth a table entry"
    tree, table = intern_strings(
        [[text], [text], [text], [text]], policy=StringTablePolicy.OBSERVATION
    )

    references = [row[0] for row in tree]

    assert table == [text]
    assert references == ["$0"] * 4
    assert len({id(reference) for reference in references}) == 1


_VALUES = [
    {"b": [1, 2.5, None, True], "a": {"z": "é→<", "y": []}, "c": {}},
    [{"k": index, "t": ("x", index)} for index in range(10)],
    {"rows": [{"id": index, "text": f"Zeile {index} →"} for index in range(25)], "n": (1, 2)},
    {"deep": {"deeper": {"deepest": {"bottom": {"x": list(range(9))}}}}},
    {1: "a", 2: ["b"] * 9},
    {"empty": [], "tuple": tuple(range(7)), "single": [0]},
]


@pytest.mark.parametrize("separators", [_COMPACT, _DEFAULT])
@pytest.mark.parametrize("value", _VALUES)
def test_json_in_pieces_equals_json_dumps(
    value: object, separators: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(codec_wire, "_LIST_PIECE", 3)
    out = BytesIO()

    write_json(out, value, separators=separators)

    assert out.getvalue() == _dumps(value, separators)
    assert codec_wire.json_bytes(value, separators=separators, tail=b"\n") == (
        _dumps(value, separators) + b"\n"
    )


def test_json_for_a_script_element_has_no_less_than_sign(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codec_wire, "_LIST_PIECE", 2)
    value = {"</script>": ["<b>", "<i>", "<u>", "ok"]}
    out = BytesIO()

    write_json(out, value, html_safe=True)

    assert out.getvalue() == _dumps(value, _COMPACT).replace(b"<", b"\\u003c")
    assert b"<" not in out.getvalue()


def test_json_in_pieces_peaks_near_the_size_of_its_output() -> None:
    value = {"rows": [{"id": index, "text": f"Zeile {index} → ß"} for index in range(60_000)]}
    size = len(_dumps(value, _COMPACT))
    tracemalloc.start()
    try:
        codec_wire.json_bytes(value, tail=b"\n")
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    # One text for the value holds two bytes for each character; with its copies it takes 5 times.
    assert peak < 2.5 * size


def test_canonical_bytes_equal_the_text_of_json_dumps() -> None:
    model = {"b": [{"é": 1}], "a": ("x", None)}

    assert canonical_json_bytes(model) == (_dumps(model, _COMPACT) + b"\n")
