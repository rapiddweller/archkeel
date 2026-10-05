# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Atlas presents Core facts without embedding every source detail."""

import json
import re

import pytest
from browser_report_support import _browser_page
from test_module_explore import _sample

from archkeel.ir.codec import canonical_report_bytes
from archkeel.ir.model import RunResult
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.report_projection import architecture_projection
from archkeel.render.html import render_architecture_html


def _result(model):
    return RunResult(
        "report",
        0,
        "PASS",
        "FAIL",
        "n/a",
        coverage=model.coverage,
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


def _atlas(page):
    match = re.search(r'<script id="flow-data" type="application/json">(.*?)</script>', page, re.S)
    assert match is not None
    data = json.loads(match.group(1))["atlas"]
    data["cells"] = [
        dict(
            zip(
                (
                    "source_id",
                    "target_id",
                    "import_sites",
                    "status",
                    "permission",
                    "permission_reason",
                    "evidence_ids",
                    "finding_ids",
                    "reasons",
                ),
                (data["modules"][row[0]]["id"], data["modules"][row[1]]["id"], *row[2:]),
                strict=True,
            )
        )
        for row in data["cells"]
    ]
    data["assignments"] = [
        dict(
            zip(
                ("id", "component_id", "candidate_ids", "ownership_status", "ownership_reason"),
                (data["modules"][row[0]]["id"], *row[1:4], data["reference_ids"][row[4]]),
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


def test_default_report_is_one_authentic_repository_with_sparse_native_cells(tmp_path):
    model = _sample(tmp_path)
    page = _page(model)
    data = _atlas(page)
    assert data["repository"] == "One target"
    assert data["source"]["git_head"] == model.source.git_head
    assert data["source"]["source_digest"] == model.source.source_digest
    assert {item["id"] for item in data["components"]} == {"core", "peer"}
    assert len(data["cells"]) == 1
    cell = data["cells"][0]
    assert cell["status"] == "FAIL" and cell["permission"] == "UNKNOWN"
    assert cell["import_sites"] == 2
    assert cell["evidence_ids"] and cell["finding_ids"] and cell["reasons"]
    assert "data-ds=" not in page
    assert "Simulate violation" not in page
    assert "EXT-TS" not in page
    assert "Worth a look" in page
    assert 'aria-label="Switch to light theme"' in page
    assert len(page.encode()) < 1_000_000


def test_partial_lexical_inventory_keeps_symbols_and_uncertainty(tmp_path):
    model = _sample(tmp_path, extra_files={"sample/inventory.py": "def observed():\n    pass\n"})
    data = _atlas(_page(model))
    module = next(item for item in data["modules"] if item["name"] == "sample.inventory")
    assert module["symbols"] == 1
    assert module["symbol_coverage"]
    assert any(item["status"] != "complete" for item in module["symbol_coverage"])
    assert not any(question["kind"] == "heavy" for question in data["questions"])


def test_ambiguous_and_unowned_assignments_remain_distinct(tmp_path):
    data = _atlas(_page(_sample(tmp_path, ambiguous=True)))
    level = next(item for item in data["levels"] if item["parent_id"] is None)
    names = {item["id"]: item["name"] for item in data["modules"]}
    ambiguous = next(item for item in level["modules"] if names[item["id"]] == "sample.core")
    assert ambiguous["component_id"] is None
    assert ambiguous["candidate_ids"] == ["core", "overlap"]
    assert ambiguous["ownership_status"] == "UNKNOWN"
    unowned = next(item for item in level["modules"] if names[item["id"]] == "sample.unowned")
    assert unowned["candidate_ids"] == [] and unowned["ownership_status"] == "UNKNOWN"


def test_component_detail_links_are_relative_and_keep_shared_uml(tmp_path):
    from archkeel.render.html import render_architecture_details

    model = _sample(tmp_path, uml=True)
    encoded = canonical_report_bytes(model)
    result = _result(model)
    details = render_architecture_details(
        result, encoded, repository="One target", architecture_href="architecture.json"
    )
    data = _atlas(_page(model))
    assert len(details) >= 2
    for component in data["components"]:
        href = component["detail_href"]
        assert "/" not in href and href.endswith(".html")
        page = details[href].decode()
        assert 'id="flow-data"' in page
        assert "architecture.json" in page
        assert "fetch(" not in page
        assert "default-src 'none'" in page


@pytest.mark.parametrize("width", [1440, 400])
def test_atlas_browser_keeps_positions_and_unknown_cells_across_lenses(tmp_path, width):
    api = pytest.importorskip("playwright.sync_api")
    page_html = _page(_sample(tmp_path))
    errors = []
    playwright, browser, page = _browser_page(api, page_html, width=width, errors=errors)
    try:
        card = page.locator('.flow-nodes [data-label="core"]')
        assert card.count() == 1
        if width == 1440:
            assert page.locator(".flow-canvas").bounding_box()["y"] < 370
        position = card.get_attribute("transform")
        for lens in ("Target", "Diff", "As-Is"):
            page.get_by_role("button", name=lens, exact=True).click()
            assert card.get_attribute("transform") == position
        page.locator('.flow-matrix [data-cell="0"]').click()
        assert "Permission: UNKNOWN" in page.locator(".flow-inspector-content").inner_text()
        assert "FAIL" in page.locator(".flow-inspector-content").inner_text()
        page.get_by_role("button", name="Target", exact=True).click()
        details = page.locator(".flow-inspector-content").inner_text()
        assert "observed import cell" not in details.lower()
        assert "evidence ids" not in details.lower()
        page.get_by_role("button", name="As-Is", exact=True).click()
        page.locator(".matrix-label[data-module]").first.click()
        assert "observed module" in page.locator(".flow-inspector-content").inner_text().lower()
        page.get_by_role("button", name="Target", exact=True).click()
        assert "observed module" not in page.locator(".flow-inspector-content").inner_text().lower()
        dark = page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(0, 0, 0)"
        page.get_by_role(
            "button", name="Switch to light theme" if dark else "Switch to dark theme"
        ).click()
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == (
            "rgb(255, 255, 255)" if dark else "rgb(0, 0, 0)"
        )
        page.get_by_role(
            "button", name="Switch to dark theme" if dark else "Switch to light theme"
        ).click()
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == (
            "rgb(0, 0, 0)" if dark else "rgb(255, 255, 255)"
        )
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_offline_module_drilldown_reaches_native_classifiers_and_returns(tmp_path):
    from archkeel.render.html import render_architecture_details

    api = pytest.importorskip("playwright.sync_api")
    source = (
        "from enum import Enum\nLIMIT = 3\n"
        "def transform(value: int) -> int:\n    return value + LIMIT\n"
        "class Client:\n    def run(self, value: int) -> int:\n        return transform(value)\n"
        "class State(Enum):\n    READY = 'ready'\n    FAILED = 'failed'\n"
    )
    model = _sample(tmp_path, extra_files={"sample/core.py": source})
    index = tmp_path / "architecture.report.html"
    index.write_text(_page(model))
    result = _result(model)
    for name, content in render_architecture_details(
        result,
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).items():
        (tmp_path / name).write_bytes(content)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri())
        page.locator('.flow-nodes [data-label="core"]').dblclick()
        page.locator(".atlas-module-list").get_by_role(
            "link", name="sample.core", exact=True
        ).click()
        assert page.url.startswith("file:") and "?module=" in page.url
        for name, kind in (
            ("Client", "class"),
            ("transform", "function"),
            ("State", "enum"),
            ("LIMIT", "constant"),
        ):
            card = page.locator(f'.flow-nodes [data-label="{name}"]')
            assert card.get_attribute("data-uml-kind") == kind
            card.click()
            assert name in page.locator(".flow-inspector-content").inner_text()
        page.locator('.flow-nodes [data-label="State"]').dblclick()
        assert (
            page.locator('.flow-nodes [data-label="READY"]').get_attribute("data-uml-kind")
            == "enum_literal"
        )
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        assert page.url.startswith(index.as_uri())
        assert "scope=" in page.url
        assert "Architecture map · core" == page.locator("#flow-heading").inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_component_details_retain_outside_method_classifier_context(tmp_path):
    from archkeel.render.atlas import detail_report

    model = _sample(
        tmp_path,
        extra_files={
            "sample/core.py": "from sample.peer import Client\nClient.run()\n",
            "sample/peer.py": (
                "class Client:\n    @staticmethod\n    def run() -> int:\n        return 1\n"
            ),
        },
    )
    report = architecture_report(model)
    methods = {entity.id for entity in report.observed.entities if entity.kind == "method"}
    assert any(
        edge.kind == "calls" and edge.target_id in methods for edge in report.observed.relationships
    )
    scoped = detail_report(report, "core")
    scoped.validate()
    method = next(entity for entity in scoped.observed.entities if entity.kind == "method")
    classifier = next(
        entity for entity in scoped.observed.entities if entity.id == method.parent_id
    )
    assert classifier.kind == "class" and classifier.qualified_name == "sample.peer.Client"


def test_nested_detail_scope_retains_authentic_component_ancestors(tmp_path):
    from test_target_graph import _nested_repository

    from archkeel.check.report import run_report
    from archkeel.cli.observe import observe
    from archkeel.ir.codec import decode_canonical_model, parse_observation
    from archkeel.render.atlas import detail_report

    root, config = _nested_repository(tmp_path)
    _, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    report = architecture_report(parse_observation(decode_canonical_model(json.loads(encoded))))
    assert any(intent.parent_id for intent in report.target.component_intents)
    for intent in report.target.component_intents:
        scoped = detail_report(report, intent.component_id)
        scoped.validate()
        ids = {item.component_id for item in scoped.target.component_intents}
        assert intent.component_id in ids
        if intent.parent_id:
            assert intent.parent_id in ids


def test_module_and_classifier_defaults_show_only_direct_native_children(tmp_path):
    from archkeel.render.html import render_architecture_details

    api = pytest.importorskip("playwright.sync_api")
    model = _sample(
        tmp_path,
        extra_files={
            "sample/core.py": (
                "from enum import Enum\nfrom sample.peer import Base\nLIMIT = 3\n"
                "def transform(value):\n    if value is State:\n        return State.READY\n"
                "    return value + LIMIT\n"
                "class Client(Base):\n    def run(self):\n        return transform(LIMIT)\n"
                "class State(Enum):\n    READY = 'ready'\n    FAILED = 'failed'\n"
            ),
            "sample/peer.py": "class Base:\n    def outside(self):\n        return 1\n",
        },
    )
    graph = architecture_report(model).observed
    module = next(item for item in graph.entities if item.qualified_name == "sample.core")
    pages = render_architecture_details(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    )
    data = _atlas(_page(model))
    href = next(item["detail_href"] for item in data["components"] if item["id"] == "core")
    for name, content in pages.items():
        (tmp_path / name).write_bytes(content)
    errors = []
    playwright, browser, page = _browser_page(api, pages[href].decode(), errors=errors)
    try:
        page.goto((tmp_path / href).as_uri() + "?module=" + module.id)

        def direct_ids(parent):
            return {
                item.id
                for item in graph.entities
                if item.parent_id == parent and item.presence != "referenced"
            }

        def scene_ids():
            return set(
                page.locator(".flow-nodes [data-uml-id]").evaluate_all(
                    "nodes => nodes.map(node => node.dataset.umlId)"
                )
            )

        assert scene_ids() == direct_ids(module.id)
        assert page.locator('.flow-nodes [data-outside="true"]').count() == 0
        direct = direct_ids(module.id)
        sites = [
            (edge, target)
            for edge in graph.relationships
            if edge.kind != "owns" and edge.source_id in direct
            for target in ([edge.target_id] if edge.target_id else edge.candidate_ids)
            if target in direct
        ]
        groups = {(edge.kind, edge.source_id, target, edge.resolution) for edge, target in sites}
        assert groups
        assert page.locator(".flow-edges .hit").count() == len(groups)
        reset = page.locator('.flow-legend [data-relationship-kind=""]')
        assert reset.inner_text() == f"Local relationships · {len(groups)}"
        assert f"local relationships at this level · {len(groups)}" in reset.get_attribute("title")
        for kind, source, target, resolution in groups:
            hit = page.locator(
                f'.flow-edges [data-uml-id="{kind}:{source}>{target}:{resolution}"] .hit'
            )
            expected = sum(
                edge.kind == kind
                and edge.source_id == source
                and endpoint == target
                and edge.resolution == resolution
                for edge, endpoint in sites
            )
            assert f"{expected} source or declaration site" in hit.get_attribute("aria-label")
            hit.press("Enter")
            items = (
                page.locator(".flow-inspector-content h3")
                .filter(has_text="Relationship sites")
                .locator("xpath=following-sibling::ul[1]/li")
            )
            assert items.count() == expected
        assert (
            page.get_by_label("Element kind", exact=True).locator('[value="class"]').inner_text()
            == "class · 1"
        )
        page.get_by_label("Element kind", exact=True).select_option("class")
        assert scene_ids() == {
            item.id
            for item in graph.entities
            if item.parent_id == module.id and item.kind == "class"
        }
        page.get_by_label("Element kind", exact=True).select_option("")
        page.locator('.flow-legend [data-relationship-kind="inherits"]').click()
        assert (
            "in context"
            in page.locator('.flow-legend [data-relationship-kind="inherits"]').inner_text()
        )
        assert page.locator('.flow-nodes [data-label="Base"]').count() == 1
        assert page.locator(".flow-edges .hit").count() > 0
        page.locator('.flow-legend [data-relationship-kind=""]').click()
        assert scene_ids() == direct_ids(module.id)
        for name in ("Client", "State"):
            classifier = next(
                item
                for item in graph.entities
                if item.parent_id == module.id and item.qualified_name.endswith("." + name)
            )
            page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]').click()
            page.locator(".flow-open-selected").click()
            assert scene_ids() == direct_ids(classifier.id)
            page.locator(".flow-back").click()
            assert scene_ids() == direct_ids(module.id)
        assert not errors
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("component_id", ["ROOT", "unassigned"])
def test_unknown_detail_links_keep_deeper_claimed_modules_and_distinct_names(
    tmp_path, component_id
):
    from test_target_graph import _nested_repository

    from archkeel.check.report import run_report
    from archkeel.cli.observe import observe
    from archkeel.ir.codec import decode_canonical_model, parse_observation
    from archkeel.ir.graph_codec import parse_report
    from archkeel.render.html import render_architecture_details

    root, config = _nested_repository(tmp_path)
    raw = json.loads((root / config.contract).read_bytes())
    raw["components"][0]["id"] = component_id
    (root / config.contract).write_text(json.dumps(raw))
    inner = json.loads((root / "inside.json").read_bytes())
    inner["components"][0].update(packages=["sample.future"], namespace="sample.future")
    (root / "inside.json").write_text(json.dumps(inner))
    _, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    data = _atlas(_page(model))
    level = next(item for item in data["levels"] if item["parent_id"] == component_id)
    module = next(item for item in data["modules"] if item["name"] == "sample.core")
    assignment = next(item for item in level["modules"] if item["id"] == module["id"])
    assert assignment["component_id"] is None and assignment["ownership_status"] == "UNKNOWN"
    assert any(module["id"] in item.module_ids for item in architecture_report(model).memberships)
    pages = render_architecture_details(
        _result(model), encoded, repository="One target", architecture_href="architecture.json"
    )
    component_href = next(
        item["detail_href"] for item in data["components"] if item["id"] == component_id
    )
    assert component_href != data["unassigned_detail_href"]
    assert component_href in pages and data["unassigned_detail_href"] in pages
    text = pages[data["unassigned_detail_href"]].decode()
    payload = re.search(
        r'<script id="flow-data" type="application/json">(.*?)</script>', text, re.S
    )
    native = json.loads(payload.group(1))
    native.pop("initial_scope")
    native.pop("initial_view")
    native.pop("navigation")
    scoped = parse_report(native)
    scoped.validate()
    original = architecture_report(model).observed
    wanted = {
        item
        for item in original.entities
        if item.id == module["id"] or item.parent_id == module["id"]
    }
    assert wanted <= set(scoped.observed.entities)
    api = pytest.importorskip("playwright.sync_api")
    index = tmp_path / "architecture.report.html"
    index.write_text(_page(model))
    for name, content in pages.items():
        (tmp_path / name).write_bytes(content)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri())
        page.locator(f'.flow-nodes [data-uml-id="{component_id}"]').dblclick()
        page.locator(".atlas-module-list > summary").click()
        page.locator(".atlas-module-list").get_by_role(
            "link", name="sample.core", exact=True
        ).click()
        assert data["unassigned_detail_href"] in page.url
        assert page.locator('.flow-nodes [data-label="Service"]').count() == 1
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        assert page.url.startswith(index.as_uri())
        assert "scope=" in page.url
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def _route_pages(tmp_path):
    from archkeel.render.html import render_architecture_details

    model = _sample(
        tmp_path,
        core_exact=("sample.empty",),
        extra_files={
            "sample/empty.py": "",
            "sample/core.py": (
                "from enum import Enum\nLIMIT = 3\n"
                "class Client:\n    def run(self):\n        return LIMIT\n"
                "class State(Enum):\n    READY = 'ready'\n"
            ),
        },
    )
    index = tmp_path / "architecture.report.html"
    index.write_text(_page(model))
    for name, content in render_architecture_details(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).items():
        (tmp_path / name).write_bytes(content)
    return index, architecture_report(model).observed


def test_offline_atlas_and_uml_share_shell_empty_scope_and_url_theme(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    index, graph = _route_pages(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri() + "?theme=dark")
        page.locator('.flow-nodes [data-label="core"]').press("Enter")
        page.get_by_role("button", name="Switch to light theme", exact=True).click()
        page.locator(".atlas-module-list").get_by_role(
            "link", name="sample.empty", exact=True
        ).click()
        assert page.locator(".atlas-heading").count() == 1
        assert page.locator(".flow-views [data-flow-view]").count() == 3
        assert page.locator(".theme-toggle").count() == 1
        assert page.locator("html").get_attribute("data-theme") == "light"
        assert "No direct declarations" in page.locator(".flow-alternative").inner_text()
        assert "sample/empty.py" in page.locator(".flow-alternative").inner_text()
        empty = next(item for item in graph.entities if item.qualified_name == "sample.empty")
        assert "module=" + empty.id in page.url
        page.reload()
        assert page.locator("html").get_attribute("data-theme") == "light"
        for lens in ("Target", "Diff", "As-Is"):
            page.get_by_role("button", name=lens, exact=True).click()
            assert "module=" + empty.id in page.url
            assert page.locator('.flow-nodes [data-uml-kind="component"]').count() == 0
        page.get_by_role("link", name="Back to architecture map", exact=True).click()
        assert "scope=core" in page.url and "theme=light" in page.url
        assert page.locator("#flow-heading").inner_text() == "Architecture map · core"
        page.get_by_role("button", name="Target", exact=True).click()
        assert "No declared subcomponents" in page.locator(".flow-alternative").inner_text()
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_offline_scope_url_history_matches_direct_classifier_and_members(tmp_path):
    api = pytest.importorskip("playwright.sync_api")
    index, graph = _route_pages(tmp_path)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri())
        page.locator('.flow-nodes [data-label="core"]').press("Enter")
        page.locator(".atlas-module-list").get_by_role(
            "link", name="sample.core", exact=True
        ).click()
        module = next(item for item in graph.entities if item.qualified_name == "sample.core")
        classifier = next(
            item for item in graph.entities if item.qualified_name == "sample.core.Client"
        )
        method = next(
            item for item in graph.entities if item.qualified_name == "sample.core.Client.run"
        )
        page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]').press("Enter")
        assert "module=" + module.id in page.url and "scope=" + classifier.id in page.url
        page.reload()
        assert page.locator(f'.flow-nodes [data-uml-id="{method.id}"]').count() == 1
        assert "Client [class]" in page.locator(".flow-breadcrumb").inner_text()
        page.locator(".flow-back").click()
        assert "scope=" + classifier.id not in page.url
        page.go_back()
        assert "scope=" + classifier.id in page.url
        assert page.locator(f'.flow-nodes [data-uml-id="{method.id}"]').count() == 1
        page.goto(page.url.replace(classifier.id, "unknown-native-id"))
        assert "scope=unknown-native-id" not in page.url
        assert page.locator(f'.flow-nodes [data-uml-id="{classifier.id}"]').count() == 1
        assert not errors
    finally:
        browser.close()
        playwright.stop()


