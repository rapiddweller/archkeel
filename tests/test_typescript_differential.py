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


def _verdict_findings(monkeypatch, old, new, name="unit/core-aggregate"):
    case = differential.Case(
        name,
        "variant",
        Path("."),
        differential.request_for(Path("."), ("src",), "app"),
        variant=VARIANTS[0],
    )
    monkeypatch.setattr(differential, "run_variant", lambda *_: new)
    monkeypatch.setattr(differential, "_statuses", lambda outcome: outcome)
    return differential._verdicts(old, case, Path("."))


@pytest.mark.parametrize(
    "old_rules,new_rules,aggregate,klass",
    [
        ({"FAILURE": "FAIL", "UNCERTAIN": "UNKNOWN"}, None, "FAIL", "equivalent"),
        ({"FAILURE": "FAIL", "PASSING": "PASS"}, None, "FAIL", "equivalent"),
        ({"FAILURE": "FAIL"}, None, "PASS", "defect"),
        ({"PASSING": "PASS", "UNCERTAIN": "UNKNOWN"}, None, "FAIL", "defect"),
        ({}, None, "FAIL", "defect"),
        ({"<diagnostics>": "FAIL", "UNCERTAIN": "UNKNOWN"}, None, "FAIL", "defect"),
        ({"<observation_complete>": "FAIL"}, None, "FAIL", "defect"),
        ({"FAILURE": "FAIL"}, {"FAILURE": "PASS"}, "FAIL", "defect"),
        (
            {"FAILURE": "FAIL", "OTHER": "PASS"},
            {"FAILURE": "FAIL", "OTHER": "FAIL"},
            "FAIL",
            "defect",
        ),
        (
            {"FAILURE": "FAIL", "OTHER": "UNKNOWN"},
            {"FAILURE": "FAIL", "OTHER": "FAIL"},
            "FAIL",
            "defect",
        ),
        ({"FAILURE": "FAIL"}, {}, "FAIL", "defect"),
        ({"FAILURE": "FAIL", "OTHER": "PASS"}, {"FAILURE": "FAIL"}, "FAIL", "defect"),
        ({"FAILURE": "FAIL"}, {"FAILURE": "FAIL", "EXTRA": "PASS"}, "FAIL", "defect"),
        ({"FAILURE": "FAIL"}, {"FAILURE": "FAIL", "EXTRA": "FAIL"}, "FAIL", "defect"),
    ],
)
def test_core_aggregate_failure_requires_identical_known_failed_rules(
    monkeypatch, old_rules, new_rules, aggregate, klass
):
    old = {"<declared_rules>": "UNKNOWN", **old_rules}
    new = {"<declared_rules>": aggregate, **(old_rules if new_rules is None else new_rules)}
    findings, rules, compared = _verdict_findings(monkeypatch, old, new)
    finding = next(item for item in findings if item.subject == "Core verdict <declared_rules>")
    assert finding.klass == klass
    assert compared == len(old.keys() | new.keys())
    if klass == "equivalent":
        assert findings == [finding] and rules == []


@pytest.mark.parametrize("before", ["PASS", "absent"])
def test_other_aggregate_fail_transitions_remain_defects(monkeypatch, before):
    old = {"FAILURE": "FAIL"}
    if before != "absent":
        old["<declared_rules>"] = before
    new = {"<declared_rules>": "FAIL", "FAILURE": "FAIL"}
    findings, _, _ = _verdict_findings(monkeypatch, old, new)
    assert findings[0].klass == "defect"


@pytest.mark.parametrize(
    "metadata,before,after,klass",
    [
        ("<diagnostics>", "parse_error", "", "defect"),
        ("<exit>", "2", "1", "defect"),
        ("<observation_complete>", "UNKNOWN", "PASS", "defect"),
        ("<observation_complete>", "PASS", "UNKNOWN", "more_conservative"),
    ],
)
def test_aggregate_equivalence_does_not_mask_other_metadata_changes(
    monkeypatch, metadata, before, after, klass
):
    old = {"<declared_rules>": "UNKNOWN", "FAILURE": "FAIL", metadata: before}
    new = {**old, "<declared_rules>": "FAIL", metadata: after}
    findings, _, _ = _verdict_findings(monkeypatch, old, new)
    assert {item.subject: item.klass for item in findings} == {
        "Core verdict <declared_rules>": "equivalent",
        f"Core verdict {metadata}": klass,
    }


