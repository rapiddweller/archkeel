# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check the shipped Explorer HTML without a browser."""

from pathlib import Path

import core_support
import pytest
from explorer_support import write_pages


def test_report_keeps_the_diagram_without_removed_panels(
    release_core: Path, tmp_path: Path
) -> None:
    write_pages(
        release_core, tmp_path, {"system": (None, "docs/architecture/architecture-system.json")}
    )
    page = (tmp_path / "system.html").read_text(encoding="utf-8")
    for removed in (
        "Health check",
        "data-open-matrix",
        "flow-matrix",
        "atlas-matrix-dialog",
        "flow-explore",
        "Keyboard shortcuts",
        "data-gap-search",
        "run-frame-data",
        "data-download-frame",
    ):
        assert removed not in page
    for retained in (
        'id="flow-graph"',
        "data-flow-view",
        "flow-details-toggle",
        "Objects (O)",
        'id="gap-records-file"',
    ):
        assert retained in page


def test_missing_report_shows_the_refusal(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(core_support, "run", lambda *_args: (2, {"error": "scan limit"}))
    with pytest.raises(AssertionError, match="scan limit") as error:
        write_pages(tmp_path / "core", tmp_path, {"system": (None, "config.json")})
    assert str(tmp_path / "system.html") in str(error.value)


@pytest.mark.parametrize("code", [1, 2])
def test_existing_report_accepts_a_nonzero_verdict(monkeypatch, tmp_path: Path, code: int) -> None:
    (tmp_path / "system.html").write_text("report")
    monkeypatch.setattr(core_support, "run", lambda *_args: (code, {"status": "FAIL"}))
    write_pages(tmp_path / "core", tmp_path, {"system": (None, "config.json")})