def test_target_counterpart_and_planned_classifier_open_declared_members(tmp_path):
    from test_target_graph import _contract
    from test_uml_evaluation import _model, _repository

    from archkeel.render.html import render_architecture_details

    api = pytest.importorskip("playwright.sync_api")
    contract = _contract()
    entities = contract["declarations"]["uml"]["entities"]
    entities[0]["parent_id"] = "declared-module"
    context = {
        "presence": "planned",
        "language": "python",
        "provenance": ["docs/target.md"],
        "responsibilities": ["Own the declared operation."],
    }
    entities.extend(
        [
            {
                **context,
                "id": "declared-module",
                "kind": "module",
                "qualified_name": "sample.core",
                "parent_id": "core",
            },
            {
                **context,
                "id": "future",
                "kind": "class",
                "qualified_name": "sample.core.Future",
                "parent_id": "declared-module",
            },
            {
                **context,
                "id": "execute",
                "kind": "method",
                "qualified_name": "sample.core.Future.execute",
                "parent_id": "future",
            },
        ]
    )
    root, config = _repository(
        tmp_path,
        contract=contract,
        source="class Service:\n    def run(self, request):\n        return request\n",
    )
    model = _model(root, config)
    index = tmp_path / "architecture.report.html"
    index.write_text(_page(model))
    for name, content in render_architecture_details(
        _result(model),
        canonical_report_bytes(model),
        repository="One target",
        architecture_href="architecture.json",
    ).items():
        (tmp_path / name).write_bytes(content)
    errors = []
    playwright, browser, page = _browser_page(api, index.read_text(), errors=errors)
    try:
        page.goto(index.as_uri() + "?theme=dark")
        page.locator('.flow-nodes [data-label="core"]').press("Enter")
        page.locator(".atlas-module-list").get_by_role(
            "link", name="sample.core", exact=True
        ).click()
        page.get_by_role("button", name="Target", exact=True).click()
        for identity, member in (("service", "run"), ("future", "execute")):
            page.locator(f'.flow-nodes [data-uml-id="{identity}"]').press("Enter")
            assert "origin=declared" in page.url and "scope=" + identity in page.url
            page.reload()
            assert (
                page.get_by_role("button", name="Target", exact=True).get_attribute("aria-pressed")
                == "true"
            )
            assert page.locator(f'.flow-nodes [data-uml-id="{member}"]').count() == 1
            assert page.locator('.flow-nodes [data-uml-kind="component"]').count() == 0
            page.locator(".flow-back").click()
        assert not errors
    finally:
        browser.close()
        playwright.stop()
