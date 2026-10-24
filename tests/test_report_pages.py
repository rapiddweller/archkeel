# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The published demo gallery links complete, real reports."""

import json
from html.parser import HTMLParser
from urllib.parse import urlsplit

from fixtures.architecture_demo import PROJECT_REPORT_GROUPS, REPORT_CASES, UML_DEMO_COMPARISONS
from tools.report_pages import _write_index, build_demos


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


def test_gallery_builds_real_reports_with_working_dark_links(tmp_path):
    output = tmp_path / "demos"
    build_demos(output)
    index = json.loads((output / "index.json").read_text())
    projects = index["projects"]
    controls = index["controls"]
    assert [item["id"] for item in projects] == [
        "compass",
        "python-realworld",
        "nest-realworld",
    ]
    control_ids = {row["id"] for row in controls}
    runnable = next(row for row in controls if row["id"] == "uml-flutter-shop")
    assert runnable["kind"] == "runnable_control"
    assert "smaller runnable control" in runnable["label"]
    assert control_ids >= {
        "tour",
        "uml-dart-match",
        "uml-dart-signature-fail",
        "uml-dart-missing-member-fail",
        "uml-dart-forbidden-dependency-fail",
        "uml-dart-partial-unknown",
        "dart-clean",
        "dart-tour",
        "typescript-clean",
        "uml-typescript-match",
        "uml-typescript-mismatch",
        "uml-typescript-partial",
    }
    report_rows = [
        entry for group in projects for entry in (group["baseline"], *group["variants"])
    ] + controls
    assert {entry["uml_comparison"] for entry in report_rows} >= {"PASS", "FAIL", "UNKNOWN"}
    assert all(
        entry["uml_comparison"] in {"PASS", "FAIL", "UNKNOWN"}
        for group in projects
        for entry in (group["baseline"], *group["variants"])
    )
    unsupported_control = next(
        row for row in controls if row["id"] == "uml-flutter-unsupported-declaration"
    )
    assert unsupported_control["uml_comparison"] is None
    for entry in report_rows:
        assert entry["observation_complete"] in {"PASS", "FAIL", "UNKNOWN"}
        assert entry["coverage"]["status"] in {"PASS", "FAIL", "UNKNOWN"}
        assert entry["declared_rules"] in {"PASS", "FAIL", "UNKNOWN"}
        assert isinstance(entry["rule_assessments"], list)
    for group in projects:
        assert all(entry["rule_assessments"] for entry in (group["baseline"], *group["variants"]))
    python_group = projects[1]
    assert python_group["baseline"]["observation_complete"] == "PASS"
    assert python_group["baseline"]["coverage"]["status"] == "PASS"
    assert python_group["baseline"]["declared_rules"] == "UNKNOWN"
    for group in projects:
        forbidden = next(row for row in group["variants"] if "forbidden-edge" in row["id"])
        assert any(item["status"] == "FAIL" for item in forbidden["rule_assessments"])
        assert forbidden["uml_comparison"] == UML_DEMO_COMPARISONS[forbidden["case_id"]]

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
