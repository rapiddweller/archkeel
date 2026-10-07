# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11: every catalogued demo variant produces its declared findings, or cites evidence."""

import json
import shutil
import subprocess
import sys
from dataclasses import fields as dataclass_fields
from dataclasses import replace
from pathlib import Path
from typing import get_args, get_type_hints

import pytest

from archkeel.check.expectation import GUARDRAIL_DIMENSIONS
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.validation import run_validate
from archkeel.cli import main
from archkeel.cli.config import load_config
from archkeel.cli.observe import observe, observer_for
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.measurements import SCALARS, compare_measurements
from archkeel.ir.model import (
    ArchitectureRule,
    ContractDeclarations,
    DiagnosticCode,
    DiagnosticKind,
    ForbiddenConstructKind,
    RuleVerdict,
)
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations
from archkeel.render.html import render_architecture_html
from archkeel.render.summary import badge, report_summary
from fixtures import architecture_demo
from fixtures.architecture_demo import CATALOG, markdown
from fixtures.architecture_demo import main as demo_main
from fixtures.demo_catalog_check import build_and_run_check
from fixtures.demo_catalog_support import FIXTURE_DIR, Variant, apply_overlay
from fixtures.demo_catalog_widening import build_and_run_against

ROOT = Path(__file__).parents[1]
CONFIG = ScanConfig(("shop",), "shop", "architecture-contract.json", "0" * 64)
_SAMPLE_VARIANTS = [
    variant
    for variant in CATALOG
    if variant.evidence is None and variant.check is None and variant.against is None
]
_CHECK_VARIANTS = [variant for variant in CATALOG if variant.check is not None]
_AGAINST_VARIANTS = [variant for variant in CATALOG if variant.against is not None]
# A scalar row and its guardrail row share one CheckExpectation, so each protocol runs once.
_UNIQUE_CHECK_RUNS = list({id(variant.check): variant for variant in _CHECK_VARIANTS}.values())
# Raising these makes typed code raise instead of returning FAIL; see demo_catalog_evidence.py.
_CLASS_B_TESTED_ONLY = {
    "SCALARS:coverage_failures",
    "GUARDRAIL_DIMENSIONS:unknowns",
    "GUARDRAIL_DIMENSIONS:dependency_edges",
    "coverage_must_pass",
}


def test_variant_ids_are_unique() -> None:
    ids = [variant.id for variant in CATALOG]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "variant_id",
    [
        "target-hierarchy-positive",
        "target-hierarchy-ambiguous",
        "target-hierarchy-missing",
        "target-hierarchy-cycle",
    ],
)
def test_target_hierarchy_demo_reports_declared_targets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    variant_id: str,
) -> None:
    output = tmp_path / f"{variant_id}.json"

    assert demo_main(["--replay", variant_id, "--output", str(output)]) == 0
    validation, report = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert validation["exit_code"] == 0
    assert report["declared_rules"] == "UNKNOWN"
    assert [
        assessment["id"]
        for assessment in report["rule_assessments"]
        if assessment["status"] == "UNKNOWN"
    ] == ["store:STORE-REQUIRES-COMPLETE"]

    model = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    graph = architecture_report(model).target
    assert graph is not None
    html = output.with_suffix(".report.html").read_text()
    marker = html.index('id="flow-data"')
    atlas = json.loads(html[html.index(">", marker) + 1 : html.index("</script>", marker)])["atlas"]
    assert {item["id"] for item in atlas["components"]} == {
        item.component_id for item in graph.component_intents
    }
    assert atlas["components"]
    assert output.with_name(atlas["detail_page"]).is_file()
    intents = {item.component_id: item for item in graph.component_intents}
    assert {"COMP-APP", "COMP-CLI", "COMP-STORE"} <= intents.keys()
    if variant_id == "target-hierarchy-positive":
        layout = next(item for item in report["rule_assessments"] if item["id"] == "ROOT-LAYOUT")
        assert (layout["status"], layout["provenance"]) == ("PASS", ["docs/architecture/shop.md"])
        assert intents["COMP-APP"].public == ("shop.app.orders:place_order",)
        assert any(
            item.source_id == "COMP-APP"
            and item.target_id == "COMP-STORE"
            and item.through == ("shop.store.repository:OrderRepository",)
            for item in graph.relationships
            if item.kind == "requires"
        )
        assert any(item.parent_id == "COMP-STORE" for item in graph.component_intents)
    elif variant_id == "target-hierarchy-ambiguous":
        assert sum("shop.app" in item.allowed_children for item in graph.layout_rules) == 2
    elif variant_id == "target-hierarchy-missing":
        assert any("shop.missing" in item.allowed_children for item in graph.layout_rules)
    else:
        assert {
            (item.source_id, item.target_id)
            for item in graph.relationships
            if item.kind == "requires"
        } >= {("COMP-APP", "COMP-STORE"), ("COMP-CLI", "COMP-APP"), ("COMP-STORE", "COMP-APP")}
        assert (
            next(
                item for item in report["rule_assessments"] if item["id"] == "COMPONENT-NO-CYCLES"
            )["status"]
            == "PASS"
        )


def test_recursive_wide_package_root_executes(tmp_path: Path) -> None:
    variant = next(item for item in CATALOG if item.id == "class-a-recursive-wide-package")
    root = _prepare_repo(tmp_path, dict(variant.files), variant.fixture)
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from shop.store.backend.tasks import run; assert len(run()) == 8",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_recursive_wide_package_contains_an_isolated_observed_module(tmp_path: Path) -> None:
    variant = next(item for item in CATALOG if item.id == "class-a-recursive-wide-package")
    root = _prepare_repo(tmp_path, dict(variant.files), variant.fixture)
    result, architecture = run_report(
        root, config=load_config(root, variant.config), analyzer=observe
    )
    assert result.exit_code == 0
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    isolated = "shop.store.backend.tasks.isolated"
    assert isolated in {
        item.data.get("qualified_name") for item in observation.records("modules") or ()
    }
    assert not any(
        item.data.get("source") == isolated or item.data.get("target") == isolated
        for item in observation.records("dependency_edges") or ()
        if item.data.get("level") == "module"
    )


