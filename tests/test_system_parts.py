# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-522: the parts of the system are in one document that the tools and the page follow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_report_product_page import _STUB, _frame, _visible

from tools import report_gallery
from tools.report_product import Part
from tools.report_product_page import product_page
from tools.system_parts import load


def _fake(tmp_path: Path, ids: list[str]) -> Path:
    parts = [{"id": i, "title": i.title(), "config": "native/archkeel.toml"} for i in ids]
    path = tmp_path / "system.json"
    path.write_text(json.dumps({"kind": "system", "title": "Demo", "parts": parts}))
    return path


@pytest.mark.parametrize(
    "document",
    [
        "[]",
        '{"kind": "other", "title": "x", "parts": [{"id": "a", "title": "A", "config": "c"}]}',
        '{"kind": "system", "title": "x", "parts": []}',
        '{"kind": "system", "title": "", "parts": [{"id": "a", "title": "A", "config": "c"}]}',
        '{"kind": "system", "title": "x", "parts": [{"id": "A b", "title": "A", "config": "c"}]}',
        '{"kind": "system", "title": "x", "parts": [{"id": "a", "title": "A", "config": "c"},'
        ' {"id": "a", "title": "B", "config": "c"}]}',
    ],
)
def test_a_bad_document_is_refused(tmp_path: Path, document: str) -> None:
    path = tmp_path / "s.json"
    path.write_text(document)
    with pytest.raises(ValueError):
        load(path)


def test_a_third_part_in_a_copy_of_the_document_is_a_third_card_and_the_weakest_verdict_wins(
    tmp_path: Path,
) -> None:
    system = load(_fake(tmp_path, ["one", "two", "three"]))
    assert system.name == "Demo (One + Two + Three)"
    parts = [
        Part(p.id, p.title, p.language, p.subject, f"{p.id}.html", status=s, counts=c)
        for p, s, c in zip(
            system.parts,
            ["PASS", "PASS", "UNKNOWN"],
            [
                {"PASS": 5, "FAIL": 0, "UNKNOWN": 0},
                {"PASS": 6, "FAIL": 0, "UNKNOWN": 0},
                {"PASS": 0, "FAIL": 0, "UNKNOWN": 2},
            ],
            strict=True,
        )
    ]
    page = product_page(system.name, parts, {p.key: frozenset() for p in parts}, "abc", "t")
    assert page.count('class="rp-part"') == 3
    text = _visible(page)
    assert "Demo (One + Two + Three): UNKNOWN" in text and "2 rules cannot be decided" in text
    assert ">11<" in page


def test_the_gallery_links_each_part_of_a_document_with_three_parts_and_each_links_back(
    tmp_path: Path,
) -> None:
    stub = tmp_path / "stub.py"
    stub.write_text(_STUB.replace("FRAME", repr(_frame())))
    out = tmp_path / "site"
    code = report_gallery.main(
        [
            "--out",
            str(out),
            "--archkeel",
            f"python3 {stub}",
            "--sha",
            "abc",
            "--built-at",
            "t",
            "--system",
            str(_fake(tmp_path, ["one", "two", "three"])),
        ]
    )
    page = (out / "self" / "index.html").read_text()
    assert code == 0
    for name in ("one", "two", "three"):
        assert f'href="{name}.html"' in page
        part = (out / "self" / f"{name}.html").read_text()
        assert '<a href="index.html">System</a>' in part
