# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Small browser acceptance pass over the report demo catalog."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

try:
    from playwright.sync_api import Browser, Page, sync_playwright
except ImportError as error:
    raise SystemExit("Playwright is missing; run `make browser-install` first.") from error

from archkeel.check.ratchets import unknown_positions_by_rule
from archkeel.check.report import VIOLATION_REMEDY
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.graph_codec import parse_report
from archkeel.ir.module_explore import module_exploration
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.report_projection import architecture_projection
from fixtures.architecture_demo import replay


def _make_reports(output: Path) -> dict[str, Path]:
    cases = {
        "uml-match": ("uml-match", 0),
        "uml-complete": ("uml-complete", 0),
        "uml-dart": ("uml-dart", 0),
        "uml-typescript": ("uml-typescript", 0),
        "uml-typescript-match": ("uml-typescript-match", 0),
        "uml-typescript-mismatch": ("uml-typescript-mismatch", 2),
        "uml-typescript-partial": ("uml-typescript-partial", 0),
        "uml-mismatch": ("uml-mismatch", 2),
        "uml-partial": ("uml-partial", 0),
        "tour": ("tour", 2),
        "clean": ("clean", 0),
        "open": ("class-a-decision-open", 2),
        "wide": ("class-a-recursive-wide-package", 0),
        "deep": ("class-a-recursive-inside-violation", 2),
        "mixed": ("class-a-boundary-types-mixed-evidence", 2),
        "unknown": ("class-a-boundary-types-ordinary-reexport-chain-unknown", 0),
        "known": ("validation-baseline-subject-order", 0),
        "target-present": ("target-module-present", 0),
        "target-absent": ("target-module-absent", 0),
        "target-store": ("target-hierarchy-positive", 0),
        "empty-responsibility": ("target-empty-responsibilities", 0),
    }
    reports = {}
    for name, (variant, expected_exit) in cases.items():
        report = output / f"{name}.json"
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            actual_exit = replay(variant, report)
        assert actual_exit == expected_exit, (
            f"{variant}: exit {actual_exit}, expected {expected_exit}\n"
            f"{stdout.getvalue()}\n{stderr.getvalue()}"
        )
        result = json.loads(stdout.getvalue().splitlines()[-1])
        (output / f"{name}.result.json").write_text(json.dumps(result, indent=2) + "\n")
        html = report.with_name(f"{name}.report.html")
        assert html.is_file(), f"{variant} did not produce {html}"
        reports[name] = html
    return reports


def _visit(
    browser: Browser,
    report: Path,
    name: str,
    output: Path,
    *,
    device_scale_factor: float = 1,
) -> tuple[Page, list[str]]:
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000}, device_scale_factor=device_scale_factor
    )
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console", lambda message: errors.append(message.text) if message.type == "error" else None
    )
    page.on(
        "request",
        lambda request: (
            errors.append(f"Offline report requested {request.url}")
            if request.url.startswith(("http:", "https:"))
            else None
        ),
    )
    try:
        page.goto(report.as_uri(), wait_until="load")
        page.screenshot(path=str(output / f"{name}-1440x1000.png"), full_page=True)
    except Exception:
        try:
            _finish(page, name, output)
        except Exception:
            pass
        raise
    return page, errors


def _finish(page: Page, name: str, output: Path) -> None:
    page.context.tracing.stop(path=str(output / f"{name}-trace.zip"))
    page.context.close()


def _check_no_javascript(browser: Browser, report: Path, output: Path) -> None:
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, java_script_enabled=False)
    try:
        page.goto(report.as_uri(), wait_until="load")
        assert page.locator(".atlas-heading").is_visible()
        assert page.locator(".atlas-status").is_visible()
        page.locator(".atlas-source summary").click()
        assert page.get_by_role(
            "link", name="Complete architecture JSON and recorded evidence"
        ).is_visible()
        assert not page.locator(".flow-views").is_visible()
        page.screenshot(path=str(output / "atlas-nojs-1440.png"), full_page=True)
    finally:
        page.close()


