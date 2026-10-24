# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The published demo gallery links complete, real reports."""

import json
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest

from fixtures.architecture_demo import PROJECT_REPORT_GROUPS, REPORT_CASES
from tools import report_pages
from tools.report_pages import _entry, _write_index, build_demos


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href")


def test_project_report_groups_are_the_first_three_complete_catalog_entries():
    assert [group["id"] for group in PROJECT_REPORT_GROUPS] == [
        "compass",
        "python-realworld",
        "nest-realworld",
    ]
    for group in PROJECT_REPORT_GROUPS:
        assert group["commit"] and group["repository"] and group["scope"]
        assert group["feature"] and group["target_depth"] and group["evidence_limits"]
        case_ids = (group["baseline"], *group["variants"])
        assert len(group["variants"]) == 3
        assert len(set(case_ids)) == 4
        assert all(case in REPORT_CASES for case in case_ids)
        assert set(group["browser"]) == {
            "root_component",
            "nested_component",
            "module_path",
            "class_name",
            "member_name",
        }


def test_gallery_surfaces_known_rule_failures_separately_from_aggregate_unknown(tmp_path):
    rows = []
    for group in PROJECT_REPORT_GROUPS:
        for case_id in (group["baseline"], *group["variants"]):
            forbidden = "forbidden-edge" in case_id
            rows.append(
                {
                    "id": case_id,
                    "case_id": case_id,
                    "summary": "Source-only project variant",
                    "observation_complete": "PASS",
                    "coverage": {"status": "PASS", "failures": []},
                    "declared_rules": "UNKNOWN",
                    "rule_assessments": [
                        {
                            "id": "REQUIRES-COMPLETE",
                            "status": "FAIL" if forbidden else "UNKNOWN",
                            "count": 1 if forbidden else 0,
                        }
                    ],
                    "uml_comparison": "UNKNOWN",
                    "report_href": f"demos/{case_id}/architecture.report.html?theme=dark",
                    "detail_href": f"demos/{case_id}/architecture.detail.html?theme=dark",
                }
            )
    rows.append(
        {
            "id": "uml-flutter-unsupported-declaration",
            "case_id": "uml-flutter-unsupported-declaration",
            "summary": "Unsupported source declaration control",
            "observation_complete": "UNKNOWN",
            "coverage": {"status": "UNKNOWN", "failures": []},
            "declared_rules": "UNKNOWN",
            "rule_assessments": [],
            "uml_comparison": None,
            "report_href": "demos/control/architecture.report.html?theme=dark",
            "detail_href": "demos/control/architecture.detail.html?theme=dark",
        }
    )

    output = tmp_path / "demos"
    output.mkdir()
    _write_index(output, rows)

    html = (tmp_path / "index.html").read_text()
    assert "Rules: UNKNOWN" in html
    assert '<p class="known-failure">Known rule failure: REQUIRES-COMPLETE (1)</p>' in html
    failure_offset = html.index('class="known-failure"')
    card_offset = html.rfind('<article class="demo">', 0, failure_offset)
    assert failure_offset < html.index("<details>", card_offset)
    assert "UML: N/A" in html

    index = json.loads((output / "index.json").read_text())
    assert [group["id"] for group in index["projects"]] == [
        group["id"] for group in PROJECT_REPORT_GROUPS
    ]
    parser = Links()
    parser.feed(html)
    assert {href for href in parser.hrefs if href.startswith("demos/")} == {
        row[key] for row in rows for key in ("report_href", "detail_href")
    }


@pytest.mark.parametrize("comparison", [None, {"status": "unsupported"}])
def test_project_gallery_rejects_missing_or_invalid_comparison(tmp_path, comparison):
    artifact = tmp_path / "architecture.json"
    artifact.with_suffix(".report.html").write_text("report")
    payload = json.dumps({"comparison": comparison})
    artifact.with_suffix(".detail.html").write_text(f'<script id="flow-data">{payload}</script>')
    with pytest.raises(ValueError, match="comparison status"):
        _entry("project", "", {}, artifact, requires_uml=True)


def test_gallery_builds_real_reports_with_working_dark_links(tmp_path, monkeypatch):
    selected = ("uml-match", "uml-mismatch", "uml-partial")
    monkeypatch.setattr(
        report_pages, "REPORT_CASES", {name: REPORT_CASES[name] for name in selected}
    )
    monkeypatch.setattr(report_pages, "PROJECT_REPORT_GROUPS", ())
    output = tmp_path / "demos"
    build_demos(output)
    index = json.loads((output / "index.json").read_text())
    projects = index["projects"]
    controls = index["controls"]
    assert projects == []
    assert {row["id"] for row in controls} == {
        *selected,
        "dart-clean",
        "dart-tour",
        "typescript-clean",
    }
    report_rows = controls
    assert {entry["uml_comparison"] for entry in report_rows} >= {"PASS", "FAIL", "UNKNOWN"}
    for entry in report_rows:
        assert entry["observation_complete"] in {"PASS", "FAIL", "UNKNOWN"}
        assert entry["coverage"]["status"] in {"PASS", "FAIL", "UNKNOWN"}
        assert entry["declared_rules"] in {"PASS", "FAIL", "UNKNOWN"}
        assert isinstance(entry["rule_assessments"], list)
    parser = Links()
    landing = (tmp_path / "index.html").read_text()
    parser.feed(landing)
    assert "architecture.report.html?theme=dark" in parser.hrefs
    assert 'id="projects"' in landing and 'id="controls"' in landing
    assert "http-equiv" not in landing
    assert "../#projects" in (output / "index.html").read_text()
    report_links = [
        urlsplit(href)
        for href in parser.hrefs
        if href.startswith("demos/") and ".report.html" in href
    ]
    detail_links = [
        urlsplit(href)
        for href in parser.hrefs
        if href.startswith("demos/") and ".detail.html" in href
    ]
    assert len(report_links) == len(detail_links) == len(report_rows)
    for link in (*report_links, *detail_links):
        assert link.query == "theme=dark"
        assert (tmp_path / link.path).is_file()
    assert not list(output.rglob(".git"))
    assert not list(output.rglob("node_modules"))
