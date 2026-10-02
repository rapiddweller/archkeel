# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Opened review tables keep every evidence column reachable without JavaScript."""

import pytest
from test_delta import _model, _record

from archkeel.ir.bindings import BindingReads, UnreadBinding
from archkeel.ir.codec import parse_observation
from archkeel.ir.duplication import OwnedLogic, RepeatedLogic
from archkeel.ir.references import SymbolReferences, UnreferencedSymbol
from archkeel.ir.structure import InsideSizes, OversizedInside
from archkeel.ir.type_fanin import TypeCrossing, TypeFanin
from archkeel.render.html import (
    _binding_claim_body,
    _claim_body,
    _document,
    _fanin_claim_body,
    _inside_claim_body,
    _repetition_claim_body,
    _structure,
)

NAME = "datamimic_ce.engine.runtime.tasks." + "nested_namespace_" * 4
OBSERVATION = parse_observation(
    _model(
        git_head="a" * 40,
        modules=[_record("module", kind="module", data={"qualified_name": NAME + ".worker"})],
    )
)
CASES = (
    (
        "symbols",
        _claim_body(
            SymbolReferences(
                "SUPPORTED", 1, 0, (UnreferencedSymbol(NAME, "function", "public", NAME),)
            ),
            OBSERVATION,
        ),
        "Visibility",
        "public",
    ),
    (
        "bindings",
        _binding_claim_body(
            BindingReads("SUPPORTED", 1, (UnreadBinding(NAME, "value", "parameter", NAME),))
        ),
        "Binding",
        "parameter",
    ),
    (
        "repetitions",
        _repetition_claim_body(
            OwnedLogic(
                "SUPPORTED", 1, 2, (RepeatedLogic(NAME, "owns work", NAME, NAME + ".copy", 17),)
            )
        ),
        "Nodes",
        "17",
    ),
    (
        "type crossings",
        _fanin_claim_body(TypeFanin("SUPPORTED", 3, (TypeCrossing(NAME, 2),))),
        "Component pairs",
        "2",
    ),
    (
        "inside sizes",
        _inside_claim_body(InsideSizes("SUPPORTED", 1, 1, (OversizedInside(NAME, 12, 23),))),
        "Edges inside",
        "23",
    ),
    ("size and coupling", _structure(OBSERVATION), "Unresolved calls", "no calls"),
)


@pytest.mark.parametrize("label,body,header,value", CASES, ids=[case[0] for case in CASES])
@pytest.mark.parametrize("width,javascript", [(375, True), (375, False), (1440, True)])
def test_opened_secondary_table_keeps_last_evidence_column_reachable(
    label: str, body: str, header: str, value: str, width: int, javascript: bool
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    html = _document(
        repository="sample",
        kind="Architecture evidence report",
        title="Archkeel report",
        content=(
            '<details class="report-section report-evidence">'
            "<summary>More measurements and review claims</summary>"
            f"<h2>{label}</h2>{body}</details>"
        ),
    ).decode()
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                viewport={"width": width, "height": 900}, java_script_enabled=javascript
            )
            page.set_default_timeout(2500)
            page.set_content(html, wait_until="load")
            page.locator("details > summary").click()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            table = page.locator("table")
            assert table.locator("th").last.text_content() == header
            assert table.locator("tbody tr").first.locator("td").last.inner_text() == value
            container = table.locator("xpath=parent::*")
            container.evaluate("node => node.scrollIntoView({block:'start'})")
            box = container.bounding_box()
            assert box is not None
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 40)
            page.mouse.wheel(2400, 0)
            # Rounded table borders can clip a subpixel corner of the header cell.
            playwright_api.expect(table.locator("th").last).to_be_in_viewport(ratio=0.99)
            last = table.locator("th").last.bounding_box()
            assert last is not None and 0 <= last["x"] < last["x"] + last["width"] <= width
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        finally:
            browser.close()