def _check_atlas(page: Page, architecture: Path) -> None:
    data = json.loads(page.locator("#flow-data").text_content() or "{}")["atlas"]
    model = parse_observation(decode_canonical_model(json.loads(architecture.read_bytes())))
    report = architecture_report(model)
    assessments = rule_assessments(model, undecided_by_rule=unknown_positions_by_rule(model))
    projection = architecture_projection(
        model, report, assessments, violation_remedy=VIOLATION_REMEDY
    )
    assert str(model.source.git_head) in page.locator(".atlas-heading").inner_text()
    audit_text = page.locator(".atlas-source").text_content() or ""
    assert model.source.source_digest in audit_text
    assert model.contract.digest in audit_text
    assert data["source"] == {
        "git_head": model.source.git_head,
        "source_digest": model.source.source_digest,
    }
    assert data["status"] == projection.status and data["reason"] == projection.reason
    assert data["unknown_count"] == len(projection.unknowns)
    expected = {item.id: item for item in projection.components}
    assert set(expected) == {item["id"] for item in data["components"]}
    for item in data["components"]:
        native = expected[item["id"]]
        assert (item["status"], data["reference_ids"][item["reason_ref"]]) == (
            native.status,
            native.reason,
        )
        intent = json.loads(json.dumps(asdict(native)))
        for field in (
            "responsibilities",
            "not_responsible_for",
            "planned",
        ):
            assert item[field] == intent[field]
        assert [data["reference_ids"][index] for index in item["provenance"]] == intent[
            "provenance"
        ]
        assert (
            None
            if item["public"] is None
            else [data["reference_ids"][index] for index in item["public"]]
        ) == intent["public"]
        assert [
            {
                **{key: value for key, value in edge.items() if key != "rationale_ref"},
                "target_id": data["components"][edge["target_id"]]["id"],
                "rationale": data["reference_ids"][edge["rationale_ref"]],
            }
            for edge in item["requires"]
        ] == intent["requires"]
        assert [
            {"component_id": data["components"][index]["id"], "import_sites": count}
            for index, count in item["used_by"]
        ] == intent["used_by"]
        href = data["detail_page"] + "?" + urlencode({"component": item["id"]})
        filename = urlsplit(href).path
        assert Path(filename).name == filename and (architecture.parent / filename).is_file()
        assert parse_qs(urlsplit(href).query)["component"] == [native.id]
        sidecar = (architecture.parent / filename).read_text()
        assert "default-src 'none'" in sidecar and "fetch(" not in sidecar
        assert "Back to architecture map" in sidecar
    exploration = module_exploration(model)
    assert {item["id"] for item in data["modules"]} == {item.id for item in exploration[0].modules}
    native_modules = {item.id: item for item in exploration[0].modules}
    for item in data["modules"]:
        native = native_modules[item["id"]]
        assert (item["name"], item["symbols"], item["fan_in"], item["fan_out"]) == (
            native.name,
            native.symbols,
            native.fan_in,
            native.fan_out,
        )
    assert [
        (
            data["modules"][row[0]]["id"],
            data["modules"][row[1]]["id"],
            row[2],
            row[3],
            "UNKNOWN",
            data["reference_ids"][data["cell_permission_reason_ref"]],
            tuple(data["reference_ids"][index] for index in row[4]),
            tuple(data["reference_ids"][index] for index in row[5]),
            tuple(data["reference_ids"][index] for index in row[6]),
        )
        for row in data["cells"]
    ] == [
        (
            item.source_id,
            item.target_id,
            item.import_sites,
            item.status,
            item.permission,
            item.permission_reason,
            item.evidence_ids,
            item.finding_ids,
            item.reasons,
        )
        for item in exploration[0].cells
    ]
    hints = [
        {
            **hint,
            **{
                field: [data["reference_ids"][index] for index in hint[field]]
                for field in ("evidence_ids", "relationship_ids")
            },
        }
        for hint in data["questions"]
    ]
    assert hints == json.loads(
        json.dumps([asdict(hint) for level in exploration for hint in level.hint_candidates])
    )
    unknown_href = urlsplit(data["detail_page"] + data["unassigned_detail_href"]).path
    assert (
        Path(unknown_href).name == unknown_href and (architecture.parent / unknown_href).is_file()
    )
    html = page.content()
    assert "default-src 'none'" in html and "fetch(" not in html
    assert "data-ds=" not in html and "Simulate violation" not in html
    assert page.locator('[data-atlas="true"]').is_visible()


