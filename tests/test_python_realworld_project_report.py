# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Full-source replays for the pinned Python RealWorld Target."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from archkeel.ir.graph_codec import parse_report
from fixtures.architecture_demo import CATALOG, REPORT_CASES, UML_DEMO_COMPARISONS, replay
from fixtures.demo_catalog_python_realworld import (
    PYTHON_REALWORLD_FIXTURE_DIR,
    VARIANTS,
)

ROOT = Path(__file__).parents[1]
TARGET_FILES = (
    "architecture-contract.json",
    "contracts/host-runtime.json",
    "contracts/http-interface.json",
    "contracts/product-policy.json",
    "contracts/product-contracts.json",
    "contracts/postgres-adapter.json",
)
TARGET_DIGEST = "5dcc89c72c96c49f80524b86137a4aba103bbe604f83bc2518aa542c6fa0519d"
SOURCE_DIGESTS = {
    "python-realworld-project": (
        "177b3854b42b7edd5ffad71c95d167aba3086013686d9a964e198bb079d047ce"
    ),
    "python-realworld-forbidden-edge": (
        "0749ba49669a5b41cf4eee83be56b0f7f5992d4028f69f8d9200a9cbec80a549"
    ),
    "python-realworld-signature-fail": (
        "6f8eb84c8afd9f164d138baf7438b2bda25b76f18c82489e6cd000cd6250fac1"
    ),
    "python-realworld-dynamic-unknown": (
        "b1e0e0fcac35279821dd4a1d3f88d49661ac5c77bf2223e3c7d8db7bb4032cc5"
    ),
}
EXPECTED_ASSESSMENT_STATUSES = {
    "python-realworld-project": Counter(PASS=1195, UNKNOWN=47, FAIL=0),
    "python-realworld-forbidden-edge": Counter(PASS=1195, UNKNOWN=47, FAIL=0),
    "python-realworld-signature-fail": Counter(PASS=1194, UNKNOWN=47, FAIL=1),
    "python-realworld-dynamic-unknown": Counter(PASS=1194, UNKNOWN=48, FAIL=0),
}
EXPECTED_UNKNOWN_ASPECTS = {
    "python-realworld-project": Counter(relationship=13, completeness=34),
    "python-realworld-forbidden-edge": Counter(relationship=13, completeness=34),
    "python-realworld-signature-fail": Counter(relationship=13, completeness=34),
    "python-realworld-dynamic-unknown": Counter(relationship=14, completeness=34),
}


