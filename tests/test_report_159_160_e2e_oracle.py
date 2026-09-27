# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent real-report fixtures for #159/#160.

The expected verdicts below are frozen from the fixture intent and observed records, before
binding them to the implementation's new public receipt serialization or HTML rows. In
particular, status is not inferred from the absence of a violation in these helpers.
"""

import json
from pathlib import Path

from test_architecture_demo import _prepare_repo
from test_baseline import (
    GETATTR_RULE,
    MOVED_PROBE,
    PROBE,
    _baseline_file,
    _observe,
    _repo,
)
from test_report_filter import _tour_root

from archkeel.cli import main
from archkeel.ir.baseline import KnownViolation, observed_violations
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import Observation, Record
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_dependencies import module_cycle_rule
from fixtures.demo_catalog_support import Variant, contract_with_rule

_PROVENANCE = ("docs/architecture/shop.md",)

# Status, distinct undecided positions, violation records, and declaration provenance.
_TOUR_RECEIPT_ORACLE = {
    "APP-TYPES-NOT-DICT": ("FAIL", 0, 1, _PROVENANCE),
    "CONSTRUCT-NO-DYNAMIC": ("FAIL", 0, 2, _PROVENANCE),
    "DEP-APP-NO-CLI": ("PASS", 0, 0, _PROVENANCE),
    "DEP-APP-ALLOWS-MODEL": ("DECLARATION", 0, 0, _PROVENANCE),
}
_MIXED_TYPES_ORACLE = ("APP-TYPES-NOT-DICT", "FAIL", 1, 1, _PROVENANCE)
_UNKNOWN_ROUTE_ORACLE = ("RENDER-TYPES-NOT-DICT", "UNKNOWN", 1, 0, _PROVENANCE)
_TYPE_CHECKING_ORACLE = ("DEP-APP-NO-STORE-SQLITE", "FAIL", 0, 1, _PROVENANCE)


def _variant(case_id: str) -> Variant:
    return next(variant for variant in CATALOG if variant.id == case_id)


def _cli_report(
    root: Path, tmp_path: Path, capsys, *options: str, expected_exit: int = 0
) -> tuple[dict[str, object], Observation]:
    output = tmp_path / "architecture.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    code = main(["report", "--root", str(root), "--output", str(output), *options, "--json"])
    result = json.loads(capsys.readouterr().out)
    assert code == result["exit_code"] == expected_exit
    assert output.is_file()
    observation = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    return result, observation


def _declared(observation: Observation, rule_id: str) -> Record:
    return next(
        record
        for record in observation.records("declarations") or ()
        if record.id == rule_id and record.evidence_class.value == "DECLARED_RULE"
    )


def _unknown_positions(observation: Observation, rule_id: str) -> set[tuple[str, ...]]:
    """Count concrete undecided positions/routes, not their aggregate limit summary too."""
    return {
        record.subjects
        for record in observation.records("unknowns") or ()
        if rule_id in record.rule_ids
        and record.kind in {"boundary_type_position", "boundary_type_route"}
    }


def _fixture_facts(observation: Observation, rule_id: str) -> tuple[int, int, tuple[str, ...]]:
    declared = _declared(observation, rule_id)
    violations = sum(
        rule_id in record.rule_ids for record in observation.records("violations") or ()
    )
    return len(_unknown_positions(observation, rule_id)), violations, declared.provenance


def test_tour_freezes_pass_fail_and_permission_oracles_from_real_cli_report(
    tmp_path: Path, capsys
) -> None:
    """No violation is not itself proof of PASS; receipts are attached in the post-freeze pass."""
    tour_parent = tmp_path / "tour"
    tour_parent.mkdir()
    root = _tour_root(tour_parent)
    result, observation = _cli_report(root, tmp_path, capsys)

    assert result["declared_rules"] == "FAIL"
    for rule_id, (
        expected_status,
        unknowns,
        violations,
        provenance,
    ) in _TOUR_RECEIPT_ORACLE.items():
        declared = _declared(observation, rule_id)
        assert _fixture_facts(observation, rule_id) == (unknowns, violations, provenance)
        if expected_status == "DECLARATION":
            assert declared.kind == "allowed_dependency"
            assert declared.evidence_class.value == "DECLARED_RULE"
            assert not any(
                rule_id in record.rule_ids
                for section in ("violations", "unknowns")
                for record in observation.records(section) or ()
            )


def test_fail_and_unknown_for_one_rule_are_from_the_same_real_evaluation_scope(
    tmp_path: Path, capsys
) -> None:
    tour = _variant("tour")
    files = dict(tour.files)
    orders_path = "shop/app/orders.py"
    files[orders_path] = files[orders_path].replace(
        "store_dir: object,\n    order_id",
        "store_dir: object,\n    extra_path: Path,\n    order_id",
    )
    assert "extra_path: Path" in files[orders_path]
    root = _prepare_repo(tmp_path, files, tour.fixture)
    _, observation = _cli_report(root, tmp_path, capsys)

    rule_id, expected_status, unknowns, violations, provenance = _MIXED_TYPES_ORACLE
    assert _fixture_facts(observation, rule_id) == (unknowns, violations, provenance)
    records = [
        record for record in observation.records("unknowns") or () if rule_id in record.rule_ids
    ]
    assert [record.kind for record in records].count("boundary_type_position") == 1
    assert [record.kind for record in records].count("boundary_type_limit") == 1
    aggregate = next(record for record in records if record.kind == "boundary_type_limit")
    assert aggregate.data.get("undecided") == 1
    assert expected_status == "FAIL"  # a known violation is not downgraded by partial evidence


def test_unknown_route_is_associated_with_its_rule_not_every_boundary_rule(
    tmp_path: Path, capsys
) -> None:
    variant = _variant("class-a-boundary-types-ordinary-reexport-chain-unknown")
    root = _prepare_repo(tmp_path, dict(variant.files), variant.fixture)
    result, observation = _cli_report(root, tmp_path, capsys)

    rule_id, expected_status, unknowns, violations, provenance = _UNKNOWN_ROUTE_ORACLE
    assert _fixture_facts(observation, rule_id) == (unknowns, violations, provenance)
    assert result["declared_rules"] == "UNKNOWN"
    route = next(
        record
        for record in observation.records("unknowns") or ()
        if record.kind == "boundary_type_route" and rule_id in record.rule_ids
    )
    assert route.subjects == ("shop.render.facade", "shop.render.facade.render_order")
    assert expected_status == "UNKNOWN"


def test_type_checking_edge_is_a_real_violation_not_a_runtime_only_guess(
    tmp_path: Path, capsys
) -> None:
    variant = _variant("class-a-forbidden-dependency-include-type-checking")
    root = _prepare_repo(tmp_path, dict(variant.files), variant.fixture)
    _, observation = _cli_report(root, tmp_path, capsys)

    rule_id, expected_status, unknowns, violations, provenance = _TYPE_CHECKING_ORACLE
    assert _fixture_facts(observation, rule_id) == (unknowns, violations, provenance)
    assert expected_status == "FAIL"


def test_planned_only_entry_is_frozen_as_target_work_not_a_passing_public_api(
    tmp_path: Path, capsys
) -> None:
    variant = _variant("validation-interface-planned-built")
    root = _prepare_repo(tmp_path, dict(variant.files), variant.fixture)
    _, observation = _cli_report(root, tmp_path, capsys)

    contract = json.loads((root / "architecture-contract.json").read_bytes())
    app = next(item for item in contract["components"] if item["label"] == "app")
    assert app["planned"] == ["shop.app.maintenance"]
    assert not any(
        record.subjects == ("shop.app.maintenance",)
        for record in observation.records("declarations") or ()
        if record.kind == "declared_public_api"
    )
    assert not any(
        "shop.app.maintenance" in record.subjects
        for record in observation.records("violations") or ()
    )
    # The UI/status oracle will assert this planned entry is not rendered as PASS.


def test_report_baseline_is_explicit_read_only_and_never_turns_a_failure_into_pass(
    tmp_path: Path, capsys
) -> None:
    root = _repo(tmp_path, "report-baseline", {"shop/model/probe.py": PROBE})
    baseline = _baseline_file(root, observed_violations(_observe(root)))
    before = baseline.read_bytes()
    unbased_result, unbased_observation = _cli_report(root, tmp_path / "unbased", capsys)

    based_result, based_observation = _cli_report(
        root, tmp_path / "based", capsys, "--baseline", str(baseline)
    )

    assert based_result["declared_rules"] == unbased_result["declared_rules"] == "FAIL"
    assert based_result["rule_assessments"] == unbased_result["rule_assessments"]
    assert baseline.read_bytes() == before
    assert unbased_observation == based_observation
    assert based_result["baseline_comparisons"] == []


def test_report_without_baseline_does_not_auto_discover_a_default_file(
    tmp_path: Path, capsys
) -> None:
    root = _repo(tmp_path, "no-auto-baseline", {"shop/model/probe.py": PROBE})
    default_baseline = root / "architecture-baseline.json"
    default_baseline.write_bytes(b"not a valid baseline\n")

    result, observation = _cli_report(root, tmp_path, capsys)

    assert result.get("baseline_comparisons") in (None, [])
    assert result["declared_rules"] == "FAIL"
    assert _fixture_facts(observation, GETATTR_RULE) == (0, 1, ("docs/architecture/shop.md",))


def test_report_baseline_groups_growth_after_line_movement_by_fingerprint_count(
    tmp_path: Path, capsys
) -> None:
    root = _repo(tmp_path, "baseline-growth", {"shop/model/probe.py": PROBE})
    baseline = _baseline_file(root, observed_violations(_observe(root)))
    before = _observe(root)
    moved_twice = MOVED_PROBE.replace(
        '    return getattr(_Box(), "value")\n',
        '    first = getattr(_Box(), "value")\n    return first, getattr(_Box(), "value")\n',
    )
    (root / "shop/model/probe.py").write_text(moved_twice)

    result, observation = _cli_report(root, tmp_path, capsys, "--baseline", str(baseline))
    after = observed_violations(observation)

    assert observed_violations(before)[0].fingerprint == after[0].fingerprint
    assert after == (KnownViolation(after[0].fingerprint, 2, after[0].roles),)
    assert [record.id for record in before.records("violations") or ()] != [
        record.id for record in observation.records("violations") or ()
    ]
    assert result["declared_rules"] == "FAIL"
    assert result["baseline_comparisons"] == [
        f"new violation: {GETATTR_RULE} | shop.model.probe.read (2 observed, 1 in the baseline)"
    ]


def test_report_does_not_claim_baseline_findings_resolved_from_incomplete_observation(
    tmp_path: Path, capsys
) -> None:
    root = _repo(tmp_path, "incomplete-report-baseline", {"shop/model/probe.py": PROBE})
    baseline = _baseline_file(root, observed_violations(_observe(root)))
    (root / "shop/model/probe.py").unlink()
    (root / "shop/model/broken.py").write_text("def broken(:\n")

    result, _ = _cli_report(root, tmp_path, capsys, "--baseline", str(baseline), expected_exit=2)

    assert result["observation_complete"] == "UNKNOWN"
    assert result["baseline_comparisons"] == []


def test_report_rejects_an_invalid_read_only_baseline_without_writing_it(
    tmp_path: Path, capsys
) -> None:
    root = _repo(tmp_path, "invalid-report-baseline", {"shop/model/probe.py": PROBE})
    baseline = root / "invalid.json"
    baseline.write_text("{not json\n")
    before = baseline.read_bytes()

    code = main(["report", "--root", str(root), "--baseline", str(baseline), "--json"])
    result = json.loads(capsys.readouterr().out)

    assert code == result["exit_code"] == 2
    diagnostic = json.dumps(result["diagnostics"])
    assert "invalid.json" in diagnostic and "baseline" in diagnostic
    assert baseline.read_bytes() == before


def test_report_baseline_preserves_a_real_strict_scc_contraction(tmp_path: Path, capsys) -> None:
    header = "# frozen SCC fixture\n"
    files = {
        "shop/model/alpha.py": header + "from shop.model.beta import VALUE as B\nVALUE = 1\n",
        "shop/model/beta.py": (
            header
            + "from shop.model.gamma import VALUE as C\n"
            + "from shop.model.alpha import VALUE as A\nVALUE = C\n"
        ),
        "shop/model/gamma.py": header + "from shop.model.alpha import VALUE as A\nVALUE = 1\n",
        "architecture-contract.json": contract_with_rule(module_cycle_rule(components=["model"])),
    }
    root = _prepare_repo(tmp_path, files)
    baseline = _baseline_file(root, observed_violations(_observe(root)))
    (root / "shop/model/beta.py").write_text(
        header + "from shop.model.alpha import VALUE as A\nVALUE = A\n"
    )

    result, observation = _cli_report(root, tmp_path, capsys, "--baseline", str(baseline))

    contracted = [
        record
        for record in observation.records("violations") or ()
        if record.rule_ids == ("MODEL-MODULES-ACYCLIC",)
    ]
    assert len(contracted) == 1
    assert contracted[0].subjects == (
        "shop.model.alpha",
        "shop.model.beta",
    )
    assert result["declared_rules"] == "FAIL"
    assert result["baseline_comparisons"] == [
        "resolved violation: MODEL-MODULES-ACYCLIC | shop.model.alpha shop.model.beta "
        "shop.model.gamma (0 observed, 1 in the baseline); rewrite the baseline with "
        "--write-baseline",
        "contracted violation: MODEL-MODULES-ACYCLIC | shop.model.alpha shop.model.beta "
        "(1 observed, 0 in the baseline) inside a baselined cycle",
    ]