def _check_atlas_interactions(page: Page) -> None:
    payload = page.locator("#flow-data").text_content()
    page.get_by_role("button", name="As-Is", exact=True).click()
    card = page.locator(".flow-nodes [data-uml-id]").first
    position = card.get_attribute("transform") if card.count() else None
    if card.count():
        card.click()
        assert "core facts" in page.locator(".flow-inspector-content").inner_text().lower()
    for lens in ("Target", "Diff", "As-Is"):
        page.get_by_role("button", name=lens, exact=True).click()
        if card.count():
            assert card.get_attribute("transform") == position
        assert page.locator("#flow-data").text_content() == payload
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if lens == "Target":
            assert page.locator(".flow-matrix").is_hidden()
            assert not page.locator(".atlas-module-list").count()
            assert not page.locator("[data-copy-question]").count()
            text = page.locator(".flow-inspector-content").inner_text().lower()
            assert "observed weight" not in text
            assert "recorded checks" not in text
            assert "observed import cell" not in text
    module = page.locator(".matrix-label[data-module]").first
    if module.count():
        module.click()
        assert "observed module" in page.locator(".flow-inspector-content").inner_text().lower()
        page.get_by_role("button", name="Target", exact=True).click()
        assert "observed module" not in page.locator(".flow-inspector-content").inner_text().lower()
        page.get_by_role("button", name="As-Is", exact=True).click()
    question = page.locator("[data-copy-question]").first
    if question.count():
        page.evaluate("""() => Object.defineProperty(navigator, 'clipboard', {
            configurable: true, value: {writeText: async () => {throw new Error('denied');}}
        })""")
        question.click()
        receipt = page.get_by_role("textbox", name="Question and recorded evidence").input_value()
        assert "Source digest:" in receipt and "Evidence IDs:" in receipt
        source = json.loads(page.locator("#flow-data").text_content() or "{}")["atlas"]["source"]
        assert source["source_digest"] in receipt and str(source["git_head"]) in receipt
        assert "Provisional hint, not a verdict." in receipt
    theme = page.locator(".theme-toggle")
    before = page.evaluate("getComputedStyle(document.body).backgroundColor")
    theme.click()
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") != before
    theme.click()
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == before


def _check_module_graph(page: Page) -> None:
    data = json.loads(page.locator("#flow-data").text_content() or "{}")["atlas"]
    query = parse_qs(urlsplit(page.url).query)
    assert query.get("view") != ["target"]
    scope = query.get("scope", [None])[0]
    level = next(item for item in data["levels"] if item["parent_id"] == scope)
    choice = page.get_by_role("group", name="Content", exact=True)
    assert choice.is_visible() == bool(level["component_ids"] and level["modules"])
    if choice.is_visible():
        choice.locator('[data-content="modules"]').click()
        assert parse_qs(urlsplit(page.url).query)["content"] == ["modules"]
    modules = [data["modules"][data["assignments"][index][0]] for index in level["modules"]]
    ids = {item["id"] for item in modules}
    cards = page.locator('.flow-nodes [data-uml-kind="module"]')
    assert set(cards.evaluate_all("nodes => nodes.map(n => n.dataset.umlId)")) == ids
    assert page.locator(".flow-canvas").is_visible()
    assert page.locator(".flow-alternative").is_hidden()
    for module in modules:
        card = page.locator(f'.flow-nodes [data-uml-id="{module["id"]}"]')
        assert card.get_attribute("data-label") == Path(module["path"]).name
    cells = {
        index: data["cells"][index]
        for index in level["cells"]
        if data["modules"][data["cells"][index][0]]["id"] in ids
        and data["modules"][data["cells"][index][1]]["id"] in ids
    }
    assert page.locator(".flow-edges .hit").count() == len(cells)
    for index, cell in cells.items():
        edge = page.locator(f'.flow-edges [data-uml-id="module-cell:{index}"]')
        assert edge.get_attribute("data-uml-source") == data["modules"][cell[0]]["id"]
        assert edge.get_attribute("data-uml-target") == data["modules"][cell[1]]["id"]
        assert edge.locator(".atlas-edge-label").text_content() == (
            f"{cell[2] if cell[2] is not None else '?'} import{'s' if cell[2] != 1 else ''}"
        )
        state = (
            "violation"
            if cell[3] == "FAIL"
            else "undecided"
            if cell[3] == "UNKNOWN"
            else "observed"
        )
        assert edge.evaluate("(edge, state) => edge.classList.contains(state)", state)
        assert f"Core {cell[3]}; permission UNKNOWN" in edge.locator(".hit").get_attribute(
            "aria-label"
        )
    sites = (
        sum(cell[2] for cell in cells.values())
        if all(cell[2] is not None for cell in cells.values())
        else "UNKNOWN"
    )
    assert page.locator(".atlas-summary").inner_text() == (
        f"{len(ids)} observed module{'s' if len(ids) != 1 else ''} · "
        f"{len(cells)} local {'dependency' if len(cells) == 1 else 'dependencies'} · "
        f"{sites} import site{'s' if sites != 1 else ''}"
    )


