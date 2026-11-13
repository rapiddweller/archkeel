# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Atlas presents Core facts without embedding every source detail."""

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest
from browser_report_support import _browser_page, _open_details
from test_architecture_demo import _prepare_repo
from test_uml_rendering import _wait_for_layout

from archkeel.check.report import run_report
from archkeel.cli.config import load_config
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import GraphSchemaVersion, ReportSchemaVersion
from archkeel.ir.codec import (
    canonical_report_bytes,
    decode_canonical_model,
    parse_observation,
)
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.model import RunResult
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.report_projection import architecture_projection
from archkeel.render import html as html_renderer
from archkeel.render.html import render_architecture_html


def _result(model):
    return RunResult(
        "report",
        0,
        "PASS",
        "FAIL",
        "n/a",
        coverage=model.coverage,
        rule_assessments=rule_assessments(model, undecided_by_rule={}),
        architecture_projection=architecture_projection(
            model, architecture_report(model), (), violation_remedy="Review native findings"
        ),
    )


def _page(model):
    return render_architecture_html(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).decode()


@pytest.mark.browser
def test_planned_component_graph_and_report_schema_1_3_render_in_browser(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    root = _prepare_repo(
        tmp_path, {}, fixture=Path(__file__).parents[1] / "fixtures/planned-component-policy"
    )
    _, encoded = run_report(root, config=load_config(root), analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    assert report.schema_version == ReportSchemaVersion.V1_3_0
    assert report.target is not None
    assert report.target.schema_version == GraphSchemaVersion.V1_3_0

    html = html_renderer.render_html(
        replace(_result(model), architecture_projection=None),
        model,
        repository="Planned component policy",
        architecture_href="architecture.json",
    ).decode()
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', html, re.S)
    assert match is not None
    payload = json.loads(match.group(1))
    assert payload["schema_version"] == "1.3.0"
    assert payload["target"]["schema_version"] == "1.3.0"
    assert any(
        intent["component_id"] == "mcp" and intent["lifecycle"] == "planned"
        for intent in payload["target"]["component_intents"]
    )

    errors: list[str] = []
    playwright, browser, page = _browser_page(api, html, errors=errors)
    try:
        assert not errors, f"The 1.3 report failed in the browser runtime: {errors}"
        assert "Unsupported architecture report schema." not in page.locator("#flow").inner_text()
        page.locator(".flow-nodes > g").first.wait_for()
        for version in ("1.2.0", "1.0.0"):
            legacy = json.loads(json.dumps(payload))
            legacy["schema_version"] = version
            for graph in (legacy["observed"], legacy["target"]):
                if graph is None:
                    continue
                graph["schema_version"] = version
                for intent in graph["component_intents"]:
                    intent.pop("lifecycle", None)
                    if version == "1.0.0":
                        intent.pop("layer", None)
            legacy_html = (
                html[: match.start(1)]
                + json.dumps(legacy).replace("<", "\\u003c")
                + html[match.end(1) :]
            )
            errors.clear()
            page.set_content(legacy_html, wait_until="load")
            assert not errors, (
                f"The legacy {version} report failed in the browser runtime: {errors}"
            )
            assert (
                "Unsupported architecture report schema." not in page.locator("#flow").inner_text()
            )
            page.locator(".flow-nodes > g").first.wait_for()
    finally:
        browser.close()
        playwright.stop()


def _atlas(page):
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', page, re.S)
    assert match is not None
    data = json.loads(match.group(1))["atlas"]
    data["cells"] = [
        {
            "source_id": data["modules"][row[0]]["id"],
            "target_id": data["modules"][row[1]]["id"],
            "import_sites": row[2],
            "status": row[3],
            "permission": "UNKNOWN",
            "permission_reason": data["reference_ids"][data["cell_permission_reason_ref"]],
            "evidence_ids": row[4],
            "finding_ids": row[5],
            "reasons": [data["reference_ids"][index] for index in row[6]],
        }
        for row in data["cells"]
    ]
    data["rule_assessments"] = [
        {
            **row,
            "id": data["reference_ids"][row["id"]],
            "kind": data["reference_ids"][row["kind"]],
            "reason": data["reference_ids"][row["reason"]],
            "scope": data["reference_ids"][row["scope"]],
            "components": [data["reference_ids"][index] for index in row["components"]],
            "uncertainty_actions": [
                {**action, "next_action": data["reference_ids"][action["next_action"]]}
                for action in row["uncertainty_actions"]
            ],
            "evidence": [
                {**entry, "id": data["reference_ids"][entry["id"]]} for entry in row["evidence"]
            ],
        }
        for row in data["rule_assessments"]
    ]
    data["assignments"] = [
        dict(
            zip(
                ("id", "component_id", "candidate_ids", "ownership_status", "ownership_reason"),
                (
                    data["modules"][row[0]]["id"],
                    data["reference_ids"][row[1]] if row[1] is not None else None,
                    [data["reference_ids"][index] for index in row[2]],
                    row[3],
                    data["reference_ids"][row[4]],
                ),
                strict=True,
            )
        )
        for row in data["assignments"]
    ]
    for module in data["modules"]:
        module["symbol_coverage"] = data["symbol_coverages"][module["symbol_coverage"]]
    for level in data["levels"]:
        level["modules"] = [data["assignments"][index] for index in level["modules"]]
    return data


def _flow_payload(path):
    match = re.search(
        r'<script id="flow-data" type="application/json">(.*?)</script>', path.read_text(), re.S
    )
    assert match
    return json.loads(match.group(1))


_ALIAS_PAIR = {
    "origin": "sample.app.impl:Packet",
    "shape": (
        "tuple[tuple[str, list[object]] | tuple[str, list[object], "
        "sample.app.types.Metadata], list[dict[str, object]]]"
    ),
}
_ABSENT_ALIAS_PAIR = object()


_TYPED_UNION_BODY = "dict[str, float] | dict[tuple[int, int], float] | dict[SexKey, float]"
_EXPANDED_UNION_BODY = _TYPED_UNION_BODY.replace("SexKey", "str | None")


def _open_permission_records(page):
    """Open the bounded permission lists without eagerly opening record bodies."""
    _open_details(page)
    if page.locator(".flow-canvas").is_visible():
        _wait_for_layout(page)
    audit = page.locator("[data-boundary-audit]")
    if audit.count() and audit.get_attribute("open") is None:
        audit.locator(":scope > summary").click()
        page.locator("[data-boundary-audit][data-boundary-loaded]").wait_for(state="attached")
    for group in page.locator("[data-boundary-group]").all():
        if group.get_attribute("open") is None:
            group.locator(":scope > summary").click()
            group.locator("[data-boundary-permission]").first.wait_for(state="attached")
        while group.locator("[data-boundary-more]").count():
            group.locator("[data-boundary-more]").click()


def _open_permission_record(entry):
    entry.locator("summary").click()
    entry.locator("dl").wait_for(state="attached")