@pytest.mark.parametrize(
    "case,rule,status,aggregate",
    [
        ("unsupported-target-symbol", "PROBE", "UNKNOWN", "UNKNOWN"),
        ("unsupported-symbol-interface", "PROBE", "FAIL", "FAIL"),
        ("unsupported-symbol-requires", "REQUIRES", "UNKNOWN", "UNKNOWN"),
    ],
)
def test_native_contract_extension_requires_every_exact_verdict(
    monkeypatch, case, rule, status, aggregate
):
    new = {
        **dict.fromkeys(
            [
                "ASSIGNMENT",
                "COMPONENT-CYCLES",
                "DATA-PEERS",
                "DOMAIN-NO-DATA",
                "EXTERNAL-COMPLETE",
                "EXTERNAL-SHOP",
                "LAYOUT",
                "MODULE-CYCLES",
                "REQUIRES",
            ],
            "PASS",
        ),
        rule: status,
        "<declared_rules>": aggregate,
        "<diagnostics>": "",
        "<exit>": "0",
        "<observation_complete>": "PASS",
    }
    old = {
        **dict.fromkeys(new, "UNKNOWN"),
        "<diagnostics>": "rule_unsupported_by_profile",
        "<exit>": "2",
    }
    name = f"variant/typescript-{case}"
    findings, _, _ = _verdict_findings(monkeypatch, old, new, name)
    assert findings and {item.klass for item in findings} == {"verified_extension"}
    for field in new:
        changed = {**new, field: "FAIL" if new[field] != "FAIL" else "PASS"}
        findings, _, _ = _verdict_findings(monkeypatch, old, changed, name)
        assert not any(item.klass == "verified_extension" for item in findings), field
    for before in ({**old, "<exit>": "0"}, {**old, rule: "PASS"}):
        findings, _, _ = _verdict_findings(monkeypatch, before, new, name)
        assert not any(item.klass == "verified_extension" for item in findings)


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
    frozen = json.loads((CATALOGS / "typescript-reference-demos.json").read_text())
    assert groups["variant"] == len(frozen["variants"]) == 34
    assert set(frozen["variants"]) <= {variant.id for variant in VARIANTS}
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
    assert counts["verified_extension"] == 3
    assert sum(
        counts[kind] for kind in ("equivalent", "more_conservative", "verified_extension")
    ) == sum(groups.values())


def test_core_verdicts_never_gain_a_pass_or_a_fail_the_oracle_lacked(
    judged: differential.Verdict,
) -> None:
    cases = judged.report["cases"]
    assert isinstance(cases, list)
    changed = [
        item
        for case in cases
        for item in case["findings"]
        if item["subject"].startswith("Core verdict")
        and item["class"] not in {"equivalent", "verified_extension"}
    ]
    # Non-equivalent changes only become UNKNOWN; aggregate equivalence requires prior FAIL.
    assert all(item["frontend"] == "UNKNOWN" for item in changed)
    assert judged.report["core_statuses_compared"] > 400


def test_native_global_inventory_has_exact_positive_and_unknown_controls(judged):
    def edge(module, name, line, column, builtin=False):
        return [
            [module, "script_global", name, line, column],
            {
                "kind": "BuiltinTarget" if builtin else "UnresolvedTarget",
                "module": None,
                "file": None,
                "runtime": None,
                "declaration": None,
                "package": name if builtin else None,
                "flags": (False, False, False),
            },
        ]

    expected = {
        "variant/typescript-indirect-require": [
            edge("shop.src.main_x2e_ts", "module", 8, 1),
            edge("shop.src.main_x2e_ts", "module", 8, 21),
        ],
        "variant/typescript-syntax-error": [edge("shop.src.domain.order_x2e_ts", "export", 1, 1)],
        "hidden-loader/export-implicit-type-equals-alias": [
            edge("app.src.main_x2e_ts", "mod", 1, 13)
        ],
        "runtime-alias/relative/first": [edge("app.src.runtime_x2e_js", "Error", 1, 7, True)],
        "fixture/H-uml-typescript": [edge("demo.src.core_x2e_ts", "String", 19, 56, True)],
        "scenario/esm-require-and-triple-slash": [
            edge("app.src.main_x2e_mts", "require", 2, 14),
            edge("app.src.main_x2e_mts", "require", 2, 23),
            edge("app.src.main_x2e_mts", "name", 2, 48, True),
        ],
    }
    for extension in ("js", "mjs"):
        for state in ("gap", "complete"):
            expected[f"scenario/explicit-runtime-{extension}-{state}"] = [
                edge(f"app.src.leaf_x2e_{extension}", "Error", 1, 7, True)
            ]
    for module in ("nodenext", "node16"):
        for route in (
            "ts-file",
            "js-extension-for-ts",
            "extensionless-js",
            "directory-index",
            "directory-main",
            "file-before-directory",
            "paths-name",
            "package-main",
        ):
            expected[f"matrix/{module}-module/{route}/main.ts-require"] = [
                edge("app.src.main_x2e_ts", "require", 1, 1)
            ]
    actual = judged.report["native_script_dependencies"]
    assert set(actual) == set(expected)
    for case, edges in expected.items():
        assert sorted(actual[case], key=lambda row: row[0]) == sorted(
            edges, key=lambda row: row[0]
        ), case


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
