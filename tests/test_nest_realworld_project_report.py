# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Full-source report replays for the frozen Nest/Mikro RealWorld Target."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from archkeel.ir.graph_codec import parse_report
from fixtures.architecture_demo import (
    CATALOG,
    REPORT_CASES,
    UML_DEMO_COMPARISONS,
    materialized_fixture,
    replay,
)
from fixtures.demo_catalog_nest_realworld import NEST_REALWORLD_FIXTURE_DIR, VARIANTS
from fixtures.demo_catalog_support import Variant

FIXTURE = NEST_REALWORLD_FIXTURE_DIR
TARGET_FILES = (
    "architecture-contract.json",
    "contracts/runtime.json",
    "contracts/identity.json",
    "contracts/publishing.json",
    "contracts/persistence.json",
)
TARGET_DIGEST = "0cb24944e3a6f7be9ecfc58deb1f868fd91958f0bcda6872c3b599530e1e4c68"
SOURCE_DIGESTS = {
    "nest-realworld-project": "d5963c18106b156eedd3149733d4e35aa03c89b811d417e4d7e2e64d07f1ad46",
    "nest-realworld-forbidden-edge": (
        "1b09739a520281ac416a537a4deb304a6720920907829efe03634ee28941b05e"
    ),
    "nest-realworld-signature-fail": (
        "b98ca8914581f73600c8109d1e92bf821cebdff246dc4394a030e17cbb4183b7"
    ),
    "nest-realworld-dynamic-unknown": (
        "d17bce3d752cc066e15d78e87e787e4c5b6b2071bf3c4f034507bd8ef7f1b1c2"
    ),
}
EXPECTED_ASSESSMENTS = {
    "nest-realworld-project": Counter(PASS=841, UNKNOWN=64),
    "nest-realworld-forbidden-edge": Counter(PASS=841, UNKNOWN=64),
    "nest-realworld-signature-fail": Counter(PASS=840, UNKNOWN=64, FAIL=1),
    "nest-realworld-dynamic-unknown": Counter(PASS=840, UNKNOWN=65),
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
    data = _payload(output.with_suffix(".detail.html"))
    assert data["navigation"]["main_href"] == main.name
    return parse_report(
        {
            key: value
            for key, value in data.items()
            if key not in {"initial_scope", "initial_view", "navigation"}
        }
    )


def _assessment(report, subject_id: str, aspect: str):
    assert report.comparison is not None
    return next(
        item
        for item in report.comparison.assessments
        if item.subject_id == subject_id and item.aspect == aspect
    )


def test_nest_materializer_commits_resolver_inputs_before_source_overlay() -> None:
    snapshot = json.loads((FIXTURE / "SNAPSHOT.json").read_bytes())
    original = snapshot["original_src_files"]
    derived = snapshot["derived_files"]
    assert len(original) == 45
    assert len(derived) == 2
    assert sum(item["build_input"] for item in original) + len(derived) == 41
    for item in original:
        content = (FIXTURE / item["path"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == item["sha256"]
    for item in derived:
        content = (FIXTURE / item["path"]).read_bytes()
        template = (FIXTURE / item["source_path"]).read_bytes()
        assert content == template
        assert hashlib.sha256(content).hexdigest() == item["sha256"]

    provenance = json.loads((FIXTURE / "resolver-inputs/provenance.json").read_bytes())
    records = [
        item
        for package in provenance["packages"]
        for item in (*package["files"], package["license_file"])
    ]
    assert len(records) == 60
    relative = "src/user/user.service.ts"
    original = (FIXTURE / relative).read_bytes()
    variant = Variant(
        id="nest-materializer-probe",
        section="clean",
        item="nest:materializer-probe",
        summary="Probe replay materialization only.",
        files={relative: "post-commit overlay"},
        expected_violations=(),
        expected_codes=(),
        fixture=FIXTURE,
    )

    with materialized_fixture(variant) as root:
        for item in snapshot["original_src_files"]:
            committed = subprocess.check_output(["git", "show", f"main:{item['path']}"], cwd=root)
            assert committed == (FIXTURE / item["path"]).read_bytes()
        for item in snapshot["derived_files"]:
            committed = subprocess.check_output(["git", "show", f"main:{item['path']}"], cwd=root)
            assert committed == (FIXTURE / item["source_path"]).read_bytes()
        assert (root / relative).read_text() == "post-commit overlay"
        for item in records:
            for staged_prefix in ("resolver-inputs", "node_modules"):
                committed = subprocess.check_output(
                    ["git", "show", f"main:{staged_prefix}/{item['path']}"], cwd=root
                )
                assert len(committed) == item["size"]
                assert hashlib.sha256(committed).hexdigest() == item["sha256"]


def test_nest_realworld_catalog_and_reports_preserve_full_target_with_partial_coverage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    expected_ids = {
        "nest-realworld-project",
        "nest-realworld-forbidden-edge",
        "nest-realworld-signature-fail",
        "nest-realworld-dynamic-unknown",
    }
    assert {item.id for item in VARIANTS} == expected_ids
    assert {item.id for item in CATALOG if item.id.startswith("nest-realworld-")} == expected_ids
    assert {key for key, (variant, _) in REPORT_CASES.items() if variant in expected_ids} == {
        f"uml-{variant}" for variant in expected_ids
    }
    assert {
        key: value
        for key, value in UML_DEMO_COMPARISONS.items()
        if key.startswith("uml-nest-realworld-")
    } == {
        "uml-nest-realworld-project": "UNKNOWN",
        "uml-nest-realworld-forbidden-edge": "UNKNOWN",
        "uml-nest-realworld-signature-fail": "FAIL",
        "uml-nest-realworld-dynamic-unknown": "UNKNOWN",
    }

    snapshot = json.loads((FIXTURE / "SNAPSHOT.json").read_bytes())
    selected = {item["path"] for item in snapshot["original_src_files"] if item["build_input"]} | {
        item["path"] for item in snapshot["derived_files"]
    }
    target_hash = hashlib.sha256(
        b"".join((FIXTURE / path).read_bytes() for path in TARGET_FILES)
    ).hexdigest()
    assert target_hash == TARGET_DIGEST
    assert f"Target bundle SHA-256: `{TARGET_DIGEST}`" in (FIXTURE / "docs/target.md").read_text(
        encoding="utf-8"
    )

    reports = {}
    target_digests = set()
    for variant in VARIANTS:
        assert variant.fixture == FIXTURE
        output = tmp_path / f"{variant.id}.json"
        actual_exit = replay(variant.id, output)
        captured = capsys.readouterr().out.splitlines()
        summaries = [json.loads(line) for line in captured if line.startswith("{")]
        validate = next(item for item in summaries if item["command"] == "validate")
        report_summary = next(item for item in summaries if item["command"] == "report")
        assert actual_exit == REPORT_CASES[f"uml-{variant.id}"][1] == 2
        assert validate["exit_code"] == report_summary["exit_code"] == actual_exit
        assert report_summary["observation_complete"] == "UNKNOWN"
        assert report_summary["declared_rules"] == "UNKNOWN"
        for summary in (validate, report_summary):
            coverage = summary["coverage"]
            assert coverage["files_discovered"] == 41
            assert coverage["files_read"] == 41
            assert coverage["files_parsed"] == 41
            assert coverage["ast_coverage_percent"] == 100.0
            assert coverage["status"] == "FAIL"
            assert len(coverage["failures"]) == 1
            failure = coverage["failures"][0]
            assert failure["kind"] == "source_resolution_gap"
            assert failure["subjects"] == ["nestjs.realworld.src.mikro_x2d_orm_x2e_config_x2e_ts"]
            assert failure["title"] == "Computed dynamic_import cannot be resolved"

        raw = json.loads(output.read_text(encoding="utf-8"))
        assert raw["source"]["source_digest"] == SOURCE_DIGESTS[variant.id]
        target_digests.add(raw["contract"]["digest"])
        assert output.with_suffix(".report.html").is_file()
        assert output.with_suffix(".detail.html").is_file()
        report = _report(output)
        assert report.comparison is not None
        assert report.comparison.status == UML_DEMO_COMPARISONS[f"uml-{variant.id}"]
        assert len(report.comparison.assessments) == 905
        assert (
            Counter(item.status for item in report.comparison.assessments)
            == EXPECTED_ASSESSMENTS[variant.id]
        )
        assert len(report.target.entities) == 266
        assert len(report.target.relationships) == 123
        target_modules = {
            item.file_path for item in report.target.entities if item.kind == "module"
        }
        observed_modules = {
            item.file_path for item in report.observed.entities if item.kind == "module"
        }
        assert target_modules == observed_modules == selected
        assert len(target_modules) == 41
        reports[variant.id] = report

    assert len(target_digests) == 1
    base = reports["nest-realworld-project"]
    forbidden = reports["nest-realworld-forbidden-edge"]
    validation = next(
        item
        for item in forbidden.observed.entities
        if item.file_path == "src/shared/pipes/validation.pipe.ts"
    )
    article = next(
        item
        for item in forbidden.observed.entities
        if item.file_path == "src/article/article.entity.ts"
    )
    edge = next(
        item
        for item in forbidden.observed.relationships
        if item.kind == "imports"
        and item.source_id == validation.id
        and item.target_id == article.id
    )
    violation = next(
        item
        for item in forbidden.findings
        if item.kind == "complete_requires" and item.status == "FAIL"
    )
    assert violation.rule_ids == ("REQUIRES-COMPLETE",)
    assert violation.id == "VIO-67fab996e87538cc"
    assert violation.status == "FAIL"
    assert violation.evidence_ids == edge.evidence_ids == ("EVD-17576bc5e19411f3",)
    assert not any(
        item.kind == "complete_requires" and item.status == "FAIL" for item in base.findings
    )

    method = next(
        item
        for item in base.target.entities
        if item.qualified_name.endswith("ArticleService.findFeed")
    )
    signature = _assessment(reports["nest-realworld-signature-fail"], method.id, "signature")
    assert signature.status == "FAIL"
    assert signature.reason == "Return annotation differs."

    obligation = "Account and authentication:create-user-invocation"
    baseline_call = _assessment(base, obligation, "relationship")
    dynamic_call = _assessment(
        reports["nest-realworld-dynamic-unknown"], obligation, "relationship"
    )
    assert (baseline_call.status, dynamic_call.status) == ("PASS", "UNKNOWN")
    assert baseline_call.evidence_ids == ("EVD-3c8426b5f4544736",)
    assert set(baseline_call.evidence_ids) <= set(dynamic_call.evidence_ids)


def test_nest_realworld_report_browses_deep_target_at_desktop_and_mobile(
    tmp_path: Path,
) -> None:
    api = pytest.importorskip("playwright.sync_api")
    output = tmp_path / "nest-realworld-project.json"
    assert replay("nest-realworld-project", output) == 2
    screenshots = Path(os.environ.get("ARCHKEEL_NEST_REPORT_ARTIFACTS", tmp_path / "screenshots"))
    screenshots.mkdir(parents=True, exist_ok=True)

    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            main = output.with_suffix(".report.html")
            page.goto(main.as_uri())
            assert _payload(main)["atlas"]["detail_page"] == output.with_suffix(".detail.html").name

            page.locator('.flow-nodes [data-uml-id="publishing"]').click()
            page.get_by_text("Browse 9 modules", exact=True).click()
            page.locator('[data-content="components"]').last.click()
            page.locator(
                '.flow-nodes [data-uml-id="Article and comment publishing:article-service"]'
            ).press("Enter")

            atlas = _payload(main)["atlas"]
            module = next(
                item
                for item in atlas["modules"]
                if item["path"] == "src/article/article.service.ts"
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
                    page.locator('.flow-nodes [data-label="ArticleService"]').dblclick()
                    member = page.locator('.flow-nodes [data-label="findFeed"]')
                    assert member.count() == 1
                    member.press("Space")
                    inspector = page.locator(".flow-inspector-content").inner_text()
                    assert "findFeed" in inspector
                    assert "src/article/article.service.ts" in inspector
                    if view == "target":
                        assert "docs/target.md" in inspector
                        assert "Promise<IArticlesRO>" in inspector
                    else:
                        assert "SOURCE SITES" in inspector
                        assert "article.service.ts" in inspector
                        assert "Promise<IArticlesRO>" in inspector
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(
                        path=str(screenshots / f"nest-realworld-{width}-{view}.png"),
                        full_page=True,
                    )
        finally:
            browser.close()
