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
TARGET_DIGEST = "c15508d0515c640e36f365943a54f8becff32d1523ed0d34aecee2aa3a3e9839"
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
    "python-realworld-project": Counter(PASS=1025, UNKNOWN=47, FAIL=0),
    "python-realworld-forbidden-edge": Counter(PASS=1025, UNKNOWN=47, FAIL=0),
    "python-realworld-signature-fail": Counter(PASS=1024, UNKNOWN=47, FAIL=1),
    "python-realworld-dynamic-unknown": Counter(PASS=1024, UNKNOWN=48, FAIL=0),
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
        output = tmp_path / f"{variant_id}.json"
        assert replay(variant_id, output) == replay_exit
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
        assert len(report.comparison.assessments) == 1072
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
        assert len(report.target.relationships) == 89
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
                    page.screenshot(
                        path=str(screenshots / f"python-realworld-{width}-{view}.png"),
                        full_page=True,
                    )
        finally:
            browser.close()
