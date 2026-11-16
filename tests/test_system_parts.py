# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-522: the parts of the system are in one document that the tools and the page follow."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from test_report_product_page import _STUB, _frame, _visible

from tools import report_gallery
from tools.report_product import Part
from tools.report_product_page import product_page
from tools.system_parts import DOCUMENT, ROOT, load

SHAPE = {"schema_version", "kind", "title", "parts", "rules"}


def test_the_document_has_the_shape_of_the_first_slice_of_the_system_contract() -> None:
    data = json.loads(DOCUMENT.read_text())
    assert set(data) == SHAPE and data["kind"] == "system" and data["rules"] == []
    assert all(set(part) == {"id", "title", "config"} for part in data["parts"])
    # No field that a contract reads names a language (a title is text for people): the language
    # and the roots come from the scan configuration.
    read = [data["kind"], data["schema_version"]]
    read += [part[key] for part in data["parts"] for key in ("id", "config")]
    flat = " ".join(read).lower()
    assert not any(word in flat for word in ("python", "rust", "typescript", "dart"))
    system = load()
    assert [(p.language, p.subject) for p in system.parts] == [
        ("PYTHON", "Python shell (src/archkeel)"),
        ("RUST", "Rust core (native)"),
    ]
    assert system.name == "ArchKeel (Python shell + Rust core)"


def test_no_tool_or_makefile_target_hard_wires_a_part() -> None:
    makefile = (ROOT / "Makefile").read_text()
    recipe = makefile.split("self-validate-system:")[1].split("\n\n")[0]
    # AD-616: the core runs the system document; the recipe names no part, config or result path.
    assert "--config $(SYSTEM_DOCUMENT)" in recipe
    assert "docs/architecture" not in recipe and "native/" not in recipe and ".json" not in recipe
    document = DOCUMENT.relative_to(ROOT).as_posix()
    assert f"SYSTEM_DOCUMENT := {document}\n" in makefile
    for tool in (
        "report_product.py",
        "report_product_page.py",
        "report_gallery.py",
    ):
        text = (ROOT / "tools" / tool).read_text()
        assert "ArchKeel (Python shell" not in text and "SYSTEM_TITLE" not in text, tool
        assert not re.search(r'["\'](Python shell|Rust core)["\']', text), tool


def test_the_gallery_self_runs_are_the_parts_of_the_document() -> None:
    parts = load().parts
    assert [run["name"] for run in report_gallery.SELF_RUNS] == [p.id for p in parts]
    assert [run["config"] for run in report_gallery.SELF_RUNS] == [p.config for p in parts]


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


def test_the_gallery_builds_one_card_for_each_part_of_a_document_with_three_parts(
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
    assert code == 0 and page.count('class="rp-part"') == 3
    assert all((out / "self" / f"{name}.html").is_file() for name in ("one", "two", "three"))