def test_demo_replay_writes_cli_json_and_html_without_overwrite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "nested" / "architecture.json"
    assert demo_main(["--replay", "class-a-recursive-wide-package", "--output", str(output)]) == 0
    validation, result = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    html = output.with_name("architecture.report.html")
    assert validation["command"] == "validate"
    assert validation["exit_code"] == 0
    assert result["command"] == "report"
    assert result["artifact"] == str(output)
    assert json.loads(output.read_text())["source"]["source_digest"]
    assert "<html" in html.read_text().lower()

    output.write_text("preserve me")
    assert demo_main(["--replay", "class-a-recursive-wide-package", "--output", str(output)]) == 2
    capsys.readouterr()
    assert output.read_text() == "preserve me"
    protocol = tmp_path / "protocol.json"
    assert demo_main(["--replay", "protocol-ordered", "--output", str(protocol)]) == 2
    capsys.readouterr()
    assert not protocol.exists()
    unsupported_against = tmp_path / "unsupported-against.json"
    assert (
        demo_main(["--replay", "against-widened-unamended", "--output", str(unsupported_against)])
        == 2
    )
    capsys.readouterr()
    assert not unsupported_against.exists()

    evidence = tmp_path / "evidence.json"
    assert (
        demo_main(["--replay", "validation-observation-incomplete", "--output", str(evidence)]) == 2
    )
    capsys.readouterr()
    assert not evidence.exists()
    assert not evidence.with_name("evidence.report.html").exists()

    unknown = tmp_path / "unknown.json"
    assert demo_main(["--replay", "not-a-catalog-row", "--output", str(unknown)]) == 2
    capsys.readouterr()
    assert not unknown.exists()
    assert not unknown.with_name("unknown.report.html").exists()

    html_collision = tmp_path / "html-collision.json"
    html = html_collision.with_name("html-collision.report.html")
    html.write_bytes(b"keep this HTML")
    assert (
        demo_main(["--replay", "class-a-recursive-wide-package", "--output", str(html_collision)])
        == 2
    )
    capsys.readouterr()
    assert not html_collision.exists()
    assert html.read_bytes() == b"keep this HTML"


def test_demo_replay_runs_deepest_change_through_validate_against(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "deepest.json"
    assert (
        demo_main(
            ["--replay", "against-recursive-deepest-contract-change", "--output", str(output)]
        )
        == 1
    )
    validation, report = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert validation["command"] == "validate"
    assert validation["failures"] == [
        "rule store:backend:tasks:DEEP-REQUIRES-COMPLETE (complete_requires) removed"
    ]
    assert report["command"] == "report"
    assert output.with_name("deepest.report.html").is_file()
    architecture = json.loads(output.read_text())
    assert len(architecture["contract"]["digest"]) == 64


@pytest.mark.parametrize(
    ("variant_id", "validation_exit"),
    [
        ("validation-graph-drift-write-graph", 2),
        ("validation-baseline-refused", 1),
    ],
)
def test_demo_replay_preserves_validate_failure_before_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    variant_id: str,
    validation_exit: int,
) -> None:
    output = tmp_path / f"{variant_id}.json"

    assert demo_main(["--replay", variant_id, "--output", str(output)]) == validation_exit
    results = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert [item["command"] for item in results] == ["validate", "report"]
    assert results[0]["exit_code"] == validation_exit
    if variant_id == "validation-graph-drift-write-graph":
        assert {item["code"] for item in results[0]["diagnostics"]} == {"graph.drift"}
    else:
        assert any("--write-baseline refused" in item for item in results[0]["failures"])
        assert results[1]["baseline_comparisons"] == [
            {
                "current_count": 0,
                "known_count": 1,
                "new_count": 0,
                "resolved_count": 0,
                "rules": ["DEP-STORE-NO-MONEY"],
                "shared_count": 0,
                "status": "unknown",
                "subjects": ["shop.model.entities.Money", "shop.store.legacy"],
            },
            {
                "current_count": 1,
                "known_count": 0,
                "new_count": 1,
                "resolved_count": 0,
                "rules": ["DEP-STORE-NO-MONEY"],
                "shared_count": 0,
                "status": "new",
                "subjects": ["shop.model.entities.Money", "shop.store.repository"],
            },
        ]
    assert results[1]["command"] == "report"
    if variant_id == "validation-graph-drift-write-graph":
        assert results[1]["baseline_new"] is None
        assert results[1]["baseline_resolved"] is None
    assert output.is_file() and output.stat().st_size > 0
    assert output.with_name(f"{variant_id}.report.html").stat().st_size > 0


def test_demo_replay_rejects_a_corrupt_explicit_baseline_for_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    variant = next(item for item in CATALOG if item.id == "validation-baseline-refused")
    assert variant.baseline is not None
    files = dict(variant.files)
    files[variant.baseline] = "{invalid JSON\n"
    corrupted = replace(variant, files=files)
    monkeypatch.setattr(
        architecture_demo,
        "CATALOG",
        tuple(corrupted if item.id == variant.id else item for item in CATALOG),
    )
    output = tmp_path / "corrupt-baseline.json"

    assert demo_main(["--replay", variant.id, "--output", str(output)]) == 2
    validation, report = (json.loads(line) for line in capsys.readouterr().out.splitlines())

    assert validation["command"] == "validate" and validation["exit_code"] == 2
    assert report["command"] == "report" and report["exit_code"] == 2
    assert any(
        "baseline architecture-baseline.json" in item["unknown_claim"]
        and "invalid JSON" in item["unknown_claim"]
        for item in report["diagnostics"]
    )
    assert report["baseline_comparisons"] is None
    assert not output.exists()
    assert not output.with_name("corrupt-baseline.report.html").exists()


def test_demo_replay_handles_incomplete_report_without_empty_reservations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "missing-child.json"
    html = output.with_name("missing-child.report.html")

    assert demo_main(["--replay", "validation-contract-invalid", "--output", str(output)]) == 2
    results = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert [item["command"] for item in results] == ["validate", "report"]
    assert [item["exit_code"] for item in results] == [2, 2]
    assert results[-1]["observation_complete"] == "UNKNOWN"
    if output.exists():
        assert output.stat().st_size > 0
        parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    if html.exists():
        assert html.stat().st_size > 0
        assert "UNKNOWN" in html.read_text()
    assert output.exists() == html.exists()