def _open_uml_details(page: Page) -> None:
    payload = json.loads(page.locator("#flow-data").text_content() or "{}")
    if "atlas" not in payload:
        return
    data = payload["atlas"]
    module = next(item for item in data["modules"] if Path(item["path"]).stem == "core")
    component = next(item for item in data["components"] if item["label"] == "demo")
    page.locator(f'.flow-nodes [data-uml-id="{component["id"]}"]').press("Enter")
    _check_module_graph(page)
    page.locator(f'.flow-nodes [data-uml-id="{module["id"]}"]').dblclick()
    page.wait_for_url("**/*.detail.html?*")
    assert page.url.startswith("file:") and ".detail.html" in page.url
    query = parse_qs(urlsplit(page.url).query)
    assert query["module"] == [module["id"]]
    assert query["return_selected"] == [module["id"]]


def _show_details(page: Page) -> None:
    toggle = page.locator(".flow-details-toggle")
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()


def _check_inner_uml(page: Page, name: str, output: Path) -> None:
    _open_uml_details(page)
    module_url = page.url
    payload = page.locator("#flow-data").text_content()
    fields = json.loads(payload or "{}")
    # Navigation hints belong to the page transport, not the Core report schema.
    report = parse_report(
        {
            key: value
            for key, value in fields.items()
            if key not in {"initial_scope", "initial_view", "navigation"}
        }
    )
    expected = {
        "uml-match": "PASS",
        "uml-complete": "UNKNOWN",
        "uml-mismatch": "FAIL",
        "uml-partial": "UNKNOWN",
        "uml-dart": "UNKNOWN",
        "uml-typescript": "UNKNOWN",
        "uml-typescript-match": "PASS",
        "uml-typescript-mismatch": "FAIL",
        "uml-typescript-partial": "UNKNOWN",
    }[name]
    assert report.comparison.status == expected
    language = next(e.language for e in report.target.entities if e.kind == "module")
    annotation = {"python": "str", "dart": "String", "typescript": "string"}[language]
    returns = "None" if language == "python" else "void"
    for view in ("diagram", "target", "diff"):
        page.goto(module_url, wait_until="load")
        page.locator(f'[data-flow-view="{view}"]').click()
        assert page.locator(".atlas-heading").count() == 1
        assert page.locator(".flow-views [data-flow-view]").count() == 3
        assert page.locator('.flow-nodes [data-uml-kind="component"]').count() == 0
        if language == "dart" and view in {"diagram", "diff"}:
            assert not any(
                e.kind in {"class", "method", "function"} for e in report.observed.entities
            )
            _show_details(page)
            details = page.locator(".flow-inspector-content").inner_text().lower()
            assert "source file" in details and "coverage" in details and "unavailable" in details
            assert page.locator(".flow-nodes [data-uml-id]").count() == 0
            page.locator("#flow").screenshot(path=str(output / f"{name}-{view}-modules.png"))
            assert page.locator("#flow-data").text_content() == payload
            continue
        if language == "typescript":
            source_names = {entity.qualified_name for entity in report.observed.entities}
            assert "demo.src.core_x2e_ts.Client" in source_names
            assert "demo.src.core_x2e_ts.Port" in source_names
            assert "demo.src.core_x2e_ts.Client.run" in source_names
        nodes = page.locator(".flow-nodes [data-uml-id]")
        assert {"class", "interface", "enum", "function", "constant"} <= set(
            nodes.evaluate_all("nodes => nodes.map(n => n.dataset.umlKind)")
        )
        assert nodes.first.is_visible()
        edges = page.locator(".flow-edges .edge")
        assert edges.count() > 0
        assert nodes.evaluate_all("""nodes => {
          const boxes = nodes.map(n => n.querySelector('.card').getBoundingClientRect());
          return boxes.every((a, i) => boxes.slice(i + 1).every(b =>
            a.right <= b.left + 1 || b.right <= a.left + 1
            || a.bottom <= b.top + 1 || b.bottom <= a.top + 1));
        }""")
        assert edges.evaluate_all("""edges => edges.every(edge => {
          const line = edge.querySelector('.line'), hit = edge.querySelector('.hit');
          return line.getAttribute('d') === hit.getAttribute('d')
            && getComputedStyle(line).markerEnd !== 'none';
        })""")
        if name == "uml-complete":
            page.locator('.flow-nodes [data-label="describe"]').press("Space")
            page.mouse.move(0, 0)
            related = page.locator(".flow-nodes .node.related").evaluate_all(
                "nodes => nodes.map(n => n.dataset.label)"
            )
            assert {"State", "VERSION"} <= set(related)
            assert (
                page.locator(
                    '.flow-edges .edge.related[data-relationship-kind="references"]'
                ).count()
                == 2
            )
            page.locator("#flow").screenshot(path=str(output / f"{name}-{view}-internal-uses.png"))
        page.get_by_role("button", name="Member previews", exact=True).click()
        client = page.locator('.flow-nodes [data-label="Client"]')
        assert f"− _token: {annotation}" in client.text_content()
        assert client.locator(".uml-icon").count() > 0
        client.press("Space")
        page.mouse.move(0, 0)
        assert client.evaluate("n => n.classList.contains('selected')")
        assert page.locator(".flow-nodes .node.related").count() > 1
        assert page.locator(".flow-nodes .node.dim").count() > 0
        page.locator("#flow").screenshot(path=str(output / f"{name}-{view}-core.png"))
        client.dblclick()
        reset = page.locator('.flow-nodes [data-label="reset"]')
        assert reset.get_attribute("data-uml-kind") == "method"
        assert (
            reset.locator(".label").evaluate("n => getComputedStyle(n).textDecorationLine")
            == "underline"
        )
        reset.press("Space")
        _show_details(page)
        expected_reset_return = (
            "number" if name == "uml-typescript-mismatch" and view != "target" else returns
        )
        assert (
            f"+ reset(): {expected_reset_return}"
            in page.locator(".flow-inspector-content").inner_text()
        )
        page.locator("#flow").screenshot(path=str(output / f"{name}-{view}-members.png"))
        page.locator(".flow-back").click()
        page.locator('.flow-nodes [data-label="State"]').dblclick()
        ready = page.locator('.flow-nodes [data-label="READY"][data-uml-kind="enum_literal"]')
        if name == "uml-partial" and view in {"diagram", "diff"}:
            assert ready.count() == 0
            for kind in ("attribute", "binding"):
                assert (
                    page.locator(
                        f'.flow-nodes [data-label="READY"][data-uml-kind="{kind}"]'
                    ).count()
                    == 1
                )
        else:
            assert ready.count() == 1
            assert ready.locator(".stereotype").text_content() == "«enumeration literal»"
        page.locator(".flow-back").click()
        page.locator('.flow-nodes [data-label="build"]').dblclick()
        item = page.locator('.flow-nodes [data-label="item"]')
        assert item.get_attribute("data-uml-kind") == "binding"
        if view in {"diagram", "diff"} and name == "uml-typescript-partial":
            assert "constructors[0]" in item.text_content()
            assert any(
                relationship.kind == "instance_of"
                and relationship.target_id is None
                and relationship.resolution == "unresolved"
                for relationship in report.observed.relationships
            )
        else:
            if view in {"diagram", "diff"}:
                initializer = "new Unit()" if language == "typescript" else "Unit()"
                assert initializer in item.text_content()
            assert page.locator('.flow-edges [data-relationship-kind="instance_of"]').count() > 0
        item.press("Space")
        _show_details(page)
        inspector = page.locator(".flow-inspector-content").inner_text()
        if language == "typescript":
            assert "binding" in inspector
            if view in {"diagram", "diff"}:
                assert "does not identify a live object or its current value" in inspector
        else:
            assert "live object" in inspector
        assert page.locator("#flow-data").text_content() == payload


