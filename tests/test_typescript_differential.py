# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The in-package frontend against the frozen Node reference: no unexplained difference."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from archkeel.ir.facts_codec import encode_request
from fixtures import typescript_differential as differential
from fixtures import typescript_scenarios
from fixtures.demo_catalog_typescript import VARIANTS

CATALOGS = Path(differential.FIXTURES)


@pytest.fixture(scope="module")
def judged(tmp_path_factory: pytest.TempPathFactory) -> differential.Verdict:
    results = differential.run(tmp_path_factory.mktemp("differential"))
    verdict = differential.judge(results, differential.load_allowlist())
    output = Path(os.environ.get("ARCHKEEL_DIFFERENTIAL_OUTPUT", tmp_path_factory.mktemp("report")))
    output.mkdir(parents=True, exist_ok=True)
    (output / "typescript-differential.json").write_text(
        json.dumps(verdict.report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return verdict


def _size(name: str) -> int:
    return len(json.loads((CATALOGS / name).read_text()))


def test_the_corpus_holds_every_catalog_case(judged: differential.Verdict) -> None:
    groups = judged.report["groups"]
    assert isinstance(groups, dict)
    assert groups["variant"] == len(VARIANTS) == 34
    assert groups["hidden-loader"] == _size("typescript-hidden-loaders.json") == 111
    # Each runtime alias runs once as written and once with a hidden dependency.
    assert groups["runtime-alias"] == 2 * _size("typescript-runtime-aliases.json") == 48
    assert groups["module-identity"] == _size("typescript-module-identities.json") == 9
    assert groups["fixture"] == 2


def test_no_case_is_a_defect_or_suspicious_without_proof(judged: differential.Verdict) -> None:
    assert judged.failures == []
    counts = judged.report["counts"]
    assert isinstance(counts, dict)
    assert counts["defect"] == 0
    assert counts["suspicious"] == 0
    groups = judged.report["groups"]
    assert isinstance(groups, dict)
    assert counts["equivalent"] + counts["more_conservative"] == sum(groups.values())


def test_core_verdicts_never_gain_a_pass_or_a_fail_the_oracle_lacked(
    judged: differential.Verdict,
) -> None:
    cases = judged.report["cases"]
    assert isinstance(cases, list)
    changed = [
        item
        for case in cases
        for item in case["findings"]
        if item["subject"].startswith("Core verdict") and item["class"] != "equivalent"
    ]
    # Every Core difference is a verdict that became UNKNOWN; none became PASS or FAIL.
    assert all(item["frontend"] == "UNKNOWN" for item in changed)
    assert judged.report["core_statuses_compared"] > 400


def test_the_report_names_every_case_with_its_class(judged: differential.Verdict) -> None:
    cases = judged.report["cases"]
    assert isinstance(cases, list)
    assert len({case["case"] for case in cases}) == len(cases)
    assert {case["class"] for case in cases} <= set(differential.ORDER)


def _result(name: str, klass: differential.Klass) -> differential.Result:
    request = differential.request_for(Path("."), ("src",), "app")
    case = differential.Case(name, "scenario", Path("."), request)
    return differential.Result(case, (differential.Finding(klass, "x", "a", "b"),))


def test_the_judge_rejects_defects_and_unlisted_or_stale_or_unexplained_entries() -> None:
    results = [
        _result("kept", "more_conservative"),
        _result("unlisted", "more_conservative"),
        _result("broken", "defect"),
        _result("fine", "equivalent"),
        _result("risky", "suspicious"),
    ]
    allowlist = {
        "more_conservative": {
            "kept": "the frontend leaves it UNKNOWN",
            "fine": "stale",
            "gone": "x",
        },
        "suspicious": {"risky": " "},
    }
    failures = differential.judge(results, allowlist).failures
    assert "defect: broken" in failures
    assert "more_conservative without an allow-list reason: unlisted" in failures
    assert "stale allow-list entry (more_conservative): fine" in failures
    assert "stale allow-list entry (more_conservative): gone" in failures
    assert "suspicious without an allow-list reason: risky" in failures
    assert "allow-list entry without a reason: risky" in failures
    assert not any("kept" in item for item in failures)


def test_the_checked_in_allowlist_gives_every_entry_one_line_of_reason() -> None:
    allowlist = differential.load_allowlist()
    assert set(allowlist) == {"more_conservative", "suspicious"}
    for entries in allowlist.values():
        for name, reason in entries.items():
            assert reason.strip() and "\n" not in reason, name


def test_reference_rejects_missing_and_stale_cases(tmp_path: Path, monkeypatch) -> None:
    scenario = typescript_scenarios.SCENARIOS[0]
    typescript_scenarios.write(tmp_path, scenario)
    case = differential.Case(
        "scenario/missing-reference",
        "scenario",
        tmp_path,
        differential.request_for(tmp_path, scenario.roots, "app"),
    )
    with pytest.raises(ValueError, match="missing frozen TypeScript reference"):
        differential.reference(case)

    reference = json.loads(differential.REFERENCE.read_text())
    reference["cases"][case.name] = {
        "input_digest": "0" * 64,
        "summary": {},
        "statuses": {},
    }
    monkeypatch.setattr(differential, "REFERENCE", tmp_path / "reference.json")
    differential.REFERENCE.write_text(json.dumps(reference))
    with pytest.raises(ValueError, match="stale frozen TypeScript reference"):
        differential.reference(case)


def test_two_runs_of_the_frontend_are_byte_identical(tmp_path: Path) -> None:
    scenario = typescript_scenarios.SCENARIOS[0]
    typescript_scenarios.write(tmp_path, scenario)
    request = differential.request_for(tmp_path, scenario.roots, "app")
    runs = [
        subprocess.run(
            differential.FRONTEND, input=encode_request(request), capture_output=True, check=True
        ).stdout
        for _ in range(2)
    ]
    assert runs[0] == runs[1]