def test_demo_replay_uses_catalog_custom_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "tests.json"

    assert demo_main(["--replay", "test-scope-clean", "--output", str(output)]) == 0
    results = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert results[-1]["command"] == "report"
    assert results[0]["command"] == "validate"
    assert results[0]["scan_roots"] == ["tests"]
    assert results[-1]["scan_roots"] == ["tests"]


def test_recursive_wide_report_includes_catalog_isolated_module_and_package_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    variant = next(item for item in CATALOG if item.id == "class-a-recursive-wide-package")
    combined_root = tmp_path / "combined"
    combined_root.mkdir()
    root = _prepare_repo(combined_root, dict(variant.files), variant.fixture)
    output = tmp_path / "combined-report" / "architecture.json"

    assert main(["report", "--root", str(root), "--output", str(output), "--json"]) == 0
    capsys.readouterr()
    observation = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    modules = {
        str(record.data.get("qualified_name")): record
        for record in observation.records("modules") or ()
    }
    expected = {
        "shop.app.maintenance",
        "shop.app.orders",
        "shop.cli.main",
        "shop.model.entities",
        "shop.render.text",
        "shop.store",
        "shop.store.backend",
        "shop.store.backend.files",
        "shop.store.backend.paths",
        "shop.store.backend.tasks",
        "shop.store.backend.tasks.alpha",
        "shop.store.backend.tasks.bravo",
        "shop.store.backend.tasks.charlie",
        "shop.store.backend.tasks.delta",
        "shop.store.backend.tasks.echo",
        "shop.store.backend.tasks.foxtrot",
        "shop.store.backend.tasks.isolated",
        "shop.store.backend.tasks.source",
        "shop.store.backend.tasks.target",
        "shop.store.codec",
        "shop.store.repository",
        "shop.store.sqlite",
    }
    assert set(modules) == expected
    isolated = modules["shop.store.backend.tasks.isolated"].data
    assert (isolated.get("fan_in"), isolated.get("fan_out")) == (0, 0)
    package_root = modules["shop.store.backend.tasks"].data
    assert package_root.get("file") == "shop/store/backend/tasks/__init__.py"
    assert package_root.get("fan_out", 0) > 0

    graph_report = architecture_report(observation)
    html = output.with_name("architecture.report.html").read_text()
    begin = html.index('id="flow-data"')
    begin = html.index(">", begin) + 1
    atlas = json.loads(html[begin : html.index("</script>", begin)])["atlas"]
    assert {item["name"] for item in atlas["modules"]} == expected
    assert {
        item.qualified_name
        for item in graph_report.observed.entities
        if item.kind == "module" and item.presence == "defined"
    } == expected
    tasks = next(
        item.component_id for item in graph_report.target.component_intents if item.label == "tasks"
    )
    names = {item.id: item.qualified_name for item in graph_report.observed.entities}
    assert {"shop.store.backend.tasks.isolated", "shop.store.backend.tasks"} <= {
        names[item]
        for membership in graph_report.memberships
        if membership.component_id == tasks
        for item in membership.module_ids
    }


def test_class_a_covers_every_rule_kind() -> None:
    items = {variant.item.split(":", 1)[0] for variant in CATALOG if variant.section == "class_a"}
    kinds = {get_args(get_type_hints(rule)["kind"])[0] for rule in get_args(ArchitectureRule)}
    assert kinds <= items


# allowed_dependency records a permission, never a violation: the analyzer never evaluates it
# against a run (docs/rules.md), so no run, `tour` included, can ever make it fire (AD-11).
_KIND_CANNOT_VIOLATE = {"allowed_dependency"}


def _clean_sample_rule_kind_by_id() -> dict[str, str]:
    """Every rule id the clean sample declares, mapped to its kind.

    An inside rule (AD-36) is keyed the way a finding names it, `<component>:<id>`, so it lines
    up directly with `Variant.expected_violations`.
    """
    top = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    mapping = {rule["id"]: rule["kind"] for rule in top["rules"]}
    inside = json.loads((FIXTURE_DIR / "shop/store/architecture-contract.json").read_text())
    mapping.update({f"store:{rule['id']}": rule["kind"] for rule in inside["rules"]})
    return mapping