def _check_wide_inventory(page: Page) -> None:
    data = json.loads(page.locator("#flow-data").text_content() or "{}")["atlas"]
    names = {item["name"] for item in data["modules"]}
    expected = {
        "shop.store.backend.tasks",
        *(
            f"shop.store.backend.tasks.{name}"
            for name in (
                "alpha",
                "bravo",
                "charlie",
                "delta",
                "echo",
                "foxtrot",
                "isolated",
                "source",
                "target",
            )
        ),
    }
    assert {name for name in names if name.startswith("shop.store.backend.tasks")} == expected
    page.get_by_role("button", name="As-Is", exact=True).click()
    for label in ("store", "backend", "tasks"):
        page.locator(f'.flow-nodes [data-label="{label}"]').press("Enter")
    _check_module_graph(page)
    module = next(
        item for item in data["modules"] if item["name"] == "shop.store.backend.tasks.isolated"
    )
    card = page.locator(f'.flow-nodes [data-uml-id="{module["id"]}"]')
    assert card.is_visible()
    card.press("Enter")
    page.wait_for_url("**/*.detail.html?*")
    assert page.url.startswith("file:")
    assert parse_qs(urlsplit(page.url).query)["module"] == [module["id"]]
    assert page.locator("#flow-data").text_content()


def _capture_assets(browser: Browser, reports: dict[str, Path], output: Path) -> None:
    # Keep published PNGs under 400 KB without changing the CSS layout.
    page, errors = _visit(browser, reports["tour"], "assets-atlas", output, device_scale_factor=0.9)
    try:
        page.goto(reports["tour"].as_uri() + "?theme=dark", wait_until="load")
        assert page.locator("html").get_attribute("data-theme") == "dark"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        for heading in ("Worth a look", "Module matrix"):
            assert page.get_by_role("heading", name=heading, exact=True).is_visible()
        assert page.locator(".flow-nodes [data-uml-kind=component]").count()
        page.locator(".atlas-findings").evaluate("node => node.open = false")
        assert page.locator(".atlas-findings").is_visible()
        assert page.locator(".atlas-verdict-grid .verdict-card").count() == 4
        assert not page.locator(".atlas-status-key").count()
        page.screenshot(path=str(output / "archkeel-report-preview.png"), full_page=True)
        page.locator("#flow").screenshot(path=str(output / "archkeel-component-flow.png"))
        page.locator('.flow-nodes [data-label="store"]').dblclick()
        page.locator(".atlas-findings").evaluate("node => node.open = true")
        page.locator(".atlas-finding-group").first.locator("summary").click()
        assert page.locator(".atlas-findings li").first.is_visible()
        page.locator("#flow").screenshot(path=str(output / "archkeel-shop-store-inside.png"))
        _check_module_graph(page)
        for name in ("archkeel-report-preview.png", "archkeel-shop-store-inside.png"):
            assert (output / name).stat().st_size <= 400_000, f"{name} exceeds 400 KB"
        for width in (1440, 375):
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors
    finally:
        _finish(page, "assets-atlas", output)