def _payload(html: Path) -> dict:
    match = re.search(
        r'<script[^>]*id="flow-data"[^>]*>(.*?)</script>',
        html.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert match
    return json.loads(match.group(1))


def _report(output: Path):
    main = output.with_suffix(".report.html")
    atlas = _payload(main)["atlas"]
    detail = main.with_name(atlas["detail_page"])
    data = _payload(detail)
    assert data["navigation"]["main_href"] == main.name
    return parse_report(
        {
            key: value
            for key, value in data.items()
            if key not in {"initial_scope", "initial_view", "navigation"}
        }
    )


def _assess(report, subject_id: str, aspect: str):
    assert report.comparison is not None
    return next(
        item
        for item in report.comparison.assessments
        if item.subject_id == subject_id and item.aspect == aspect
    )


def test_python_realworld_variants_are_source_only_and_keep_all_upstream_inputs() -> None:
    expected = {
        "python-realworld-project",
        "python-realworld-forbidden-edge",
        "python-realworld-signature-fail",
        "python-realworld-dynamic-unknown",
    }
    assert {item.id for item in VARIANTS} == expected
    assert {item.id for item in CATALOG if item.id.startswith("python-realworld-")} == expected
    assert {key for key, (variant_id, _) in REPORT_CASES.items() if variant_id in expected} == {
        f"uml-{variant_id}" for variant_id in expected
    }
    assert {
        key: UML_DEMO_COMPARISONS[key]
        for key in UML_DEMO_COMPARISONS
        if key.startswith("uml-python-realworld-")
    } == {
        "uml-python-realworld-project": "UNKNOWN",
        "uml-python-realworld-forbidden-edge": "UNKNOWN",
        "uml-python-realworld-signature-fail": "FAIL",
        "uml-python-realworld-dynamic-unknown": "UNKNOWN",
    }

    snapshot = json.loads((PYTHON_REALWORLD_FIXTURE_DIR / "SNAPSHOT.json").read_bytes())
    app_files = {
        item["path"]: item for item in snapshot["files"] if item["path"].startswith("app/")
    }
    python_paths = {path for path in app_files if path.endswith(".py")}
    assert len(app_files) == 79
    assert len(python_paths) == 72
    for variant in VARIANTS:
        assert variant.fixture == PYTHON_REALWORLD_FIXTURE_DIR
        changed_paths = set(variant.files)
        assert changed_paths <= python_paths
        for relative, item in app_files.items():
            if relative not in changed_paths:
                assert (
                    hashlib.sha256(
                        (PYTHON_REALWORLD_FIXTURE_DIR / relative).read_bytes()
                    ).hexdigest()
                    == item["sha256"]
                )
        for relative, content in variant.files.items():
            assert content is not None
            assert content != (PYTHON_REALWORLD_FIXTURE_DIR / relative).read_text()

    target_digest = hashlib.sha256(
        b"".join((PYTHON_REALWORLD_FIXTURE_DIR / path).read_bytes() for path in TARGET_FILES)
    ).hexdigest()
    assert target_digest == TARGET_DIGEST
    assert f"Target bundle SHA-256: `{TARGET_DIGEST}`" in (
        PYTHON_REALWORLD_FIXTURE_DIR / "docs/target.md"
    ).read_text(encoding="utf-8")
    variants = {item.id: item for item in VARIANTS}
    edge = variants["python-realworld-forbidden-edge"].files
    assert set(edge) == {"app/api/routes/articles/articles_resource.py"}
    assert (
        "from app.db.queries.queries import queries"
        in edge["app/api/routes/articles/articles_resource.py"]
    )
    signature = variants["python-realworld-signature-fail"].files
    assert signature["app/models/domain/articles.py"].count("tags: List[int]") == 1
    assert signature["app/models/domain/articles.py"].count("tags: List[str]") == 0
    dynamic = variants["python-realworld-dynamic-unknown"].files["app/api/routes/authentication.py"]
    login, register = dynamic.split("async def register", maxsplit=1)
    assert 'getattr(jwt, "create_access_token_for_user")' in login
    assert "token = jwt.create_access_token_for_user(" in register


def test_python_realworld_reports_keep_coverage_architecture_and_uml_distinct(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    expected = {
        "python-realworld-project": ("UNKNOWN", "UNKNOWN", 0),
        "python-realworld-forbidden-edge": ("FAIL", "UNKNOWN", 2),
        "python-realworld-signature-fail": ("FAIL", "FAIL", 2),
        "python-realworld-dynamic-unknown": ("UNKNOWN", "UNKNOWN", 0),
    }
    reports = {}
    target_digests = set()
    target_module_sets = set()
    observed_module_sets = set()
    for variant_id, (rules_status, comparison_status, replay_exit) in expected.items():
        assert REPORT_CASES[f"uml-{variant_id}"] == (variant_id, replay_exit)
        output = tmp_path / f"{variant_id}.json"
        assert replay(variant_id, output) == REPORT_CASES[f"uml-{variant_id}"][1]
        summaries = [
            json.loads(line)
            for line in capsys.readouterr().out.splitlines()
            if line.startswith("{") and line.endswith("}")
        ]
        validate_summary = next(item for item in summaries if item.get("command") == "validate")
        report_summary = next(item for item in summaries if item.get("command") == "report")
        assert validate_summary["exit_code"] == replay_exit
        assert report_summary["exit_code"] == 0
        assert report_summary["observation_complete"] == "PASS"
        assert report_summary["declared_rules"] == rules_status
        assert report_summary["coverage"]["status"] == "PASS"
        assert report_summary["coverage"]["files_discovered"] == 72
        assert report_summary["coverage"]["files_read"] == 72
        assert report_summary["coverage"]["files_parsed"] == 72
        assert report_summary["coverage"]["ast_coverage_percent"] == 100.0
        assert report_summary["coverage"]["failures"] == []

        raw = json.loads(output.read_text(encoding="utf-8"))
        assert raw["source"]["source_digest"] == SOURCE_DIGESTS[variant_id]
        target_digests.add(raw["contract"]["digest"])
        assert output.with_suffix(".report.html").is_file()
        assert output.with_suffix(".detail.html").is_file()
        report = _report(output)
        assert report.comparison is not None
        assert report.comparison.status == comparison_status
        assert len(report.comparison.assessments) == 1242
        assert (
            Counter(item.status for item in report.comparison.assessments)
            == (EXPECTED_ASSESSMENT_STATUSES[variant_id])
        )
        assert (
            Counter(
                item.aspect for item in report.comparison.assessments if item.status == "UNKNOWN"
            )
            == EXPECTED_UNKNOWN_ASPECTS[variant_id]
        )
        assert len(report.target.entities) == 329
        assert len(report.target.relationships) == 259
        assert sum(item.kind == "imports" for item in report.target.relationships) == 170
        modules = frozenset(
            item.file_path for item in report.target.entities if item.kind == "module"
        )
        assert len(modules) == 72
        target_module_sets.add(modules)
        observed_modules = frozenset(
            item.file_path for item in report.observed.entities if item.kind == "module"
        )
        assert len(observed_modules) == 72
        observed_module_sets.add(observed_modules)
        reports[variant_id] = (raw, report)

    assert len(target_digests) == 1
    assert len(target_module_sets) == 1
    assert len(observed_module_sets) == 1
    snapshot = json.loads((PYTHON_REALWORLD_FIXTURE_DIR / "SNAPSHOT.json").read_bytes())
    expected_modules = {
        item["path"]
        for item in snapshot["files"]
        if item["path"].startswith("app/") and item["path"].endswith(".py")
    }
    assert next(iter(target_module_sets)) == expected_modules
    assert next(iter(observed_module_sets)) == expected_modules

    article_tags_id = next(
        item.id
        for item in reports["python-realworld-project"][1].target.entities
        if item.qualified_name == "app.models.domain.articles.Article.tags"
    )
    baseline_tags = _assess(reports["python-realworld-project"][1], article_tags_id, "annotation")
    changed_tags = _assess(
        reports["python-realworld-signature-fail"][1], article_tags_id, "annotation"
    )
    assert (baseline_tags.status, changed_tags.status) == ("PASS", "FAIL")
    assert baseline_tags.evidence_ids == changed_tags.evidence_ids == ("EVD-c2388a9ba3d25a6a",)

    call_id = "login-creates-access-token"
    baseline_call = _assess(reports["python-realworld-project"][1], call_id, "relationship")
    dynamic_call = _assess(reports["python-realworld-dynamic-unknown"][1], call_id, "relationship")
    assert (baseline_call.status, dynamic_call.status) == ("PASS", "UNKNOWN")
    assert baseline_call.evidence_ids == ("EVD-88d03eb1dba95d8e",)
    assert set(baseline_call.evidence_ids) <= set(dynamic_call.evidence_ids)

    forbidden = reports["python-realworld-forbidden-edge"][0]["violations"]
    assert len(forbidden) == 1
    assert forbidden[0][7] == ["REQUIRES-COMPLETE"]
    assert forbidden[0][6] == ["EVD-9ce79f4676056d33"]


def test_python_realworld_report_browses_deep_target_at_desktop_and_mobile(
    tmp_path: Path,
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    output = tmp_path / "python-realworld-project.json"
    assert replay("python-realworld-project", output) == 0
    screenshots = tmp_path / "screenshots"
    screenshots.mkdir()

    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            main = output.with_suffix(".report.html")
            page.goto(main.as_uri())
            atlas = _payload(main)["atlas"]
            assert atlas["detail_page"] == output.with_suffix(".detail.html").name

            page.locator('.flow-nodes [data-uml-id="product-contracts"]').click()
            page.get_by_text("Browse 18 modules", exact=True).click()
            page.locator('[data-content="components"]').last.click()
            page.locator(
                '.flow-nodes [data-uml-id="Product and wire contracts:contracts-publishing"]'
            ).press("Enter")

            atlas = _payload(main)["atlas"]
            module = next(
                item for item in atlas["modules"] if item["path"] == "app/models/domain/articles.py"
            )
            page.locator(f'.flow-nodes [data-uml-id="{module["id"]}"]').dblclick()
            page.wait_for_url("**/*.detail.html?*")
            module_url = page.url
            assert page.locator(".atlas-heading").is_visible()
            assert page.locator(".flow-views [data-flow-view]").count() == 3

            for width in (1440, 390):
                page.set_viewport_size({"width": width, "height": 900})
                for view in ("diagram", "target", "diff"):
                    page.goto(module_url)
                    page.locator(f'[data-flow-view="{view}"]').click()
                    page.locator('.flow-nodes [data-label="Article"]').dblclick()
                    tags = page.locator('.flow-nodes [data-label="tags"]')
                    assert tags.count() == 1
                    tags.press("Space")
                    inspector = page.locator(".flow-inspector-content").inner_text()
                    assert "tags" in inspector
                    assert "app/models/domain/articles.py" in inspector
                    if view == "diagram":
                        assert "SOURCE SITES" in inspector
                        assert "articles.py:13:4" in inspector
                        assert "tags: List[str]" in inspector
                    elif view == "target":
                        assert "docs/target.md" in inspector
                        assert "List[str]" in inspector
                    else:
                        assert "SOURCE SITES" in inspector
                        assert "articles.py:13:4" in inspector
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.locator(".flow-canvas").scroll_into_view_if_needed()
                    page.locator(".flow-canvas").evaluate(
                        "canvas => { canvas.scrollTop = 0; canvas.scrollLeft = 0; }"
                    )
                    page.screenshot(
                        path=str(screenshots / f"python-realworld-{width}-{view}.png"),
                        full_page=False,
                    )
        finally:
            browser.close()
            playwright.stop()


def test_python_http_module_scope_preserves_nested_ownership_and_target_routes(
    tmp_path: Path,
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    output = tmp_path / "python-realworld-project.json"
    assert replay("python-realworld-project", output) == 0
    main = output.with_suffix(".report.html")
    atlas = _payload(main)["atlas"]
    scope_id = "http-interface"
    components = {component["id"]: component for component in atlas["components"]}

    def in_scope(component_id: str, scope: str = scope_id) -> bool:
        while component_id:
            if component_id == scope:
                return True
            component_id = components[component_id]["parent_id"]
        return False

    scoped_modules = [
        module for module in atlas["declared_modules"] if in_scope(module["component_id"])
    ]
    expected_ids = {module["id"] for module in scoped_modules}
    expected_edges = {
        edge["id"]
        for module in scoped_modules
        for edge in module["relationships"]
        if edge["target_id"] in expected_ids
    }
    assert len(expected_ids) == 21 and len(expected_edges) == 31
    target_boundary_count = len(
        {
            edge["id"]
            for module in atlas["declared_modules"]
            for edge in module["relationships"]
            if (module["id"] in expected_ids) != (edge["target_id"] in expected_ids)
        }
    )

    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(main.as_uri())
            page.locator('[data-flow-view="target"]').click()
            page.locator(f'.flow-nodes [data-uml-id="{scope_id}"]').press("Enter")
            modules = page.locator('.atlas-content-choice [data-content="modules"]')
            if modules.is_visible():
                modules.click()
            page.wait_for_function(
                "() => document.querySelectorAll('[data-uml-kind=module]').length === 21"
            )

            observed = page.locator('.flow-nodes [data-uml-kind="module"]').evaluate_all(
                "nodes => nodes.map(node => node.dataset.umlId)"
            )
            assert set(observed) == expected_ids
            assert page.locator('.flow-frames [data-uml-kind="component"]').count() > 1
            assert (
                f"{target_boundary_count} cross-scope relationship"
                in page.locator(".atlas-summary").inner_text()
            )
            routes = page.locator(".flow-edges > g[data-uml-source]").evaluate_all("""groups =>
              groups.map(group => {
                const path = group.querySelector('.line');
                const endpoint = distance => {
                  const point = path.getPointAtLength(distance);
                  return new DOMPoint(point.x, point.y).matrixTransform(path.getScreenCTM());
                };
                const start = endpoint(0), end = endpoint(path.getTotalLength());
                const source = document.querySelector(`[data-uml-id="${group.dataset.umlSource}"]`)
                  .getBoundingClientRect();
                const target = document.querySelector(`[data-uml-id="${group.dataset.umlTarget}"]`)
                  .getBoundingClientRect();
                const inside = (point, box) => point.x >= box.left - 3 && point.x <= box.right + 3
                  && point.y >= box.top - 3 && point.y <= box.bottom + 3;
                return {
                  id: group.dataset.umlId,
                  sourceId: group.dataset.umlSource,
                  targetId: group.dataset.umlTarget,
                  start: inside(start, source), end: inside(end, target),
                  sourceDelta: [start.x - source.x, start.y - source.y],
                  targetDelta: [end.x - target.x, end.y - target.y],
                  sourceSize: [source.width, source.height],
                  targetSize: [target.width, target.height],
                };
              })""")
            assert {edge["id"] for edge in routes} == expected_edges
            assert all(edge["start"] and edge["end"] for edge in routes), [
                (
                    edge["id"],
                    edge["sourceId"],
                    edge["targetId"],
                    edge["sourceDelta"],
                    edge["targetDelta"],
                )
                for edge in routes
                if not edge["start"] or not edge["end"]
            ]
            assert page.locator(".atlas-edge-label").count() == 0
            assert page.locator(".flow-edges .hit[aria-label]").count() == len(expected_edges)

            frame_ids = page.locator('.flow-frames [data-uml-kind="component"]').evaluate_all(
                "frames => frames.map(frame => frame.dataset.umlId)"
            )
            assert frame_ids
            deep_id = next(item for item in frame_ids if item.endswith(":http-publishing"))
            owner_colors = page.locator('.flow-frames [data-uml-kind="component"]').evaluate_all(
                """frames => Object.fromEntries(frames.map(frame => [
                  frame.dataset.umlId, frame.dataset.ownerColor]))"""
            )
            assert all(value is not None for value in owner_colors.values())
            zoom = page.locator(".flow-zoom-value")
            assert int(zoom.inner_text().rstrip("%")) >= 100
            page.get_by_role("button", name="Fit overview").click()
            page.wait_for_function(
                "() => parseInt(document.querySelector('.flow-zoom-value').textContent) < 100"
            )
            overview_scale = int(zoom.inner_text().rstrip("%"))
            page.get_by_role("button", name="Zoom in").click()
            assert int(zoom.inner_text().rstrip("%")) > overview_scale
            for view in ("diagram", "diff"):
                page.locator(f'[data-flow-view="{view}"]').click()
                page.wait_for_function(
                    "() => document.querySelectorAll('[data-uml-kind=component]').length > 1"
                )
                current_level = next(
                    item for item in atlas["levels"] if item["parent_id"] == scope_id
                )
                observed_ids = {
                    atlas["modules"][atlas["assignments"][index][0]]["id"]
                    for index in current_level["modules"]
                }
                observed_boundary_count = len(
                    {
                        (atlas["modules"][cell[0]]["id"], atlas["modules"][cell[1]]["id"])
                        for cell in atlas["cells"]
                        if (atlas["modules"][cell[0]]["id"] in observed_ids)
                        != (atlas["modules"][cell[1]]["id"] in observed_ids)
                    }
                )
                assert (
                    f"{observed_boundary_count} cross-scope relationship"
                    in page.locator(".atlas-summary").inner_text()
                )
                next_colors = page.locator('.flow-frames [data-uml-kind="component"]').evaluate_all(
                    """frames => Object.fromEntries(frames.map(frame => [
                      frame.dataset.umlId, frame.dataset.ownerColor]))"""
                )
                assert all(
                    next_colors[key] == value
                    for key, value in owner_colors.items()
                    if key in next_colors
                )
                if view == "diagram":
                    first_relationship = page.locator(".flow-edges .hit[aria-label]").first
                    first_relationship.press("Enter")
                    assert page.get_by_text("Observed import cell", exact=True).is_visible()
                    assert page.get_by_text("Permission:", exact=False).is_visible()
            page.locator('[data-flow-view="target"]').click()
            page.wait_for_function(
                "() => document.querySelectorAll('[data-uml-kind=component]').length > 1"
            )
            page.locator(f'.flow-frames [data-uml-id="{deep_id}"]').press("Enter")
            page.wait_for_function(
                "id => new URLSearchParams(location.search).get('scope') === id", arg=deep_id
            )
            page.wait_for_function(
                "() => document.querySelectorAll('.flow-nodes [data-uml-kind=module]').length > 1"
            )
            deep_modules = {
                module["id"]
                for module in atlas["declared_modules"]
                if in_scope(module["component_id"], deep_id)
            }
            assert len(deep_modules) > 1
            assert (
                set(
                    page.locator('.flow-nodes [data-uml-kind="module"]').evaluate_all(
                        "nodes => nodes.map(node => node.dataset.umlId)"
                    )
                )
                == deep_modules
            )
            page.locator('[data-atlas-depth="1"]').click()
            page.locator('.atlas-content-choice [data-content="modules"]').click()
            page.wait_for_function(
                "() => document.querySelectorAll('.flow-nodes [data-uml-kind=module]').length > 1"
            )
            header = page.locator(
                f'.flow-frames [data-uml-id="{deep_id}"] .target-frame-header-hit'
            )
            header.click()
            page.wait_for_function(
                "id => new URLSearchParams(location.search).get('scope') === id", arg=deep_id
            )
            toggle = page.locator(".flow-details-toggle")
            expanded = toggle.get_attribute("aria-expanded")
            toggle.click()
            assert toggle.get_attribute("aria-expanded") != expanded
            page.wait_for_function(
                "() => document.querySelectorAll('.flow-nodes [data-uml-kind=module]').length > 1"
            )
            assert (
                set(
                    page.locator('.flow-nodes [data-uml-kind="module"]').evaluate_all(
                        "nodes => nodes.map(node => node.dataset.umlId)"
                    )
                )
                == deep_modules
            )

            page.locator('[data-atlas-depth="1"]').click()
            page.wait_for_function(
                "id => new URLSearchParams(location.search).get('scope') === id",
                arg=scope_id,
            )
            modules = page.locator('.atlas-content-choice [data-content="modules"]')
            if modules.is_visible():
                modules.click()
            page.wait_for_function(
                "() => document.querySelectorAll('[data-uml-kind=module]').length === 21"
            )
            identity_scope = "RealWorld HTTP interface:http-identity"
            identity_modules = {
                module["id"]
                for module in atlas["declared_modules"]
                if in_scope(module["component_id"], identity_scope)
            }
            assert identity_modules
            retry_scope = next(
                component["id"]
                for component in atlas["components"]
                if component["parent_id"] == scope_id
                and component["id"] not in {identity_scope, deep_id}
            )
            retry_modules = {
                module["id"]
                for module in atlas["declared_modules"]
                if in_scope(module["component_id"], retry_scope)
            }
            assert retry_modules
            assert page.evaluate("typeof window.ELK") == "function"
            page.evaluate("""() => {
              const prototype = window.ELK.prototype;
              window.__originalAtlasLayout = prototype.layout;
              window.__atlasLayoutCalls = 0;
              prototype.layout = function(graph) {
                window.__atlasLayoutCalls += 1;
                if (window.__atlasLayoutCalls === 1) {
                  return new Promise((resolve, reject) => {
                    window.__resolveAtlasLayout = async () => resolve(
                      await window.__originalAtlasLayout.call(this, graph));
                  });
                }
                if (window.__atlasLayoutCalls === 2) {
                  return new Promise((resolve, reject) => {
                    window.__rejectAtlasLayout = () => reject(new Error("stale layout"));
                  });
                }
                return window.__originalAtlasLayout.call(this, graph);
              };
            }""")
            page.locator(f'.flow-frames [data-uml-id="{identity_scope}"]').press("Enter")
            page.wait_for_function(
                "id => new URLSearchParams(location.search).get('scope') === id",
                arg=identity_scope,
            )
            page.wait_for_function("() => typeof window.__resolveAtlasLayout === 'function'")
            page.locator('[data-atlas-depth="1"]').click()
            page.wait_for_function(
                "id => new URLSearchParams(location.search).get('scope') === id",
                arg=scope_id,
            )
            page.locator('.atlas-content-choice [data-content="modules"]').click()
            page.wait_for_function(
                "() => document.querySelectorAll('[data-uml-kind=module]').length === 21"
            )
            page.locator(f'.flow-frames [data-uml-id="{retry_scope}"]').press("Enter")
            page.wait_for_function(
                "id => new URLSearchParams(location.search).get('scope') === id",
                arg=retry_scope,
            )
            page.wait_for_function("() => typeof window.__rejectAtlasLayout === 'function'")
            page.locator('[data-atlas-depth="1"]').click()
            page.wait_for_function(
                "id => new URLSearchParams(location.search).get('scope') === id",
                arg=scope_id,
            )
            page.locator('.atlas-content-choice [data-content="modules"]').click()
            page.wait_for_function(
                "() => document.querySelectorAll('[data-uml-kind=module]').length === 21"
            )
            page.evaluate("""async () => {
              window.__rejectAtlasLayout();
              await new Promise(resolve => requestAnimationFrame(
                () => requestAnimationFrame(resolve)));
            }""")
            assert parse_qs(urlsplit(page.url).query).get("scope") == [scope_id]
            assert page.locator('.flow-nodes [data-uml-kind="module"]').count() == 21
            page.locator(f'.flow-frames [data-uml-id="{retry_scope}"]').press("Enter")
            page.wait_for_function(
                "id => new URLSearchParams(location.search).get('scope') === id",
                arg=retry_scope,
            )
            page.wait_for_function("() => typeof window.__rejectAtlasLayout === 'function'")
            page.wait_for_function(
                "count => document.querySelectorAll('[data-uml-kind=module]').length === count",
                arg=len(retry_modules),
            )
            page.evaluate("""async () => {
              await window.__resolveAtlasLayout();
              await new Promise(resolve => requestAnimationFrame(
                () => requestAnimationFrame(resolve)));
            }""")
            assert page.evaluate("window.__atlasLayoutCalls") == 3
            assert (
                set(
                    page.locator('.flow-nodes [data-uml-kind="module"]').evaluate_all(
                        "nodes => nodes.map(node => node.dataset.umlId)"
                    )
                )
                == retry_modules
            )
            page.evaluate("""() => {
              window.ELK.prototype.layout = window.__originalAtlasLayout;
            }""")
        finally:
            browser.close()


def test_python_realworld_module_overview_uses_actual_edges_and_keeps_isolated_routes(
    tmp_path: Path,
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    output = tmp_path / "python-realworld-project.json"
    assert replay("python-realworld-project", output) == 0
    main = output.with_suffix(".report.html")
    original_html = main.read_text(encoding="utf-8")

    # Keep a tiny edge-less control to ensure isolated modules stay rendered.
    data = _payload(main)
    control = data["atlas"]
    root_level = next(level for level in control["levels"] if level["parent_id"] is None)
    assignment_indexes = root_level["modules"][:4]
    module_ids = {
        control["modules"][control["assignments"][index][0]]["id"] for index in assignment_indexes
    }
    control["declared_modules"] = [
        module for module in control["declared_modules"] if module["id"] in module_ids
    ]
    root_id = "__archkeel_atlas_layout_root__"
    first_module = control["modules"][control["assignments"][assignment_indexes[0]][0]]
    old_id = first_module["id"]
    first_module["id"] = root_id
    shared_module = control["modules"][control["assignments"][assignment_indexes[1]][0]]
    shared_old_id = shared_module["id"]
    owner_index = control["assignments"][assignment_indexes[1]][1]
    shared_module["id"] = control["reference_ids"][owner_index]
    for module in control["declared_modules"]:
        if module["id"] == old_id:
            module["id"] = root_id
        elif module["id"] == shared_old_id:
            module["id"] = shared_module["id"]
    for module in control["declared_modules"]:
        module["relationships"] = []
    root_level["modules"] = assignment_indexes
    root_level["cells"] = []
    root_level["component_ids"] = []
    root_level["questions"] = []
    control_html = re.sub(
        r'(<script[^>]*id="flow-data"[^>]*>)(.*?)(</script>)',
        lambda match: match.group(1) + json.dumps(data, separators=(",", ":")) + match.group(3),
        original_html,
        count=1,
        flags=re.DOTALL,
    )
    control_path = tmp_path / "edgeless-atlas.html"
    control_path.write_text(control_html, encoding="utf-8")

    atlas = _payload(main)["atlas"]
    level = next(item for item in atlas["levels"] if item["parent_id"] is None)
    observed_modules = {
        atlas["modules"][atlas["assignments"][index][0]]["id"] for index in level["modules"]
    }
    target_modules = {module["id"] for module in atlas["declared_modules"]}
    assert len(observed_modules) == len(target_modules) == 72

    screenshots = tmp_path / "module-overview"
    screenshots.mkdir()
    errors: list[str] = []
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("pageerror", lambda error: errors.append(str(error)))

            page.goto(main.as_uri())
            page.locator('[data-flow-view="diagram"]').click()
            assert page.locator('.flow-nodes [data-uml-kind="component"]').count() == 5
            assert page.locator(".atlas-module-inventory-label").count() == 0

            def geometry() -> dict:
                return page.evaluate("""() => ({
                  width: innerWidth,
                  documentWidth: document.documentElement.scrollWidth,
                  canvasWidth: document.querySelector('.flow-canvas').clientWidth,
                  cards: [...document.querySelectorAll('.flow-nodes [data-uml-kind="module"]')]
                    .map(node => ({id: node.dataset.umlId, inventory: node.dataset.moduleInventory,
                      transform: node.getAttribute('transform')})),
                  edges: [...document.querySelectorAll('.flow-edges > g[data-uml-source]')]
                    .map(edge => [edge.dataset.umlSource, edge.dataset.umlTarget]),
                  routeWarnings: document.querySelectorAll(
                    '.flow-edges [data-route-warning]'
                  ).length,
                  summary: document.querySelector('.atlas-summary').textContent,
                  inventory: document.querySelector('.atlas-module-inventory-label')?.textContent
                    || null
                    })""")

            def scale() -> float:
                return page.locator(".flow-canvas svg").evaluate(
                    "svg => parseFloat(svg.style.height) / svg.viewBox.baseVal.height"
                )

            def open_modules(path: Path, view: str) -> None:
                page.goto(path.as_uri())
                page.locator(f'[data-flow-view="{view}"]').click()
                modules_button = page.locator('.atlas-content-choice [data-content="modules"]')
                if modules_button.is_visible():
                    modules_button.click()

            # Every isolated module stays visible without inventing a relationship.
            open_modules(control_path, "diagram")
            for width in (1440, 390):
                page.set_viewport_size({"width": width, "height": 900})
                page.wait_for_function(
                    "() => document.querySelectorAll('[data-uml-kind=module]').length === 4"
                )
                state = geometry()
                assert len(state["cards"]) == 4
                assert state["edges"] == []
                assert "4 observed modules" in state["summary"]
                assert "0 local dependencies" in state["summary"]
                assert state["inventory"] is None
                assert all(card["inventory"] == "true" for card in state["cards"])
                assert state["documentWidth"] <= state["width"], state
                shared_selector = f'[data-uml-id="{shared_module["id"]}"]'
                assert (
                    page.locator('.flow-nodes [data-uml-kind="module"]' + shared_selector).count()
                    == 1
                )
                assert (
                    page.locator(
                        '.flow-frames [data-uml-kind="component"]' + shared_selector
                    ).count()
                    == 1
                )

            # Every real Python module remains visible in each view; isolation comes only
            # from the exact edge endpoints selected for that view.
            for width in (1440, 390):
                page.set_viewport_size({"width": width, "height": 900})
                for view in ("diagram", "target", "diff"):
                    open_modules(main, view)
                    page.set_viewport_size({"width": width, "height": 900})
                    page.wait_for_function(
                        "() => document.querySelectorAll('[data-uml-kind=module]').length === 72"
                    )
                    state = geometry()
                    assert len(state["cards"]) == 72
                    assert state["documentWidth"] <= state["width"], state
                    zoom = page.locator(".flow-zoom-value").inner_text()
                    assert int(zoom.rstrip("%")) >= 85, zoom
                    edges = state["edges"]
                    if view == "target":
                        modules_for_view = atlas["declared_modules"]
                        expected_edges = {
                            (module["id"], edge["target_id"])
                            for module in modules_for_view
                            for edge in module.get("relationships", [])
                            if edge["target_id"] in target_modules
                        }
                        assert len(expected_edges) > 0
                        expected_modules = target_modules
                    else:
                        expected_edges = {
                            (
                                atlas["modules"][atlas["cells"][index][0]]["id"],
                                atlas["modules"][atlas["cells"][index][1]]["id"],
                            )
                            for index in level["cells"]
                            if atlas["modules"][atlas["cells"][index][0]]["id"] in observed_modules
                            and atlas["modules"][atlas["cells"][index][1]]["id"] in observed_modules
                        }
                        expected_modules = observed_modules
                    actual_edges = {tuple(edge) for edge in edges}
                    assert actual_edges == expected_edges
                    assert len(actual_edges) == len(edges)
                    assert state["routeWarnings"] == 0
                    if view != "target":
                        module_list = page.locator("details.atlas-module-list")
                        assert module_list.locator("summary").inner_text() == "Modules and UML · 72"
                        module_list.locator("summary").click()
                        assert module_list.locator("li").count() == 72
                    degree = {module: 0 for module in expected_modules}
                    for source, target in actual_edges:
                        degree[source] += 1
                        degree[target] += 1
                    isolated = {module for module, count in degree.items() if count == 0}
                    state_by_id = {card["id"]: card for card in state["cards"]}
                    assert set(state_by_id) == expected_modules
                    assert {
                        module
                        for module, card in state_by_id.items()
                        if card["inventory"] == "true"
                    } == isolated
                    if isolated:
                        assert state["inventory"] is None
                    assert len({card["transform"] for card in state["cards"]}) == 72
                    if view == "target" and width == 1440:
                        assert len(isolated) < 72
                        target_isolated = sorted(isolated)
                        overview_query = parse_qs(urlsplit(page.url).query)
                        page.locator(f'.flow-nodes [data-uml-id="{target_isolated[0]}"]').press(
                            "Enter"
                        )
                        page.wait_for_url("**/*.detail.html?*")
                        query = parse_qs(urlsplit(page.url).query)
                        assert query["module"] == [target_isolated[0]]
                        assert query["origin"] == ["declared"]
                        declared_module = next(
                            module
                            for module in atlas["declared_modules"]
                            if module["id"] == target_isolated[0]
                        )
                        source_name = (declared_module["path"] or declared_module["name"]).split(
                            "/"
                        )[-1]
                        assert source_name in page.locator(".flow-breadcrumb").inner_text()
                        page.get_by_role(
                            "link", name="Back to architecture map", exact=True
                        ).click()
                        returned_query = parse_qs(urlsplit(page.url).query)
                        assert returned_query.get("scope") == overview_query.get("scope")
                        assert returned_query["view"] == overview_query["view"] == ["target"]
                        assert returned_query["content"] == overview_query["content"] == ["modules"]
                        page.wait_for_function(
                            'id => document.querySelector(`[data-uml-id="${id}"]`) !== null',
                            arg=target_isolated[0],
                        )
                        assert (
                            page.locator(
                                f'.flow-nodes [data-uml-id="{target_isolated[0]}"]'
                            ).count()
                            == 1
                        )
                    page.locator(".flow-canvas").scroll_into_view_if_needed()
                    page.locator(".flow-canvas").evaluate(
                        "canvas => { canvas.scrollTop = 0; canvas.scrollLeft = 0; }"
                    )
                    page.screenshot(
                        path=str(screenshots / f"python-{width}-{view}.png"),
                        full_page=False,
                    )
                    if width == 1440 and view == "target":
                        readable_zoom = int(
                            page.locator(".flow-zoom-value").inner_text().rstrip("%")
                        )
                        page.get_by_role("button", name="Fit overview").click()
                        overview_zoom = int(
                            page.locator(".flow-zoom-value").inner_text().rstrip("%")
                        )
                        assert overview_zoom < readable_zoom
                        assert page.locator(".flow-canvas").evaluate(
                            "canvas => canvas.scrollHeight <= canvas.clientHeight + 4"
                        )
                    if width == 390 and view == "target":
                        page.get_by_role("button", name="Fit overview").click()
                        fit_zoom = int(page.locator(".flow-zoom-value").inner_text().rstrip("%"))
                        assert fit_zoom < 100
                        assert page.locator(".flow-canvas").evaluate(
                            "canvas => canvas.scrollHeight <= canvas.clientHeight + 4"
                        )
                        fit_scale = scale()
                        page.get_by_role("button", name="Zoom out").click()
                        zoom_out = int(page.locator(".flow-zoom-value").inner_text().rstrip("%"))
                        zoom_out_scale = scale()
                        assert zoom_out_scale < fit_scale
                        assert zoom_out == round(zoom_out_scale * 100)
                        page.get_by_role("button", name="Zoom in").click()
                        zoom_in = int(page.locator(".flow-zoom-value").inner_text().rstrip("%"))
                        zoom_in_scale = scale()
                        assert zoom_in_scale > zoom_out_scale
                        assert zoom_in == round(zoom_in_scale * 100)
                        page.get_by_role("button", name="Zoom out").click()
                        zoom_out_again = int(
                            page.locator(".flow-zoom-value").inner_text().rstrip("%")
                        )
                        zoom_out_again_scale = scale()
                        assert zoom_out_again_scale < zoom_in_scale
                        assert zoom_out_again == round(zoom_out_again_scale * 100)
            assert not errors
        finally:
            browser.close()
