# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The published demo gallery links complete, real reports."""

import json
from html.parser import HTMLParser
from urllib.parse import urlsplit

from tools.report_pages import build_demos


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href")


def test_gallery_builds_real_reports_with_working_dark_links(tmp_path):
    output = tmp_path / "demos"
    build_demos(output)
    rows = json.loads((output / "index.json").read_text())
    assert {row["status"] for row in rows} >= {"PASS", "FAIL", "UNKNOWN"}
    assert {row["id"] for row in rows} >= {
        "tour",
        "uml-dart",
        "dart-clean",
        "dart-tour",
        "typescript-clean",
        "uml-typescript-match",
        "uml-typescript-mismatch",
        "uml-typescript-partial",
    }
    parser = Links()
    parser.feed((output / "index.html").read_text())
    assert "../architecture.report.html?theme=dark" in parser.hrefs
    reports = [urlsplit(href) for href in parser.hrefs if not href.startswith("../")]
    assert len(reports) == len(rows)
    for link in reports:
        assert link.query == "theme=dark"
        assert (output / link.path).is_file()
        assert (output / link.path.replace(".report.html", ".detail.html")).is_file()
    assert not list(output.rglob(".git"))
    assert not list(output.rglob("node_modules"))
