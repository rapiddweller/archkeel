# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import re
from pathlib import Path

import pytest

from tools import demo_ci
from tools.report_pages import REPORT_CASES, gallery_cases


def test_matrix_covers_the_gallery_catalog():
    cases = gallery_cases()
    assert set(cases) == {*REPORT_CASES, "dart-clean", "dart-tour", "typescript-clean"}


@pytest.mark.parametrize(
    "name", ["uml-match", "uml-flutter-unsupported-declaration", "typescript-clean"]
)
def test_demo_job_records_real_result_and_phase_timings(tmp_path: Path, name: str, capsys):
    result = demo_ci.run(name, tmp_path / name)
    assert result["name"] == name
    assert result["expected_exit"] == result["exit"]
    assert result["coverage"]["status"] in {"PASS", "FAIL", "UNKNOWN"}
    assert result["declared_rules"] in {"PASS", "FAIL", "UNKNOWN"}
    assert result["output_bytes"] > 0
    assert result["phases"]
    assert json.loads((tmp_path / name / "result.json").read_text()) == result
    output = capsys.readouterr().out
    assert name in output
    assert "rule_assessments" not in output
    assert len(output) < 1000


def test_missing_timing_is_not_reported_as_success(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(demo_ci, "replay", lambda *args, **kwargs: 0)
    with pytest.raises((ValueError, StopIteration)):
        demo_ci.run("uml-match", tmp_path / "case")


def test_full_verification_requires_every_gallery_demo():
    workflow = (Path(__file__).parents[1] / ".github/workflows/full-verification.yml").read_text()
    job = workflow.split("  demos:\n", 1)[1].split("\n  full-suite-shards:", 1)[0]
    names = re.findall(r"- name: Demo / ([a-z0-9-]+)\n", job)
    assert names == list(gallery_cases())
    for name in names:
        assert f'make demo-ci CASE="{name}" OUTPUT="test-artifacts/demos/{name}"' in job
    assert job.count("if: ${{ !cancelled() && steps.install.outcome == 'success' }}") == len(names)
    assert "matrix:" not in job
    assert "${{ needs.demos.result }}" in workflow
    assert '"$DEMOS_RESULT"' in workflow
    assert "name: demo-results" in job
