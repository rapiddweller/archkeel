# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One CI job publishes the gallery on each push to main and cannot change the verdict (AD-462)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github/workflows"
PAGES = ("pages: write", "id-token: write")


def _jobs(workflow: str) -> dict[str, str]:
    text = (WORKFLOWS / workflow).read_text()
    parts = re.split(r"^  ([\w-]+):\n", text.split("\njobs:\n", 1)[1], flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def test_the_publication_job_is_outside_the_verdict_and_cannot_fail_the_run() -> None:
    jobs = _jobs("ci.yml")
    body = jobs["publish-gallery"]
    assert "publish-gallery" not in jobs["check"]
    assert "publish-gallery" not in _jobs("full-verification.yml")
    assert "    continue-on-error: true\n" in body
    assert "needs:" not in body


def test_the_publication_runs_only_for_a_push_or_a_dispatch_on_main() -> None:
    body = _jobs("ci.yml")["publish-gallery"]
    condition = re.search(r"^    if: (.+)$", body, re.MULTILINE)
    assert condition is not None
    assert condition[1] == "github.ref == 'refs/heads/main'"
    for workflow in WORKFLOWS.glob("*.yml"):
        assert "pull_request" not in workflow.read_text(), workflow.name


def test_only_the_publication_job_can_write_pages_and_each_other_job_keeps_read_only() -> None:
    text = (WORKFLOWS / "ci.yml").read_text()
    assert text.split("\njobs:\n", 1)[0].count("contents: read") == 1
    jobs = _jobs("ci.yml")
    holders = [name for name, body in jobs.items() if any(item in body for item in PAGES)]
    assert holders == ["publish-gallery"]
    body = jobs["publish-gallery"]
    assert all(f"      {item}\n" in body for item in PAGES)
    assert "      contents: read\n" in body
    block = re.search(r"^    permissions:\n((?:      .+\n)+)", body, re.MULTILINE)
    assert block is not None
    assert sorted(re.findall(r"^      ([\w-]+):", block[1], re.MULTILINE)) == [
        "contents",
        "id-token",
        "pages",
    ]


def test_the_job_builds_the_gallery_then_uploads_and_deploys_the_same_directory() -> None:
    body = _jobs("ci.yml")["publish-gallery"]
    build = body.index("run: make report-gallery")
    upload = body.index("actions/upload-pages-artifact@")
    deploy = body.index("actions/deploy-pages@")
    assert build < upload < deploy
    assert "path: test-artifacts/gallery/" in body
    assert "name: github-pages" in body
    assert "group: github-pages" in body


def test_no_other_workflow_can_write_pages() -> None:
    """Full and release ask for no Pages permission: the release caller must not give it."""
    assert "pages: write" not in (WORKFLOWS / "release.yml").read_text()
    text = (WORKFLOWS / "full-verification.yml").read_text()
    assert not any(item in text for item in PAGES)


def test_the_release_caller_gives_every_permission_that_a_called_job_asks_for() -> None:
    """A called job cannot ask for more than its caller gives: the run would not start."""
    caller = _jobs("release.yml")["verify"]
    asked = set(
        re.findall(
            r"^      ([\w-]+: (?:read|write))$",
            (WORKFLOWS / "full-verification.yml").read_text(),
            re.MULTILINE,
        )
    )
    assert asked
    assert all(f"      {item}\n" in caller for item in asked)