def test_tour_fires_every_class_a_rule_kind_that_can_violate(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """AD-11: `tour` is the showcase promise, not only the wider catalogue.

    A rule kind present somewhere in the catalogue but missing from `tour`'s own real run is
    exactly the gap that let symbol_placement and boundary_types (AD-58) land without joining
    the showcase (issue #47), and that let `touch_store` drop out of `tour` silently when
    `boundary_types` narrowed to a component's declared facade (issue #55): this asserts against
    the violations a run of `tour` actually produces, sharing that run with
    `test_variant_produces_the_catalogued_findings[tour]` via `_sample_run` rather than scanning
    the sample a second time.
    """
    kinds = {get_args(get_type_hints(rule)["kind"])[0] for rule in get_args(ArchitectureRule)}
    tour = next(variant for variant in CATALOG if variant.id == "tour")
    rule_kind = _clean_sample_rule_kind_by_id()
    _, _, actual_violations, _, _, _, _ = _sample_run(tmp_path_factory, tour)
    fired_kinds = {rule_kind[rule_id] for rule_id in actual_violations}
    assert kinds - _KIND_CANNOT_VIOLATE <= fired_kinds


def test_clean_sample_declares_every_class_a_rule_kind() -> None:
    """AD-11: the clean sample itself declares every Class A rule kind, not only the catalogue.

    test_clean_variant_is_fully_clean proves the declared rules are all satisfied; this proves
    the declaration is complete.
    """
    kinds = {get_args(get_type_hints(rule)["kind"])[0] for rule in get_args(ArchitectureRule)}
    assert kinds <= set(_clean_sample_rule_kind_by_id().values())


def test_class_a_covers_every_forbidden_construct_kind() -> None:
    covered = {
        variant.item.split(":", 1)[1]
        for variant in CATALOG
        if variant.item.startswith("forbidden_construct:")
    }
    assert {kind.value for kind in ForbiddenConstructKind} <= covered


def test_every_diagnostic_code_has_a_variant_or_evidence() -> None:
    produced = {code for variant in CATALOG for code in variant.expected_codes}
    evidenced_codes = {
        variant.item
        for variant in CATALOG
        if variant.evidence is not None and variant.item in set(get_args(DiagnosticCode))
    }
    assert set(get_args(DiagnosticCode)) <= produced | evidenced_codes


def test_every_diagnostic_kind_has_a_variant_or_evidence() -> None:
    # expected_kinds lists uncoded diagnostics only; every coded row is a contract_invalid one.
    produced = {kind for variant in CATALOG for kind in variant.expected_kinds}
    if any(variant.expected_codes for variant in CATALOG):
        produced = produced | {"contract_invalid"}
    evidenced_kinds = {
        variant.item
        for variant in CATALOG
        if variant.evidence is not None and variant.item in set(get_args(DiagnosticKind))
    }
    assert set(get_args(DiagnosticKind)) <= produced | evidenced_kinds


def test_class_a_shows_exact_sources_beside_its_prefix_twin() -> None:
    """AD-49: one nested handler, allowed under a prefix and reported under the exact name."""
    rows = {variant.item: variant for variant in CATALOG}
    prefix = rows["forbidden_construct:allowed_sources"]
    exact = rows["forbidden_construct:exact_sources"]
    assert prefix.files["shop/cli/main.py"] == exact.files["shop/cli/main.py"]
    assert prefix.expected_violations == ()
    assert exact.expected_violations == ("CONSTRUCT-NO-BROAD-EXCEPT",)


def test_class_b_covers_every_measurement_dimension() -> None:
    items = {variant.item for variant in CATALOG if variant.section == "class_b"}
    expected = {
        *(f"SCALARS:{name}" for name in SCALARS),
        "unresolved_ratio",
        *(f"GUARDRAIL_DIMENSIONS:{name}" for name in GUARDRAIL_DIMENSIONS),
        "coverage_must_pass",
    }
    assert expected <= items

    # A new scalar or dimension fails here until it has a check run.
    checked = {
        variant.item
        for variant in CATALOG
        if variant.section == "class_b" and variant.check is not None
    }
    assert expected - _CLASS_B_TESTED_ONLY <= checked
    tested_only = {
        variant.item
        for variant in CATALOG
        if variant.section == "class_b" and variant.evidence is not None
    }
    assert tested_only == _CLASS_B_TESTED_ONLY


def test_class_c_covers_every_contract_declarations_field() -> None:
    items = {variant.item for variant in CATALOG if variant.section == "class_c"}
    expected = {
        f"ContractDeclarations.{field.name}" for field in dataclass_fields(ContractDeclarations)
    }
    assert expected <= items


def test_check_expectation_names_are_valid_measurements() -> None:
    valid_scalars = {*SCALARS, "unresolved_ratio"}
    for variant in CATALOG:
        if variant.check is None:
            continue
        assert set(variant.check.regressed_scalars) <= valid_scalars
        assert set(variant.check.regressed_dimensions) <= set(GUARDRAIL_DIMENSIONS)


def test_evidence_paths_exist() -> None:
    missing = [
        variant.id
        for variant in CATALOG
        if variant.evidence is not None and not (ROOT / variant.evidence).is_file()
    ]
    assert missing == []


def _prepare_repo(
    tmp_path: Path, files: dict[str, str | None], fixture: Path = FIXTURE_DIR
) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(fixture, root)
    apply_overlay(root, files)
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "demo@example.invalid"],
        ["git", "config", "user.name", "Demo"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "variant"],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True)
    return root


def _report_findings(
    root: Path, config: ScanConfig
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...], RuleVerdict]:
    """Violations, `unknowns` (kind, subject) pairs and the declared-rules verdict of one report.

    `run_validate` never populates `RunResult.observation` on a passing run (only its
    diagnostics reach the caller), so `expected_unknowns` has nowhere to read from there;
    `run_report`'s own decoded model already stands in for violations below, and carries the
    `unknowns` section too, so checking it costs no second scan of the sample.
    """
    report, architecture = run_report(
        root,
        config=config,
        analyzer=observer_for(
            config.language, collector_argv=config.collector_argv, tsconfig=config.tsconfig
        ),
    )
    if architecture is None:
        return (), (), report.declared_rules
    summary = report_summary(report)
    expected = badge(
        "NOT CHECKED"
        if report.exit_code == 2 and report.rule_assessments is None
        else report.declared_rules
    )
    assert summary.decision == expected
    assert (
        next(row.value for row in summary.verdicts if row.key == "declared_rules")
        == report.declared_rules
    )
    page = render_architecture_html(
        report, architecture, repository="sample", architecture_href="architecture.json"
    ).decode()
    assert f'data-decision="{expected.state}"' in page
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    violations = trace_valid_violations(observation)
    actual_violations = tuple(
        sorted(item.rule_ids[0] if item.rule_ids else item.id for item in violations)
    )
    actual_unknowns = tuple(
        sorted(
            (record.kind, subject)
            for record in observation.records("unknowns") or ()
            for subject in record.subjects
        )
    )
    return actual_violations, actual_unknowns, report.declared_rules


# Keyed by variant id, so a variant several tests need (`tour`) is run once per session, not
# once per test: `_sample_run` is the only place that materializes and analyzes a sample variant.
_SampleRun = tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[tuple[str, str], ...],
    int,
    tuple[str, ...],
    RuleVerdict,
]
_SAMPLE_RUN_CACHE: dict[str, _SampleRun] = {}