def _check_report_verdicts(browser: Browser, reports: dict[str, Path], output: Path) -> None:
    for name in ("open", "tour", "mixed", "clean"):
        result = json.loads((output / f"{name}.result.json").read_text())
        for javascript in (True, False):
            page = browser.new_page(java_script_enabled=javascript)
            try:
                page.goto(reports[name].as_uri(), wait_until="load")
                for index, status in enumerate(("PASS", "FAIL", "UNKNOWN", "NOT CHECKED")):
                    card = page.locator(".atlas-verdict-grid .verdict-card").nth(index)
                    assert card.locator(".verdict-state").inner_text().endswith(status)
                    if status == "NOT CHECKED" or result["rule_assessments"] is None:
                        assert card.locator("h3").inner_text() == "Count unavailable"
                    else:
                        count = sum(item["status"] == status for item in result["rule_assessments"])
                        assert (
                            card.locator("h3").inner_text()
                            == f"{count} rule{'s' if count != 1 else ''}"
                        )
                for width in (1440, 375):
                    page.set_viewport_size({"width": width, "height": 1000})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            finally:
                page.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.environ.get("OUTPUT", "test-artifacts/report-browser")),
    )
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    reports = _make_reports(output)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, channel=os.environ.get("PLAYWRIGHT_CHANNEL")
        )
        try:
            for name, report in reports.items():
                page, errors = _visit(browser, report, name, output)
                try:
                    _check_atlas(page, output / f"{name}.json")
                    for width in (1440, 375):
                        page.set_viewport_size({"width": width, "height": 1000})
                        _check_atlas_interactions(page)
                    if name.startswith("uml-"):
                        page.set_viewport_size({"width": 1440, "height": 1000})
                        _check_inner_uml(page, name, output)
                    if name == "wide":
                        _check_wide_inventory(page)
                    assert not errors, f"{name}: {errors}"
                finally:
                    _finish(page, name, output)
            _check_no_javascript(browser, reports["mixed"], output)
            _check_report_verdicts(browser, reports, output)
            _capture_assets(browser, reports, output)
        finally:
            browser.close()
    print(f"Browser acceptance artifacts: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
