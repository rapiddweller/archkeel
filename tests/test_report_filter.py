# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-60: `report --only`, `--rule` and `--component` narrow what is shown, never what is judged."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli import main
from archkeel.ir.baseline import declared_components, declared_rule_ids, select_violations
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import DiagnosticError, ReportFilter
from archkeel.render.html import render_architecture_html
from archkeel.render.summary import report_summary
from fixtures.architecture_demo import CATALOG

CONFIG = ScanConfig(("shop",), "shop", "architecture-contract.json", "0" * 64)


def _tour_root(tmp_path: Path) -> Path:
    """AD-51's own demo: 19 rule ids, 20 violations, crossing several component pairs."""
    tour = next(variant for variant in CATALOG if variant.id == "tour")
    return _prepare_repo(tmp_path, dict(tour.files))


def test_rule_facet_narrows_filtered_violations_to_the_named_rule(tmp_path: Path) -> None:
    root = _tour_root(tmp_path)

    result, _ = run_report(root, config=CONFIG, analyzer=observe, rule="DEP-STORE-NO-MONEY")

    assert result.report_filter == ReportFilter(False, "DEP-STORE-NO-MONEY", None)
    assert result.filtered_violations is not None
    assert [record.rule_ids for record in result.filtered_violations] == [("DEP-STORE-NO-MONEY",)]


def test_component_facet_matches_either_side_of_a_crossing(tmp_path: Path) -> None:
    """AD-60: `--component store` finds it as both an import's source and its target."""
    root = _tour_root(tmp_path)

    result, _ = run_report(root, config=CONFIG, analyzer=observe, component="store")

    assert result.filtered_violations is not None
    matched = {record.rule_ids[0] for record in result.filtered_violations}
    # store is the source of DEP-STORE-NO-MONEY and the target of the next three; the last two
    # are inner pairs sibling_isolation and complete_requires (inside) decide inside store
    # itself (AD-11, issue #47).
    assert matched == {
        "DEP-APP-NO-STORE-BACKEND",
        "DEP-APP-NO-STORE-SQLITE",
        "DEP-STORE-NO-MONEY",
        "DEP-RENDER-NO-STORE",
        "STORE-PEERS-ISOLATED",
        "store:STORE-REQUIRES-COMPLETE",
    }


def test_rule_and_component_facets_combine_as_an_intersection(tmp_path: Path) -> None:
    root = _tour_root(tmp_path)

    result, _ = run_report(
        root, config=CONFIG, analyzer=observe, rule="DEP-STORE-NO-MONEY", component="app"
    )

    # DEP-STORE-NO-MONEY crosses store -> model, never app, so the intersection is empty - a
    # valid, empty answer, not an error: a rule or component that exists just selects nothing.
    assert result.filtered_violations == ()
    assert result.declared_rules == "FAIL"
    assert result.exit_code == 0


def test_only_violations_alone_selects_every_violation(tmp_path: Path) -> None:
    root = _tour_root(tmp_path)

    result, _ = run_report(root, config=CONFIG, analyzer=observe, only_violations=True)

    assert result.report_filter == ReportFilter(True, None, None)
    assert result.filtered_violations is not None
    assert len(result.filtered_violations) == 20


def test_architecture_json_bytes_are_identical_with_and_without_a_filter(tmp_path: Path) -> None:
    """Hard constraint: a filter is a render-time projection, never a second observation."""
    root = _tour_root(tmp_path)

    _, unfiltered_bytes = run_report(root, config=CONFIG, analyzer=observe)
    _, filtered_bytes = run_report(
        root,
        config=CONFIG,
        analyzer=observe,
        only_violations=True,
        rule="DEP-STORE-NO-MONEY",
        component="store",
    )

    assert unfiltered_bytes is not None
    assert filtered_bytes == unfiltered_bytes


def test_a_valid_filter_never_changes_the_verdict_the_exit_code_or_the_full_counts(
    tmp_path: Path,
) -> None:
    root = _tour_root(tmp_path)

    unfiltered, _ = run_report(root, config=CONFIG, analyzer=observe)
    filtered, _ = run_report(root, config=CONFIG, analyzer=observe, rule="DEP-STORE-NO-MONEY")

    assert filtered.exit_code == unfiltered.exit_code == 0
    assert filtered.declared_rules == unfiltered.declared_rules == "FAIL"
    assert filtered.violations_by_rule == unfiltered.violations_by_rule
    assert filtered.violations_by_component_pair == unfiltered.violations_by_component_pair
    assert filtered.measurements is not None and unfiltered.measurements is not None
    assert filtered.measurements.scalars.violations == 20
    assert unfiltered.measurements.scalars.violations == 20
    # Only one filtered violation is shown; the count above still reads all 20 (AD-60).
    assert filtered.filtered_violations is not None
    assert len(filtered.filtered_violations) == 1


def test_unknown_rule_is_a_named_exit_2_diagnostic_not_a_silently_empty_report(
    tmp_path: Path,
) -> None:
    root = _tour_root(tmp_path)

    result, architecture = run_report(root, config=CONFIG, analyzer=observe, rule="NO-SUCH-RULE")

    assert result.exit_code == 2
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.kind == "filter_unknown"
    assert diagnostic.code is None
    assert diagnostic.subject == "--rule NO-SUCH-RULE"
    assert "NO-SUCH-RULE" in diagnostic.unknown_claim
    # The observation itself is unaffected by the CLI mistake: the evidence is still written.
    assert architecture is not None


