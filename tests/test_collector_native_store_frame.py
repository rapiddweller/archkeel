# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-346: the compact `W` frame of the shell (`ir/codec_store.py:_shell_frame`).

Consumer: the Rust store (`native/store/src/shell.rs`). Its test copy of the encoder writes
`native/store/testdata/canonical-frame.json`; the Python encoder must give the same rows, and a
row must read back as the record it came from, whatever its texts look like.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from archkeel.ir.codec_store import _shell_frame
from archkeel.ir.facts import RECORD_FIELDS
from archkeel.ir.model import CLASSIFIED_SECTIONS

TESTDATA = Path(__file__).parents[1] / "native/store/testdata"


def _value(cell: Any, texts: list[str]) -> Any:
    """The reading of one cell by `shell.rs`."""
    if isinstance(cell, bool) or cell is None:
        assert cell is None, cell
        return None
    if isinstance(cell, int):
        return texts[cell]
    if isinstance(cell, list):
        return [_value(item, texts) for item in cell]
    ((tag, inner),) = cell.items()
    assert tag in {"n", "b", "o"}, cell
    return {key: _value(item, texts) for key, item in inner.items()} if tag == "o" else inner


def _records(frame: dict[str, Any]) -> dict[str, list[Any]]:
    """The records of each section as `shell.rs` builds them back; a stored id stays an id."""
    texts, head = frame["texts"], RECORD_FIELDS[:-1]
    sections: dict[str, list[Any]] = {}
    for name in CLASSIFIED_SECTIONS:
        rows, fields = frame["model"][name], frame["fields"].get(name, [])
        if not isinstance(rows, list):
            continue
        sections[name] = []
        for row in rows:
            if isinstance(row, str):
                sections[name].append(row)
                continue
            assert len(row) == len(head) + len(fields)
            record = {key: _value(cell, texts) for key, cell in zip(head, row, strict=False)}
            cells = zip(fields, row[len(head) :], strict=True)
            record["data"] = {
                key: _value(cell, texts) for key, cell in cells if cell != {"m": True}
            }
            sections[name].append(record)
    return sections


def test_the_python_frame_has_the_rows_of_the_rust_copy() -> None:
    parts = json.loads((TESTDATA / "canonical-parts.json").read_text(encoding="utf-8"))
    committed = json.loads((TESTDATA / "canonical-frame.json").read_text(encoding="utf-8"))
    frame = _shell_frame(copy.deepcopy(parts["model"]))
    assert frame["fields"] == committed["fields"]
    assert _records(frame) == _records(committed)


def test_a_row_reads_back_as_its_record_whatever_its_texts_look_like() -> None:
    hostile = [
        "$0",
        "$m",
        "$$m",
        "$$12",
        "",
        "0",
        "true",
        "null",
        '{"n": 1}',
        "\N{LINE SEPARATOR}",
        "é" * 9,
    ]
    record = {
        "id": "$1",
        "evidence_class": "FACT",
        "area": "",
        "kind": "m",
        "title": "\x00 nul",
        "subjects": hostile,
        "evidence_ids": [],
        "rule_ids": ["b"],
        "fact_ids": ["n", "o"],
        "provenance": [],
        "data": {
            "m": True,
            "n": {"n": 1, "b": False, "o": {"m": None}},
            "texts": hostile,
            "numbers": [0, -1, 2.5, 10**20],
        },
    }
    model: dict[str, Any] = {name: None for name in CLASSIFIED_SECTIONS}
    model["metrics"] = [copy.deepcopy(record), "METRIC-stored", {**record, "data": {}}]
    frame = _shell_frame(model)
    assert json.loads(json.dumps(frame)) == frame
    assert _records(frame)["metrics"] == [record, "METRIC-stored", {**record, "data": {}}]


def test_the_frame_pieces_join_to_the_bytes_of_one_json_dump() -> None:
    from archkeel.analyzer.store import _pieces

    rows = [[index, {"n": index}, None, [index, "é"]] for index in range(25_001)]
    frame = {
        "texts": ["$m", "\N{LINE SEPARATOR}"],
        "fields": {"metrics": []},
        "model": {
            "metrics": rows,
            "evidence": [],
            "coverage": {"files_read": 3, "ok": True, "ratio": 0.5, "none": None},
        },
    }
    joined = b"".join(_pieces(frame))
    assert joined == json.dumps(frame, ensure_ascii=False, separators=(",", ":")).encode()