def _sample_run(tmp_path_factory: pytest.TempPathFactory, variant: Variant) -> _SampleRun:
    """Actual (codes, kinds, violations, unknowns, ...) from a real run, cached by id.

    The configuration is the variant's own sample's `archkeel.toml`, read the way the CLI reads
    it, so a sample in another language runs exactly as a user's repository would.
    """
    if variant.id not in _SAMPLE_RUN_CACHE:
        root = _prepare_repo(
            tmp_path_factory.mktemp(variant.id), dict(variant.files), variant.fixture
        )
        baseline = root / variant.baseline if variant.baseline is not None else None
        config = load_config(root, variant.config)
        validate_result, _ = run_validate(
            root,
            config,
            observer_for(
                config.language, collector_argv=config.collector_argv, tsconfig=config.tsconfig
            ),
            baseline=baseline,
            write_baseline=variant.write_baseline,
        )
        actual_codes = tuple(sorted(item.code for item in validate_result.diagnostics if item.code))
        actual_kinds = tuple(
            sorted(item.kind for item in validate_result.diagnostics if item.code is None)
        )
        actual_violations, actual_unknowns, declared_rules = _report_findings(root, config)
        if validate_result.observation_complete == "PASS":
            assert validate_result.declared_rules == declared_rules
        _SAMPLE_RUN_CACHE[variant.id] = (
            actual_codes,
            actual_kinds,
            actual_violations,
            actual_unknowns,
            validate_result.exit_code,
            validate_result.failures,
            declared_rules,
        )
    return _SAMPLE_RUN_CACHE[variant.id]


@pytest.mark.parametrize("variant", _SAMPLE_VARIANTS, ids=lambda v: v.id)
def test_variant_produces_the_catalogued_findings(
    tmp_path_factory: pytest.TempPathFactory, variant: Variant
) -> None:
    actual_codes, actual_kinds, actual_violations, actual_unknowns, _, _, declared_rules = (
        _sample_run(tmp_path_factory, variant)
    )
    assert actual_codes == variant.expected_codes
    assert actual_kinds == variant.expected_kinds
    assert actual_violations == variant.expected_violations
    # Subset, not equality: dynamic_call_limit/context_alias_limit/boundary_type_limit fire on
    # every sample scan regardless of this variant's own overlay (see Variant.expected_unknowns).
    assert set(variant.expected_unknowns) <= set(actual_unknowns)
    if variant.expected_declared_rules is not None:
        assert declared_rules == variant.expected_declared_rules


def test_dynamic_namespace_publication_keeps_candidate_usage_unknown(tmp_path: Path) -> None:
    variant = next(
        item for item in CATALOG if item.id == "class-a-forbidden-construct-inside-violation"
    )
    root = _prepare_repo(tmp_path, dict(variant.files))
    config = load_config(root, variant.config)
    validation, _ = run_validate(root, config, observe)
    assert "interface.unused" not in {item.code for item in validation.diagnostics}
    assert "interface.usage_unknown" in {item.code for item in validation.diagnostics}

    report, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    assert {item.rule_ids[0] for item in trace_valid_violations(observation)} == {
        "store:STORE-NO-EVAL"
    }
    assessment = next(
        item for item in report.rule_assessments or () if item.id == "INTERFACE-BOUNDARY"
    )
    assert assessment.status == "UNKNOWN"
    assert any(
        item.kind == "interface_symbol_limit" for item in observation.records("unknowns") or ()
    )


