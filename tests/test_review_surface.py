# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Review navigation and handoff preserve the underlying evidence."""

from archkeel.ir.model import Diagnostic, RunResult
from archkeel.render.html import render_check_html


def test_check_without_a_delta_does_not_claim_no_changes() -> None:
    result = RunResult(
        "check", 2, diagnostics=(Diagnostic("missing_tool", "git", "No comparison", "Install Git"),)
    )
    page = render_check_html(result, repository="shop", result_href="result.json").decode()
    assert "No semantic changes were observed" not in page
    assert "Comparison unavailable" in page
    assert "Accepted → candidate" in page
    assert 'href="#check-changes"' in page
