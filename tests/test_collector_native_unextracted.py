# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-340 (PR 4.3a-5): a node that the native extraction loses is a gap, never a complete scan.

Consumer: `imports.rs` (`check_extracted`). Every import-bearing node of the tree must end as a
record or as a gap. A bug in the extraction that skips a node would otherwise leave no trace, and
the scan would read as complete. The test plants that bug (`plant.rs`, only in the test binary)
and checks that the node becomes a collection gap named `unextracted`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_collector_native_imports import _request
from test_collector_native_syntax import dump_binary  # noqa: F401

from archkeel.analyzer.process import ProcessCollector
from archkeel.ir.facts import SourceFacts
from archkeel.ir.protocol import CollectionError, ProtocolVersion

PLANT = "ARCHKEEL_PLANT_SKIP"
FILES = {
    "tsconfig.json": '{"include":["src"]}',
    "src/a.ts": "import { b } from './b';\nimport { c } from './c';\nexport const a = b + c;\n",
    "src/b.ts": "export const b = 1;\n",
    "src/c.ts": "export const c = 2;\n",
}


def _write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _collect(binary: Path, root: Path) -> SourceFacts:
    request = _request(root, "app", "tsconfig.json")
    result = ProcessCollector((str(binary),), protocol_version=ProtocolVersion.V8).collect(request)
    assert not isinstance(result, CollectionError), result
    return result


def _titles(facts: SourceFacts) -> list[str]:
    return [gap.title for gap in facts.coverage.gaps]


def _imports_of(facts: SourceFacts, rel: str) -> int:
    evidence = {item.id: item.file for item in facts.evidence}
    section = next(item for item in facts.sections if item.name.value == "imports")
    return sum(1 for record in section.records if evidence[record.evidence_ids[0]] == rel)


def test_an_extraction_that_loses_no_node_has_no_unextracted_gap(
    tmp_path: Path,
    dump_binary: Path,  # noqa: F811
) -> None:
    _write(tmp_path, FILES)
    facts = _collect(dump_binary, tmp_path)
    assert not [title for title in _titles(facts) if "unextracted" in title]
    assert facts.coverage.full_scope
    assert _imports_of(facts, "src/a.ts") == 2


@pytest.mark.parametrize("index", [0, 1])
def test_a_node_that_the_extraction_skips_becomes_an_unextracted_gap(
    tmp_path: Path,
    dump_binary: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    index: int,
) -> None:
    _write(tmp_path, FILES)
    monkeypatch.setenv(PLANT, f"src/a.ts:{index}")
    facts = _collect(dump_binary, tmp_path)
    lost = [title for title in _titles(facts) if "unextracted" in title]
    assert lost == ["unextracted: 1 import-bearing node(s) of src/a.ts have no record and no gap"]
    assert _imports_of(facts, "src/a.ts") == 1
    assert not facts.coverage.full_scope


def test_a_node_in_a_repaired_part_has_the_gap_of_the_syntax_error(
    tmp_path: Path,
    dump_binary: Path,  # noqa: F811
) -> None:
    files = {
        **FILES,
        "src/a.ts": "import { b } from './b';\nconst x = (;\nimport { c } from './c';\n",
    }
    _write(tmp_path, files)
    facts = _collect(dump_binary, tmp_path)
    titles = _titles(facts)
    assert any(title.startswith("Syntax error in src/a.ts") for title in titles)
    assert not [title for title in titles if "unextracted" in title]
    assert not facts.coverage.full_scope


SCAN_FILES = {
    "tsconfig.json": '{"include":["src"],"compilerOptions":{"allowJs":true}}',
    "src/a.ts": (
        "import { b } from './b';\n"
        "export { b as b2 } from './b';\n"
        "export const d = import('./b');\n"
        "export const r = require('./b');\n"
    ),
    "src/b.ts": "export const b = 1;\n",
}


@pytest.mark.parametrize("lost", ["import", "export", "dynamic", "require"])
def test_a_node_that_the_scan_loses_becomes_an_unextracted_gap(
    tmp_path: Path,
    dump_binary: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    lost: str,
) -> None:
    # The count of the nodes comes from a query apart from the scan, so a loss in `scan.rs`
    # (planted here, only in the test binary) is seen, where a count fed by the scan would not.
    _write(tmp_path, SCAN_FILES)
    monkeypatch.setenv("ARCHKEEL_PLANT_SCAN", lost)
    facts = _collect(dump_binary, tmp_path)
    found = [title for title in _titles(facts) if "unextracted" in title]
    assert found == ["unextracted: 1 import-bearing node(s) of src/a.ts have no record and no gap"]
    assert not facts.coverage.full_scope


def test_a_scan_that_loses_nothing_has_no_unextracted_gap(
    tmp_path: Path,
    dump_binary: Path,  # noqa: F811
) -> None:
    _write(tmp_path, SCAN_FILES)
    facts = _collect(dump_binary, tmp_path)
    assert not [title for title in _titles(facts) if "unextracted" in title]