@pytest.mark.parametrize("name", ["OrderRepository", "_OrderRepository"])
def test_cyclic_publication_stays_unknown_without_weakening_private_imports(
    tmp_path: Path, name: str
) -> None:
    files = {
        "shop/store/__init__.py": f"from .api import {name}\n__all__ = ['{name}']\n",
        "shop/store/api.py": f"from shop.store import {name}\n__all__ = ['{name}']\n",
        "shop/app/orders.py": (FIXTURE_DIR / "shop/app/orders.py")
        .read_text()
        .replace("from shop.store import OrderRepository", f"from shop.store import {name}"),
    }
    root = _prepare_repo(tmp_path, files)
    report, architecture = run_report(root, config=load_config(root), analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    imports = [
        item
        for item in observation.records("imports") or ()
        if item.data.get("source_module") == "shop.app.orders" and item.data.get("symbol") == name
    ]
    [imported] = imports
    assert imported.data.get("reexport_candidates") == ()
    interface = next(
        item for item in report.rule_assessments or () if item.id == "INTERFACE-BOUNDARY"
    )
    assert interface.status == ("FAIL" if name.startswith("_") else "UNKNOWN")


def test_unproven_ordinary_reexport_stays_unknown_in_cli_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    variant = next(
        item
        for item in CATALOG
        if item.id == "class-a-boundary-types-ordinary-reexport-chain-unknown"
    )
    root = _prepare_repo(tmp_path, dict(variant.files))

    validate_code = main(["validate", "--root", str(root), "--json"])
    validation = json.loads(capsys.readouterr().out)
    assert validate_code == 0
    assert validation["diagnostics"] == []
    assert validation["declared_rules"] == "UNKNOWN"

    architecture_path = tmp_path / "architecture.json"
    report_code = main(
        ["report", "--root", str(root), "--output", str(architecture_path), "--json"]
    )
    report = json.loads(capsys.readouterr().out)
    assert report_code == 0
    assert report["declared_rules"] == "UNKNOWN"

    observation = parse_observation(
        decode_canonical_model(json.loads(architecture_path.read_bytes()))
    )
    assert not trace_valid_violations(observation)
    uncertain_routes = {
        subject
        for item in observation.records("unknowns") or ()
        if item.kind == "boundary_type_route"
        for subject in item.subjects
    }
    assert uncertain_routes == {
        "shop.render.facade.render_order",
        "shop.render.facade",
    }


@pytest.mark.parametrize(
    ("variant_id", "expected_violations"),
    [
        ("class-a-boundary-types-owned-public-type", ()),
        ("class-a-boundary-types-builtin-dict-allowed", ()),
        (
            "class-a-boundary-types-owned-public-broad-field",
            ("APP-TYPES-NOT-DICT",),
        ),
    ],
)
def test_owned_public_type_field_is_decided_by_cli_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    variant_id: str,
    expected_violations: tuple[str, ...],
) -> None:
    variant = next(item for item in CATALOG if item.id == variant_id)
    root = _prepare_repo(tmp_path, dict(variant.files))

    validate_code = main(["validate", "--root", str(root), "--json"])
    validation = json.loads(capsys.readouterr().out)
    expected_codes = ("rule.violated",) if expected_violations else ()
    assert tuple(sorted(item["code"] for item in validation["diagnostics"])) == expected_codes
    if not expected_violations:
        assert validation["declared_rules"] == "UNKNOWN"
    if expected_violations:
        assert validate_code != 0
    else:
        assert validate_code == 0

    architecture_path = tmp_path / "architecture.json"
    assert main(["report", "--root", str(root), "--output", str(architecture_path), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    if expected_violations:
        assert report["declared_rules"] != "PASS"
    else:
        assert report["declared_rules"] == "UNKNOWN"
        assessments = {item["id"]: item for item in report["rule_assessments"]}
        assert {
            item["id"] for item in report["rule_assessments"] if item["status"] == "UNKNOWN"
        } == {"store:STORE-REQUIRES-COMPLETE"}
        assert assessments["APP-TYPES-NOT-DICT"]["status"] == "PASS"
    observation = parse_observation(
        decode_canonical_model(json.loads(architecture_path.read_bytes()))
    )
    violations = trace_valid_violations(observation)
    assert tuple(sorted(item.rule_ids[0] for item in violations)) == expected_violations
    relevant_unknowns = [
        item
        for item in observation.records("unknowns") or ()
        if item.kind == "boundary_type_route" and "APP-TYPES-NOT-DICT" in item.rule_ids
    ]
    assert relevant_unknowns == []
    if expected_violations:
        [violation] = violations
        assert len(violation.subjects) == 2
        assert "field value" in violation.title
        assert violation.data.get("nested_annotation") == "dict"
    else:
        assert violations == ()


def test_target_empty_responsibilities_keeps_store_rule_unknown_in_cli_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    variant = next(item for item in CATALOG if item.id == "target-empty-responsibilities")
    root = _prepare_repo(tmp_path, dict(variant.files))

    assert main(["validate", "--root", str(root), "--json"]) == 2
    validation = json.loads(capsys.readouterr().out)
    assert [item["code"] for item in validation["diagnostics"]] == [
        "responsibility.missing",
        "responsibility.missing",
    ]
    assert sorted(
        (item["subject"], item["pointer"], item["contract_path"])
        for item in validation["diagnostics"]
    ) == [
        (
            "api in shop/store/architecture-contract.json",
            "/components/0/responsibilities",
            "shop/store/architecture-contract.json",
        ),
        ("app", "/components/2/responsibilities", "architecture-contract.json"),
    ]

    assert main(["report", "--root", str(root), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["declared_rules"] == "UNKNOWN"
    assert {item["id"] for item in report["rule_assessments"] if item["status"] == "UNKNOWN"} == {
        "store:STORE-REQUIRES-COMPLETE"
    }


def test_inside_forbidden_construct_is_reported_by_validate_and_report_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    variant = next(
        item for item in CATALOG if item.id == "class-a-forbidden-construct-inside-violation"
    )
    root = _prepare_repo(tmp_path, dict(variant.files))

    validate_code = main(["validate", "--root", str(root), "--json"])
    validation = json.loads(capsys.readouterr().out)
    assert validate_code == 2
    assert [
        (item["code"], item["subject"], item["pointer"])
        for item in validation["diagnostics"]
        if item["code"] == "rule.violated"
    ] == [("rule.violated", "store:STORE-NO-EVAL", "/components/1/inside")]

    architecture_path = tmp_path / "inside-report.json"
    report_code = main(
        ["report", "--root", str(root), "--output", str(architecture_path), "--json"]
    )
    report = json.loads(capsys.readouterr().out)
    assert report_code == 0
    observation = parse_observation(
        decode_canonical_model(json.loads(architecture_path.read_bytes()))
    )
    assert [
        (item.rule_ids[0], item.subjects)
        for item in trace_valid_violations(observation)
        if item.rule_ids and item.rule_ids[0] == "store:STORE-NO-EVAL"
    ] == [("store:STORE-NO-EVAL", ("shop.store.repository.OrderRepository.save",))]
    assert report["declared_rules"] == "FAIL"


def test_baseline_interface_narrowing_runs_a_real_validate_gate(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    variant = next(item for item in CATALOG if item.id == "validation-baseline-interface-narrowing")
    _, _, _, _, exit_code, failures, _ = _sample_run(tmp_path_factory, variant)

    assert exit_code == 1
    assert failures == (
        "resolved violation: RESOLVED-IMPORT | shop.app.orders.summarize shop.cli.main "
        "(0 observed, 1 in the baseline); rewrite the baseline with --write-baseline",
        "resolved public entry: shop.app.orders:summarize is no longer reached; remove it from "
        "app.public",
    )


def test_baseline_subject_order_and_refusal_rows_run_real_validate_gates(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """AD-106 (#152): a reversed entry is the same violation, and a refusal names the way on."""
    variants = {item.id: item for item in CATALOG}
    reordered = _sample_run(tmp_path_factory, variants["validation-baseline-subject-order"])
    refused = _sample_run(tmp_path_factory, variants["validation-baseline-refused"])

    assert (reordered[4], reordered[5]) == (0, ())
    assert (refused[4], refused[5]) == (
        1,
        (
            "resolved violation: DEP-STORE-NO-MONEY | shop.model.entities.Money "
            "shop.store.legacy (0 observed, 1 in the baseline)",
            "new violation: DEP-STORE-NO-MONEY | shop.model.entities.Money "
            "shop.store.repository (1 observed, 0 in the baseline)",
            "--write-baseline refused: writing would accept the new or increased debt above; "
            "fix the code, or add --accept-new once an architect has decided to accept it",
        ),
    )


def test_measurement_budget_demo_passes_clean_and_fails_on_a_rise(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    variants = {item.id: item for item in CATALOG}
    clean = _sample_run(tmp_path_factory, variants["validation-measurement-budget-clean"])
    risen = _sample_run(tmp_path_factory, variants["validation-measurement-budget-rise"])

    assert (clean[4], clean[5]) == (0, ())
    assert (risen[4], risen[5]) == (
        1,
        ("measurement budget exceeded in cycle_edges: 0->2",),
    )


def test_facade_budget_demo_holds_a_known_gap_and_names_a_new_name(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    variants = {item.id: item for item in CATALOG}
    held = _sample_run(tmp_path_factory, variants["validation-facade-budget-target-first"])
    risen = _sample_run(tmp_path_factory, variants["validation-facade-budget-ratchet"])

    assert (held[4], held[5]) == (0, ())
    assert (risen[4], risen[5]) == (
        1,
        ("measurement budget exceeded in facade_names model: new shop.model.entities:Discount",),
    )


_ROLLUP_ONLY = "Package cycle with 2 members, roll-up only: no module cycle crosses them"
_CYCLE_ROWS = {
    "class-a-no-component-cycles-module-hidden": [
        ("module_scc", ("shop.model.alpha", "shop.model.beta"), "Module cycle with 2 members")
    ],
    "class-a-package-cycle-rollup-only": [
        ("package_scc", ("shop.model", "shop.render"), _ROLLUP_ONLY)
    ],
    "class-a-package-cycle-backed": [
        ("module_scc", ("shop.model.entities", "shop.render.text"), "Module cycle with 2 members"),
        ("package_scc", ("shop.model", "shop.render"), "Package cycle with 2 members"),
    ],
}


@pytest.mark.parametrize(("variant_id", "expected"), _CYCLE_ROWS.items())
def test_cycle_rows_carry_the_cycles_their_summaries_describe(
    tmp_path: Path, variant_id: str, expected: list[tuple[str, tuple[str, ...], str]]
) -> None:
    """AD-98 (#129): a measured cycle the catalogue describes is really in the report.

    The hidden row passes the component rule while the module SCC exists; the package rows
    show one package SCC labelled roll-up only and the same one backed by a module SCC.
    """
    variant = next(item for item in CATALOG if item.id == variant_id)
    root = _prepare_repo(tmp_path, dict(variant.files))
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))

    assert (
        sorted(
            (item.kind, item.subjects, item.title) for item in observation.records("cycles") or ()
        )
        == expected
    )


@pytest.mark.parametrize("variant", _UNIQUE_CHECK_RUNS, ids=lambda v: v.id)
def test_check_variant_produces_the_catalogued_verdicts(tmp_path: Path, variant: Variant) -> None:
    check = variant.check
    assert check is not None
    result = build_and_run_check(tmp_path, variant.files, check.scenario)

    assert result.exit_code == check.exit_code
    assert result.expectation_fulfilled == check.expectation_fulfilled
    assert result.git_predicate == check.git_predicate
    assert result.host_order == check.host_order
    # AD-100: check compares both revisions' calls, so every row names its changed call sites.
    assert result.unresolved_call_changes is not None
    assert (
        tuple(
            (item.change, item.path, item.lines, item.expression)
            for item in result.unresolved_call_changes
        )
        == check.unresolved_calls
    )

    if not check.regressed_scalars and not check.regressed_dimensions:
        # Its product scan's only UNKNOWN is store:STORE-REQUIRES-COMPLETE: the unowned facade.
        assert result.declared_rules == "UNKNOWN"
        return
    delta = result.delta
    assert delta is not None
    ratchets = delta.ratchets
    assert ratchets.status == "SUPPORTED"
    assert ratchets.baseline is not None
    assert ratchets.head is not None
    actual_scalars = {
        name
        for name, _, _, verdict in compare_measurements(ratchets.baseline, ratchets.head)
        if verdict == "FAIL"
    }
    assert actual_scalars == set(check.regressed_scalars)
    # Only the guardrail-comparable dimensions matter here; a new module also adds an
    # incidental api_crossings/dependency_edges entry for its own __future__ import, which is
    # not a guardrail dimension and not part of what any row demonstrates.
    dimensions = {dimension.name: dimension for dimension in delta.dimensions}
    actual_dimensions = {
        name
        for name in GUARDRAIL_DIMENSIONS
        if dimensions[name].after_count > dimensions[name].before_count
    }
    assert actual_dimensions == set(check.regressed_dimensions)


@pytest.mark.parametrize("variant", _AGAINST_VARIANTS, ids=lambda v: v.id)
def test_against_variant_produces_the_catalogued_verdict(tmp_path: Path, variant: Variant) -> None:
    against = variant.against
    assert against is not None
    result = build_and_run_against(tmp_path, variant.files, against, variant.fixture)

    assert result.exit_code == against.exit_code
    assert result.diagnostics == ()
    assert result.failures == against.failures
    assert result.renames == against.renames


def test_graph_drift_names_the_command_or_the_line_it_refuses(tmp_path: Path) -> None:
    """AD-46: a stale page names --write-graph, which then passes; a subgraph is left to a human.

    The rename touches both markers (AD-57), since the shop sample's target graph agrees with
    its observed one today; --write-graph regenerates both in the one page.
    """
    rows = {variant.item: variant for variant in CATALOG}
    stale = _prepare_repo(tmp_path / "stale", dict(rows["graph.drift:write-graph"].files))
    drifted = run_validate(stale, CONFIG, observe)[0].diagnostics
    assert {item.code for item in drifted} == {"graph.drift"}
    assert {"archkeel validate --write-graph" in item.remedy for item in drifted} == {True}
    fixed, files = run_validate(stale, CONFIG, observe, write_graph=True)
    assert (fixed.exit_code, set(files)) == (0, {"docs/architecture/shop.md"})

    refused = _prepare_repo(tmp_path / "refused", dict(rows["graph.drift:subgraph"].files))
    result, files = run_validate(refused, CONFIG, observe, write_graph=True)
    assert files == {}
    assert {item.code for item in result.diagnostics} == {"graph.drift"}
    for item in result.diagnostics:
        assert "`subgraph composition`" in item.remedy
        assert "by hand" in item.remedy


def test_target_graph_drift_leaves_the_observed_graph_untouched(tmp_path: Path) -> None:
    """AD-57: a target-only edit drifts only the target marker; the observed one keeps passing."""
    rows = {variant.item: variant for variant in CATALOG}
    stale = _prepare_repo(
        tmp_path / "target-stale", dict(rows["graph.drift:target-write-graph"].files)
    )
    (drift,) = run_validate(stale, CONFIG, observe)[0].diagnostics
    assert drift.subject == "docs/architecture/shop.md (target graph)"
    assert "archkeel validate --write-graph" in drift.remedy
    fixed, files = run_validate(stale, CONFIG, observe, write_graph=True)
    assert (fixed.exit_code, set(files)) == (0, {"docs/architecture/shop.md"})

    refused = _prepare_repo(
        tmp_path / "target-refused", dict(rows["graph.drift:target-subgraph"].files)
    )
    result, files = run_validate(refused, CONFIG, observe, write_graph=True)
    (drift,) = result.diagnostics
    assert files == {}
    assert drift.subject == "docs/architecture/shop.md (target graph)"
    assert "`subgraph composition`" in drift.remedy
    assert "by hand" in drift.remedy


def _violation_files(root: Path, config: ScanConfig) -> set[tuple[str, str]]:
    """(rule id, source file) for every traced violation of one report run."""
    _, architecture = run_report(root, config=config, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    files = {item.id: item.file for item in observation.evidence}
    return {
        (item.rule_ids[0], files[evidence_id])
        for item in trace_valid_violations(observation)
        for evidence_id in item.evidence_ids
    }


@pytest.mark.parametrize(
    ("variant_id", "expected"),
    [
        (
            "test-scope-helper-in-unit",
            {
                ("TESTS-EXTERNAL-SHOP", "tests/unit/orders.py"),
                ("TESTS-HELPERS-IN-SUPPORT", "tests/unit/orders.py"),
                ("TESTS-REQUIRES-COMPLETE", "tests/integration/test_place_order.py"),
            },
        ),
        ("test-scope-suite-crossing", {("TESTS-REQUIRES-COMPLETE", "tests/unit/test_entities.py")}),
        (
            "test-scope-unit-imports-product",
            {("TESTS-EXTERNAL-SHOP", "tests/unit/test_entities.py")},
        ),
    ],
)
def test_test_scope_failures_name_the_file(
    tmp_path: Path, variant_id: str, expected: set[tuple[str, str]]
) -> None:
    """#143: a moved helper, a suite crossing and a suite importing the product fail at a file."""
    variant = next(item for item in CATALOG if item.id == variant_id)
    root = _prepare_repo(tmp_path, dict(variant.files))
    assert _violation_files(root, load_config(root, variant.config)) == expected


def test_test_scope_leaves_the_product_scan_unchanged(tmp_path: Path) -> None:
    """#143: the product scan reads the same bytes with or without the test scope beside it."""
    scope_files = [
        path.relative_to(FIXTURE_DIR).as_posix()
        for path in (FIXTURE_DIR / "tests").rglob("*")
        if path.is_file()
    ]
    scope_files += ["archkeel-tests.toml", "docs/architecture/tests.md"]
    with_tests = _prepare_repo(tmp_path / "with", {})
    without = _prepare_repo(tmp_path / "without", dict.fromkeys(scope_files))

    observed = []
    for root in (with_tests, without):
        result, architecture = run_report(root, config=load_config(root), analyzer=observe)
        assert architecture is not None
        observation = parse_observation(decode_canonical_model(json.loads(architecture)))
        observed.append(
            (
                result.declared_rules,
                tuple(
                    item.id for item in result.rule_assessments or () if item.status == "UNKNOWN"
                ),
                result.measurements,
                observation.source.scope,
                observation.source.source_digest,
                observation.contract.digest,
            )
        )
    assert observed[0] == observed[1]
    declared_rules, unknown_rules, _, scope, _, _ = observed[0]
    assert (declared_rules, unknown_rules, scope) == (
        "UNKNOWN",
        ("store:STORE-REQUIRES-COMPLETE",),
        ("shop/**/*.py",),
    )


def test_clean_variant_has_no_violations_but_store_scope_is_unknown(tmp_path: Path) -> None:
    clean = next(variant for variant in CATALOG if variant.id == "clean")
    root = _prepare_repo(tmp_path, dict(clean.files))

    validate_result, _ = run_validate(root, CONFIG, observe)
    assert (validate_result.exit_code, validate_result.declared_rules) == (0, "UNKNOWN")
    assert validate_result.diagnostics == ()
    # AD-46: the clean page is what --write-graph writes, so the command leaves it alone.
    assert run_validate(root, CONFIG, observe, write_graph=True)[1] == {}

    report_result, _ = run_report(root, config=CONFIG, analyzer=observe)
    # AD-93 follows collection-contained fields through the declared DTO graph.
    assert report_result.declared_rules == "UNKNOWN"
    assert {
        item.id for item in report_result.rule_assessments or () if item.status == "UNKNOWN"
    } == {"store:STORE-REQUIRES-COMPLETE"}


def test_dart_clean_variant_has_no_violations_but_unknown_cycle_scope(tmp_path: Path) -> None:
    """AD-97: the Dart sample's conditional, deferred and part directives add no finding.

    No violation is the claim. The unsupported Dart cycle-completeness proof keeps the aggregate
    UNKNOWN and names COMPONENT-NO-CYCLES; it does not turn the directive probes into findings.
    """
    clean = next(variant for variant in CATALOG if variant.id == "dart-clean")
    root = _prepare_repo(tmp_path, dict(clean.files), clean.fixture)

    validate_result, _ = run_validate(root, load_config(root), observe)
    assert (validate_result.exit_code, validate_result.diagnostics) == (0, ())
    assert run_validate(root, load_config(root), observe, write_graph=True)[1] == {}

    report_result, _ = run_report(root, config=load_config(root), analyzer=observe)
    assert (report_result.exit_code, report_result.declared_rules) == (0, "UNKNOWN")
    unknown = {item.id for item in report_result.rule_assessments or () if item.status == "UNKNOWN"}
    assert unknown == {"COMPONENT-NO-CYCLES"}


def test_architecture_demo_markdown_matches_generated_output() -> None:
    doc = ROOT / "docs/architecture-demo.md"
    assert doc.read_text() == markdown()