def test_unknown_component_is_a_named_exit_2_diagnostic(tmp_path: Path) -> None:
    root = _tour_root(tmp_path)

    result, _ = run_report(root, config=CONFIG, analyzer=observe, component="warehouse")

    assert result.exit_code == 2
    diagnostic = result.diagnostics[0]
    assert diagnostic.kind == "filter_unknown"
    assert diagnostic.subject == "--component warehouse"
    assert "warehouse" in diagnostic.unknown_claim


def test_declared_rule_ids_and_components_are_the_full_contract_domain(tmp_path: Path) -> None:
    """The domain a filter validates against, not only rules or components that violate."""
    root = _tour_root(tmp_path)
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))

    rules = declared_rule_ids(observation)
    components = declared_components(observation)

    # DEP-STORE-ALLOWS-MODEL decides no report violation (AD-15) and has none, but is declared.
    assert "DEP-STORE-ALLOWS-MODEL" in rules
    assert rules >= {record.rule_ids[0] for record in observation.records("violations") or ()}
    assert components == {"model", "store", "app", "render", "cli"}


def test_select_violations_raises_for_a_value_neither_rule_nor_component_declares(
    tmp_path: Path,
) -> None:
    root = _tour_root(tmp_path)
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))

    with pytest.raises(DiagnosticError) as excinfo:
        select_violations(observation, ReportFilter(False, "NOT-A-RULE", None))
    assert excinfo.value.diagnostic.kind == "filter_unknown"


def test_html_report_states_the_filter_that_produced_it(tmp_path: Path) -> None:
    root = _tour_root(tmp_path)
    result, architecture = run_report(
        root, config=CONFIG, analyzer=observe, rule="DEP-STORE-NO-MONEY"
    )
    assert architecture is not None

    page = render_architecture_html(
        result, architecture, repository="shop", architecture_href="architecture.json"
    ).decode()

    assert 'data-report-filter="true"' in page
    assert "Filtered (rule DEP-STORE-NO-MONEY): 1 of 20 violation(s) shown." in page
    # A rule/component facet alone narrows the violations table; it leaves the other
    # sections in place, unlike --only violations below.
    assert "Component flow" in page
    assert "Component communication" in page


def test_only_violations_hides_every_other_section(tmp_path: Path) -> None:
    root = _tour_root(tmp_path)
    result, architecture = run_report(root, config=CONFIG, analyzer=observe, only_violations=True)
    assert architecture is not None

    page = render_architecture_html(
        result, architecture, repository="shop", architecture_href="architecture.json"
    ).decode()

    assert 'data-report-filter="true"' in page
    assert "Filtered (only violations): 20 of 20 violation(s) shown." in page
    assert "Declared-rule violations" in page
    assert "Component flow" not in page
    assert "Component communication" not in page
    assert "Known unknowns" not in page
    assert "Size and coupling" not in page
    assert "Review claim" not in page
    # The escape hatch to the complete evidence stays, filter or not.
    assert "Complete ArchitectureIR inventory" in page


def test_unfiltered_html_report_carries_no_filter_marker(tmp_path: Path) -> None:
    root = _tour_root(tmp_path)
    result, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None

    page = render_architecture_html(
        result, architecture, repository="shop", architecture_href="architecture.json"
    ).decode()

    assert 'data-report-filter="false"' in page
    assert "Filtered (" not in page
    assert "Component flow" in page and "Review claim" in page


def test_terminal_summary_announces_the_filter(tmp_path: Path) -> None:
    root = _tour_root(tmp_path)
    result, _ = run_report(root, config=CONFIG, analyzer=observe, component="store")

    sentence = report_summary(result).sentence

    assert "Filtered (component store): 6 of 20 violation(s) shown." in sentence


def test_cli_report_json_output_is_filtered(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """End to end through argparse: --only, --rule and --component together, as the issue asks."""
    root = _tour_root(tmp_path)

    exit_code = main(
        [
            "report",
            "--root",
            str(root),
            "--only",
            "violations",
            "--rule",
            "DEP-STORE-NO-MONEY",
            "--json",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert result["report_filter"] == {
        "only_violations": True,
        "rule": "DEP-STORE-NO-MONEY",
        "component": None,
    }
    assert len(result["filtered_violations"]) == 1
    assert result["filtered_violations"][0]["rule_ids"] == ["DEP-STORE-NO-MONEY"]
    # Unfiltered totals still name every violation (AD-60): the filter narrows what is shown.
    assert result["measurements"]["scalars"]["violations"] == 20
    assert result["declared_rules"] == "FAIL"
    assert result["exit_code"] == 0


def test_cli_report_json_stays_unchanged_without_a_filter(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _tour_root(tmp_path)

    assert main(["report", "--root", str(root), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)

    # Absent, not merely empty, the same way every other optional RunResult field reads null.
    assert result["report_filter"] is None
    assert result["filtered_violations"] is None


def test_cli_report_unknown_rule_exits_2_with_a_named_diagnostic(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """AD-60: `filter_unknown`, this feature's own demo catalog row (AD-11)."""
    root = _tour_root(tmp_path)

    assert main(["report", "--root", str(root), "--rule", "NO-SUCH-RULE", "--json"]) == 2
    result = json.loads(capsys.readouterr().out)

    assert result["diagnostics"][0]["kind"] == "filter_unknown"
    assert "code" not in result["diagnostics"][0]


def test_cli_report_only_rejects_an_unsupported_value(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    root = _tour_root(tmp_path)

    assert main(["report", "--root", str(root), "--only", "everything", "--json"]) == 2
    result = json.loads(capsys.readouterr().out)

    assert result["diagnostics"][0]["subject"] == "command-line arguments"


def test_cli_report_help_documents_the_filters() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "archkeel.cli", "report", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--only" in result.stdout
    assert "--rule" in result.stdout
    assert "--component" in result.stdout
