# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Executed checks of the Make and CI wrappers: aggregates, cleanup, mermaid and test ownership."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest
from areas import AREAS, area_of
from timeout_support import run_bounded

ROOT = Path(__file__).parents[1]


def _jobs(workflow: str) -> dict[str, str]:
    text = (ROOT / ".github/workflows" / workflow).read_text()
    parts = re.split(r"^  ([\w-]+):\n", text.split("\njobs:\n", 1)[1], flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


@pytest.mark.parametrize(
    ("workflow", "aggregate"),
    [("ci.yml", "check"), ("full-verification.yml", "verified")],
)
def test_each_aggregate_needs_every_job_and_fails_closed(workflow: str, aggregate: str) -> None:
    jobs = _jobs(workflow)
    body = jobs[aggregate]
    assert "if: always()" in body
    needs = re.search(r"needs: \[(.+)\]|needs:\n((?:      - .+\n)+)", body)
    assert needs is not None
    listed = re.findall(r"\w[\w-]*", needs[1] or needs[2])
    # AD-462, AD-1223: the gallery and the main build publication are not required.
    assert set(listed) == set(jobs) - {aggregate, "publish-gallery", "publish-main-build"}
    script = dedent(body.split("        run: |\n", 1)[1])
    ok = " ".join(["success"] * len(listed))

    def run(results: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "RESULTS": results}
        return subprocess.run(
            ["bash", "-eu", "-c", script], env=env, capture_output=True, text=True
        )

    assert run(ok).returncode == 0
    assert run("").returncode != 0
    # AD-736: the message names what happened; a cancelled run is not called a failure.
    results = {
        bad: run(ok.replace("success", bad, 1)) for bad in ("failure", "cancelled", "skipped")
    }
    assert all(done.returncode != 0 for done in results.values())
    assert "cancelled" in results["cancelled"].stderr
    assert "failed" not in results["cancelled"].stderr
    assert "skipped" in results["skipped"].stderr
    assert "failed" in results["failure"].stderr


@pytest.mark.parametrize("renderer_exit", [0, 1])
def test_mermaid_renders_every_block_and_propagates_renderer_failure(
    tmp_path: Path, renderer_exit: int
) -> None:
    renderer = tmp_path / "npx"
    invocations = tmp_path / "renders"
    renderer.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{invocations}"\nexit {renderer_exit}\n'
    )
    renderer.chmod(0o755)
    result = run_bounded(
        ["make", "mermaid"],
        cwd=ROOT,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=15,
    )
    extracted = [line for line in result.stdout.splitlines() if ".mmd\t" in line]
    rendered = invocations.read_text().splitlines()
    assert len(rendered) == len(extracted) > 1
    assert all("@mermaid-js/mermaid-cli@11.17.0" in line for line in rendered)
    assert result.returncode == (0 if renderer_exit == 0 else 2), result.stderr
    if renderer_exit:
        assert result.stdout.count("::error::") == len(rendered)
        assert all(line.split("\t", 1)[1] in result.stdout for line in extracted)


def test_ci_cleanup_preserves_test_evidence(tmp_path: Path) -> None:
    output = tmp_path / "test-artifacts/validation-native"
    output.mkdir(parents=True)
    (output / "result.json").write_text("previous result")
    browser = tmp_path / "test-artifacts/validation"
    browser.mkdir()
    (browser / "studio-ui.json").write_text("previous result")
    evidence = tmp_path / "test-artifacts/pytest/results.xml"
    evidence.parent.mkdir()
    evidence.write_text("keep")
    run = run_bounded(
        ["make", "-f", str(ROOT / "Makefile"), "ci-artifacts-clean"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert run.returncode == 0, run.stderr
    assert not output.exists()
    assert not browser.exists()
    assert evidence.read_text() == "keep"


def _collected(
    *arguments: str, path: str | None = None
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *arguments,
        ],
        cwd=ROOT,
        env=os.environ if path is None else {**os.environ, "PYTHONPATH": path},
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result, [line for line in result.stdout.splitlines() if "::" in line]


def test_every_test_file_belongs_to_one_area_and_ci_runs_every_area() -> None:
    files = sorted(path.name for path in (ROOT / "tests").rglob("test_*.py"))
    assert [name for name in files if area_of(name) is None] == []
    for workflow in ("area-checks.yml", "full-verification.yml"):
        text = (ROOT / ".github/workflows" / workflow).read_text()
        listed = re.search(r"\n        area:\n((?:          - .+\n)+)", text)
        assert listed is not None, workflow
        assert [line.split("- ", 1)[1].strip('"') for line in listed[1].splitlines()] == list(AREAS)


def test_an_area_selects_only_its_files_and_fails_closed_when_empty() -> None:
    result, selected = _collected(
        "--area=reports", "tests/test_report_gallery.py", "tests/test_skill.py"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert selected and all(test.startswith("tests/test_report_gallery.py::") for test in selected)
    result, _ = _collected("--area=CLI and core", "tests/test_skill.py")
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.stdout + result.stderr
    assert "selects no tests" in result.stderr
    result, _ = _collected("--area=no such area", "tests/test_skill.py")
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.stdout + result.stderr
    assert "is not an area" in result.stderr
