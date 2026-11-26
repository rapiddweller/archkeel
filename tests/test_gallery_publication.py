# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Pages workflow publishes the gallery after each push to main (AD-462, AD-740)."""

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


def test_the_deploy_needs_the_build_and_a_failed_publish_turns_the_run_red() -> None:
    jobs = _jobs("pages.yml")
    assert set(jobs) == {"publish-gallery", "deploy-gallery"}
    assert "publish-gallery" not in _jobs("ci.yml")
    assert "publish-gallery" not in _jobs("full-verification.yml")
    # AD-740: no `continue-on-error`; a failed publish makes the run red.
    assert "continue-on-error" not in "".join(jobs.values())
    assert "needs:" not in jobs["publish-gallery"]
    assert "    needs: publish-gallery\n" in jobs["deploy-gallery"]


def test_the_publication_runs_only_for_a_push_or_a_dispatch_on_main() -> None:
    body = _jobs("pages.yml")["publish-gallery"]
    condition = re.search(r"^    if: (.+)$", body, re.MULTILINE)
    assert condition is not None
    assert condition[1] == "github.ref == 'refs/heads/main'"
    for workflow in WORKFLOWS.glob("*.yml"):
        if workflow.name not in {"pr-gate.yml", "pr-gate-rerun.yml"}:
            assert "pull_request:" not in workflow.read_text().split("\nconcurrency:\n", 1)[0], (
                workflow.name
            )


def test_only_the_deploy_job_can_write_pages_and_the_build_job_keeps_read_only() -> None:
    for workflow in WORKFLOWS.glob("*.yml"):
        if workflow.name == "release.yml":
            continue  # PyPI publishing asks for id-token on its own
        text = workflow.read_text()
        if workflow.name in ("ci.yml", "pages.yml"):
            assert text.split("\njobs:\n", 1)[0].count("contents: read") == 1, workflow.name
        holders = [
            f"{workflow.name}:{name}"
            for name, body in _jobs(workflow.name).items()
            if any(item in body for item in PAGES)
        ]
        assert holders == (["pages.yml:deploy-gallery"] if workflow.name == "pages.yml" else [])
    jobs = _jobs("pages.yml")
    assert all(f"      {item}\n" in jobs["deploy-gallery"] for item in PAGES)
    # The build job fetches third-party sources: it gets no token that can publish.
    for job, expected in (
        ("publish-gallery", ["contents"]),
        ("deploy-gallery", ["id-token", "pages"]),
    ):
        block = re.search(r"^    permissions:\n((?:      .+\n)+)", jobs[job], re.MULTILINE)
        assert block is not None
        assert sorted(re.findall(r"^      ([\w-]+):", block[1], re.MULTILINE)) == expected


def test_the_build_uploads_an_artifact_named_by_the_attempt_and_the_deploy_takes_that_name() -> (
    None
):
    """A rerun keeps the artifact of attempt 1, and `deploy-pages` needs exactly one artifact."""
    jobs = _jobs("pages.yml")
    build, deploy = jobs["publish-gallery"], jobs["deploy-gallery"]
    assert build.index("run: make report-gallery") < build.index("actions/upload-pages-artifact@")
    assert "path: test-artifacts/gallery/" in build
    assert 'echo "name=github-pages-${{ github.run_attempt }}"' in build
    assert "name: ${{ steps.artifact.outputs.name }}" in build
    assert "artifact: ${{ steps.artifact.outputs.name }}" in build
    assert "artifact_name: ${{ needs.publish-gallery.outputs.artifact }}" in deploy
    assert "actions/deploy-pages@" in deploy and "name: github-pages\n" in deploy


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


def test_no_push_cancels_a_publication_and_the_nightly_run_publishes_too() -> None:
    """AD-740: in ci.yml a newer push cancelled the publication; 38 of 40 runs were cancelled."""
    text = (WORKFLOWS / "pages.yml").read_text()
    head = text.split("\njobs:\n", 1)[0]
    assert "\nconcurrency:\n  group: github-pages\n  cancel-in-progress: false\n" in head
    assert "cancel-in-progress: true" not in text
    assert "push:\n    branches: [main]" in head and "schedule:" in head
    assert "publish-gallery" not in (WORKFLOWS / "ci.yml").read_text()


def test_a_failed_build_deploys_nothing_and_the_fetched_sources_are_cached() -> None:
    """A pinned source that cannot be fetched fails the build step. The deploy is another job
    that needs the build and has no `if:`, so the last good page stays and no half page appears."""
    jobs = _jobs("pages.yml")
    assert "if:" not in jobs["deploy-gallery"]
    build = jobs["publish-gallery"]
    restore = build.index("path: test-artifacts/source-cache")
    assert restore < build.index("run: make report-gallery")
    assert "hashFiles('fixtures/*/SOURCE.json')" in build


def test_the_pages_build_saves_no_cache() -> None:
    """AD-1060: CI saves the Rust cache and the core of main; a second save only conflicts."""
    assert "cache/save" not in (WORKFLOWS / "pages.yml").read_text()
