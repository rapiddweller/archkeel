# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent real-report fixtures for #159/#160.

The expected verdicts below are frozen from the fixture intent and observed records, before
binding them to the implementation's new public receipt serialization or HTML rows. In
particular, status is not inferred from the absence of a violation in these helpers.
"""

import json
from html.parser import HTMLParser
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
from test_recursive_inside_independent_contracts import (
    COMPONENT_GRAPH_MARKER,
    TARGET_GRAPH_MARKER,
    _commit_tree,
    _forbidden_edge,
    _write_three_levels,
)
from test_report_filter import _tour_root

from archkeel.cli import main
from archkeel.ir.baseline import KnownViolation, observed_violations
from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model, parse_observation
from archkeel.ir.model import Observation, Record
from fixtures.architecture_demo import CATALOG
from fixtures.architecture_demo import main as demo_main
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


def _assessment(result: dict[str, object], rule_id: str) -> dict[str, object]:
    assessments = result["rule_assessments"]
    assert isinstance(assessments, list)
    matches = [item for item in assessments if item["id"] == rule_id]
    assert len(matches) == 1
    return matches[0]


def _assert_assessment(
    result: dict[str, object],
    rule_id: str,
    status: str,
    unknowns: int,
    violations: int,
    provenance: tuple[str, ...],
) -> None:
    assessment = _assessment(result, rule_id)
    assert assessment["status"] == status
    assert assessment["undecided"] == unknowns
    assert assessment["count"] == violations
    assert tuple(assessment["provenance"]) == provenance


class _ReportFilterRows(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.filters_hidden = False
        self._in_report_filters = False
        self.rows: list[dict[str, object]] = []
        self._row: dict[str, object] | None = None
        self._labels: list[tuple[str | None, bool]] = []
        self.filter_fields: list[tuple[str | None, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "form" and "data-report-filters" in values:
            self.filters_hidden = "hidden" in values
            self._in_report_filters = True
        if tag == "label" and self._in_report_filters:
            self._labels.append((values.get("for"), False))
        if tag in {"input", "select"} and self._labels:
            label_for, _ = self._labels[-1]
            if label_for is None or label_for == values.get("id"):
                self._labels[-1] = (label_for, True)
        if tag == "tr" and "data-filter-row" in values:
            self._row = values
        if tag == "strong" and self._row is not None and "data-status" in values:
            self._row["badge-status"] = values["data-status"]

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        if tag == "form" and self._in_report_filters:
            self._in_report_filters = False
        if tag == "label" and self._labels:
            self.filter_fields.append(self._labels.pop())

    def handle_data(self, data: str) -> None:
        if self._row is not None:
            current = self._row.get("_text", "")
            self._row["_text"] = f"{current}{data}"


def _cycle_baseline_fixture(tmp_path: Path, capsys) -> tuple[Path, Path]:
    variant = _variant("class-a-no-component-cycles-module")
    files = dict(variant.files)
    contract = json.loads(files["architecture-contract.json"])
    rule = next(item for item in contract["rules"] if item["id"] == "MODEL-MODULES-ACYCLIC")
    rule["components"] = ["model", "store"]
    files["architecture-contract.json"] = json.dumps(contract, indent=2) + "\n"
    files.update(
        {
            "shop/store/cycle_left.py": (
                "from shop.store import cycle_right\nVALUE = cycle_right.VALUE\n"
            ),
            "shop/store/cycle_right.py": (
                "from shop.store import cycle_left\nVALUE = cycle_left.VALUE\n"
            ),
        }
    )
    root = _prepare_repo(tmp_path, files, variant.fixture)
    _, observation = _cli_report(root, tmp_path / "baseline-report", capsys)
    baseline = _baseline_file(root, observed_violations(observation))
    return root, baseline


def _minimal_contract(root: Path, rules: list[dict[str, object]], labels: set[str]) -> None:
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_bytes())
    contract = {
        "schema_version": contract["schema_version"],
        "components": [item for item in contract["components"] if item["label"] in labels],
        "rules": rules,
    }
    for component in contract["components"]:
        for key in ("capability_id", "inside", "requires", "public"):
            component.pop(key, None)
    path.write_text(json.dumps(contract))


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
        _assert_assessment(result, rule_id, expected_status, unknowns, violations, provenance)
        if expected_status != "DECLARATION":
            receipts = [
                item
                for item in observation.records("scope_observations") or ()
                if item.kind == "rule_evaluation" and item.rule_ids == (rule_id,)
            ]
            assert receipts, f"missing evaluator receipt for {rule_id}"
            assessment = _assessment(result, rule_id)
            assert {item.data.get("scope") for item in receipts} == {assessment["scope"]}
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
        "store_dir: object,\n    extra_path: FutureOrder,\n    order_id",
    )
    assert "extra_path: FutureOrder" in files[orders_path]
    root = _prepare_repo(tmp_path, files, tour.fixture)
    result, observation = _cli_report(root, tmp_path, capsys)

    rule_id, expected_status, unknowns, violations, provenance = _MIXED_TYPES_ORACLE
    assert _fixture_facts(observation, rule_id) == (unknowns, violations, provenance)
    records = [
        record for record in observation.records("unknowns") or () if rule_id in record.rule_ids
    ]
    assert [record.kind for record in records].count("boundary_type_position") == 1
    assert [record.kind for record in records].count("boundary_type_limit") == 1
    aggregate = next(record for record in records if record.kind == "boundary_type_limit")
    assert aggregate.data.get("undecided") == 1
    _assert_assessment(result, rule_id, expected_status, unknowns, violations, provenance)
    assert expected_status == "FAIL"  # a known violation is not downgraded by partial evidence


def test_partial_evidence_blocks_resolved_baseline_count_for_same_failed_rule(
    tmp_path: Path, capsys
) -> None:
    tour = _variant("tour")
    files = dict(tour.files)
    orders_path = "shop/app/orders.py"
    files[orders_path] = files[orders_path].replace(
        "store_dir: object,\n    order_id",
        "store_dir: object,\n    extra_path: FutureOrder,\n    order_id",
    )
    root = _prepare_repo(tmp_path, files, tour.fixture)
    _, before = _cli_report(root, tmp_path / "before", capsys)
    current = observed_violations(before)
    (finding,) = [item for item in current if "APP-TYPES-NOT-DICT" in item.fingerprint.rules]
    baseline = _baseline_file(root, (KnownViolation(finding.fingerprint, 2, finding.roles),))

    result, observation = _cli_report(
        root, tmp_path / "with-baseline", capsys, "--baseline", str(baseline)
    )

    _assert_assessment(result, *_MIXED_TYPES_ORACLE)
    assert _fixture_facts(observation, "APP-TYPES-NOT-DICT") == (1, 1, _PROVENANCE)
    comparisons = result["baseline_comparisons"]
    assert isinstance(comparisons, list)
    resolved_claims = [
        comparison
        for comparison in comparisons
        if comparison["rules"] == ["APP-TYPES-NOT-DICT"] and comparison["resolved_count"] > 0
    ]
    assert not resolved_claims, f"partial evidence lost: {resolved_claims}"


def test_unknown_route_is_associated_with_its_rule_not_every_boundary_rule(
    tmp_path: Path, capsys
) -> None:
    variant = _variant("class-a-boundary-types-ordinary-reexport-chain-unknown")
    root = _prepare_repo(tmp_path, dict(variant.files), variant.fixture)
    result, observation = _cli_report(root, tmp_path, capsys)

    rule_id, expected_status, unknowns, violations, provenance = _UNKNOWN_ROUTE_ORACLE
    assert _fixture_facts(observation, rule_id) == (unknowns, violations, provenance)
    assert result["declared_rules"] == "UNKNOWN"
    _assert_assessment(result, rule_id, expected_status, unknowns, violations, provenance)
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
    result, observation = _cli_report(root, tmp_path, capsys)

    rule_id, expected_status, unknowns, violations, provenance = _TYPE_CHECKING_ORACLE
    assert _fixture_facts(observation, rule_id) == (unknowns, violations, provenance)
    _assert_assessment(result, rule_id, expected_status, unknowns, violations, provenance)
    assert expected_status == "FAIL"


def test_planned_only_entry_is_frozen_as_target_work_not_a_passing_public_api(
    tmp_path: Path, capsys
) -> None:
    variant = _variant("validation-interface-planned-built")
    root = _prepare_repo(tmp_path, dict(variant.files), variant.fixture)
    result, observation = _cli_report(root, tmp_path, capsys)

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
    assert not any(
        "shop.app.maintenance" in str(assessment) for assessment in result["rule_assessments"]
    )


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
    assert (tmp_path / "unbased" / "architecture.json").read_bytes() == (
        tmp_path / "based" / "architecture.json"
    ).read_bytes()
    assert based_result["baseline_comparisons"] == [
        {
            "current_count": 1,
            "known_count": 1,
            "new_count": 0,
            "resolved_count": 0,
            "rules": [GETATTR_RULE],
            "shared_count": 1,
            "status": "known",
            "subjects": ["shop.model.probe.read"],
        }
    ]


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
        {
            "current_count": 2,
            "known_count": 1,
            "new_count": 1,
            "resolved_count": 0,
            "rules": [GETATTR_RULE],
            "shared_count": 1,
            "status": "new",
            "subjects": ["shop.model.probe.read"],
        },
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
    assert result["baseline_comparisons"] is None


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


def test_report_resolves_external_dependency_when_observed_source_removes_import(
    tmp_path: Path, capsys
) -> None:
    variant = _variant("class-a-external-dependency-scope")
    root = _prepare_repo(tmp_path, dict(variant.files), variant.fixture)
    _, before = _cli_report(root, tmp_path / "external-before", capsys)
    baseline_entries = observed_violations(before)
    assert len(baseline_entries) == 1
    assert baseline_entries[0].fingerprint.rules == ("EXTERNAL-JSON-STORE",)
    assert baseline_entries[0].roles == (("shop.app.reporting", "json"),)
    baseline = _baseline_file(root, baseline_entries)

    reporting = root / "shop/app/reporting.py"
    source = reporting.read_text()
    assert "import json" in source and "json.dumps(order.to_dict())" in source
    reporting.write_text(
        source.replace("import json\n", "").replace("json.dumps(order.to_dict())", "order.id")
    )

    result, after = _cli_report(
        root, tmp_path / "external-after", capsys, "--baseline", str(baseline)
    )

    assert any("shop.app.reporting" in record.subjects for record in after.records("modules") or ())
    assert _assessment(result, "EXTERNAL-JSON-STORE")["status"] == "PASS"
    assert result["baseline_comparisons"] == [
        {
            "current_count": 0,
            "known_count": 1,
            "new_count": 0,
            "resolved_count": 1,
            "rules": ["EXTERNAL-JSON-STORE"],
            "shared_count": 0,
            "status": "resolved",
            "subjects": ["json", "shop.app.reporting"],
        }
    ]


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
        {
            "current_count": 1,
            "known_count": 0,
            "new_count": 0,
            "resolved_count": 0,
            "rules": ["MODEL-MODULES-ACYCLIC"],
            "shared_count": 0,
            "status": "contracted",
            "subjects": ["shop.model.alpha", "shop.model.beta"],
        },
        {
            "current_count": 0,
            "known_count": 1,
            "new_count": 0,
            "resolved_count": 1,
            "rules": ["MODEL-MODULES-ACYCLIC"],
            "shared_count": 0,
            "status": "resolved",
            "subjects": ["shop.model.alpha", "shop.model.beta", "shop.model.gamma"],
        },
    ]


def test_model_scoped_cycle_rule_resolves_full_cross_component_scc_removal(
    tmp_path: Path, capsys
) -> None:
    files = {
        "shop/model/alpha.py": "from shop.cli.beta import VALUE\nVALUE = VALUE\n",
        "shop/cli/beta.py": "from shop.model.alpha import VALUE\nVALUE = 1\n",
    }
    root = _repo(tmp_path, "cross-component-cycle", files)
    _minimal_contract(root, [module_cycle_rule(components=["model"])], {"model", "cli"})
    _, before = _cli_report(root, tmp_path / "cross-component-before", capsys)
    (known,) = observed_violations(before)
    assert known.fingerprint.subjects == ("shop.cli.beta", "shop.model.alpha")
    baseline = _baseline_file(root, (known,))

    (root / "shop/cli/beta.py").write_text("VALUE = 1\n")
    result, after = _cli_report(
        root,
        tmp_path / "cross-component-after",
        capsys,
        "--baseline",
        str(baseline),
    )

    assert result["observation_complete"] == "PASS"
    assert _assessment(result, "MODEL-MODULES-ACYCLIC")["status"] == "PASS"
    assert any("shop.model.alpha" in record.subjects for record in after.records("modules") or ())
    assert any("shop.cli.beta" in record.subjects for record in after.records("modules") or ())
    assert result["baseline_comparisons"] == [
        {
            "current_count": 0,
            "known_count": 1,
            "new_count": 0,
            "resolved_count": 1,
            "rules": ["MODEL-MODULES-ACYCLIC"],
            "shared_count": 0,
            "status": "resolved",
            "subjects": ["shop.cli.beta", "shop.model.alpha"],
        }
    ]


def test_narrow_scan_does_not_resolve_omitted_cycle_or_hide_new_cycle_debt(
    tmp_path: Path, capsys
) -> None:
    root, baseline = _cycle_baseline_fixture(tmp_path, capsys)
    (root / "shop/model/gamma.py").write_text("from shop.model import delta\nVALUE = delta.VALUE\n")
    (root / "shop/model/delta.py").write_text("from shop.model import gamma\nVALUE = gamma.VALUE\n")
    (root / "narrow.toml").write_text(
        '[scan]\nroots = ["shop/model"]\nnamespace = "shop"\n'
        'contract = "architecture-contract.json"\n'
    )

    result, observation = _cli_report(
        root,
        tmp_path / "narrow-scan",
        capsys,
        "--config",
        "narrow.toml",
        "--baseline",
        baseline.name,
        expected_exit=2,
    )

    comparisons = result["baseline_comparisons"]
    assert comparisons is None  # the narrower scan cannot prove any old scope is resolved
    assert _assessment(result, "MODEL-MODULES-ACYCLIC")["status"] == "FAIL"
    assert any(
        record.subjects == ("shop.model.delta", "shop.model.gamma")
        and record.rule_ids == ("MODEL-MODULES-ACYCLIC",)
        for record in observation.records("violations") or ()
    )


def test_narrow_rule_scope_does_not_resolve_unchanged_cycle_or_hide_new_debt(
    tmp_path: Path, capsys
) -> None:
    root, baseline = _cycle_baseline_fixture(tmp_path, capsys)
    contract_path = root / "architecture-contract.json"
    contract = json.loads(contract_path.read_bytes())
    rule = next(item for item in contract["rules"] if item["id"] == "MODEL-MODULES-ACYCLIC")
    rule["components"] = ["model"]
    contract_path.write_text(json.dumps(contract, indent=2) + "\n")
    (root / "shop/model/gamma.py").write_text("from shop.model import delta\nVALUE = delta.VALUE\n")
    (root / "shop/model/delta.py").write_text("from shop.model import gamma\nVALUE = gamma.VALUE\n")

    result, _ = _cli_report(
        root,
        tmp_path / "narrow-rule",
        capsys,
        "--baseline",
        baseline.name,
    )

    comparisons = result["baseline_comparisons"]
    assert isinstance(comparisons, list)
    assert not any(
        "shop.store." in " ".join(item["subjects"]) and item["resolved_count"] > 0
        for item in comparisons
    )
    assert any(
        item["status"] == "new" and item["subjects"] == ["shop.model.delta", "shop.model.gamma"]
        for item in comparisons
    )
    assert result["declared_rules"] == "FAIL"


def test_narrow_root_forbidden_construct_rule_does_not_resolve_unchanged_module(
    tmp_path: Path, capsys
) -> None:
    root = _repo(tmp_path, "narrow-root-construct", {"shop/model/probe.py": PROBE})
    baseline = _baseline_file(root, observed_violations(_observe(root)))
    contract_path = root / "architecture-contract.json"
    contract = json.loads(contract_path.read_bytes())
    rule = next(item for item in contract["rules"] if item["id"] == GETATTR_RULE)
    rule["source"] = "shop.app"
    contract_path.write_text(json.dumps(contract) + "\n")

    result, observation = _cli_report(
        root, tmp_path / "narrow-root-report", capsys, "--baseline", baseline.name
    )

    assert "getattr" in (root / "shop/model/probe.py").read_text()
    assert any(
        item.data.get("qualified_name") == "shop.model.probe"
        for item in observation.records("modules") or ()
    )
    assert not any(
        item["rules"] == [GETATTR_RULE]
        and item["subjects"] == ["shop.model.probe.read"]
        and item["resolved_count"] > 0
        for item in result["baseline_comparisons"]
    )


def test_narrow_nested_construct_rule_does_not_resolve_unchanged_module(
    tmp_path: Path, capsys
) -> None:
    root = _repo(tmp_path, "narrow-nested-construct", {"shop/store/probe.py": PROBE})
    nested_path = root / "shop/store/architecture-contract.json"
    nested = json.loads(nested_path.read_bytes())
    root_rule = next(
        item
        for item in json.loads((root / "architecture-contract.json").read_bytes())["rules"]
        if item["id"] == GETATTR_RULE
    )
    nested_rule = dict(root_rule, id="STORE-NO-DYNAMIC", source="shop.store")
    nested["rules"].append(nested_rule)
    nested_path.write_text(json.dumps(nested) + "\n")
    baseline = _baseline_file(root, observed_violations(_observe(root)))
    nested_rule["source"] = "shop.store.codec"
    nested_path.write_text(json.dumps(nested) + "\n")

    result, observation = _cli_report(
        root, tmp_path / "narrow-nested-report", capsys, "--baseline", baseline.name
    )

    rule_id = "store:STORE-NO-DYNAMIC"
    assert "getattr" in (root / "shop/store/probe.py").read_text()
    assert any(
        item.data.get("qualified_name") == "shop.store.probe"
        for item in observation.records("modules") or ()
    )
    assert not any(
        item["rules"] == [rule_id]
        and item["subjects"] == ["shop.store.probe.read"]
        and item["resolved_count"] > 0
        for item in result["baseline_comparisons"]
    )


def test_complete_partial_scc_scan_does_not_resolve_or_contract_omitted_member(
    tmp_path: Path, capsys
) -> None:
    files = {
        "shop/model/alpha.py": "from shop.model.beta import VALUE\nVALUE = 1\n",
        "shop/model/beta.py": (
            "from shop.model.alpha import VALUE\nfrom shop.cli.gamma import VALUE\nVALUE = 1\n"
        ),
        "shop/cli/gamma.py": "from shop.model.alpha import VALUE\nVALUE = 1\n",
    }
    root = _repo(tmp_path, "partial-cycle-scan", files)
    cycle_rule = module_cycle_rule(components=["model", "cli"])
    _minimal_contract(root, [cycle_rule], {"model", "cli"})
    _, baseline_observation = _cli_report(root, tmp_path / "full-cycle", capsys)
    (known,) = [
        item
        for item in observed_violations(baseline_observation)
        if "MODEL-MODULES-ACYCLIC" in item.fingerprint.rules
    ]
    assert known.fingerprint.subjects == (
        "shop.cli.gamma",
        "shop.model.alpha",
        "shop.model.beta",
    )
    baseline = _baseline_file(root, (known,))
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["shop/model"]\nnamespace = "shop"\n'
        'contract = "architecture-contract.json"\n'
    )

    result, observation = _cli_report(
        root,
        tmp_path / "partial-cycle-report",
        capsys,
        "--baseline",
        baseline.name,
    )

    assert result["observation_complete"] == "PASS"
    assert _assessment(result, "MODEL-MODULES-ACYCLIC")["status"] == "FAIL"
    assert any(
        record.subjects == ("shop.model.alpha", "shop.model.beta")
        for record in observation.records("violations") or ()
    )
    assert not any(
        item["rules"] == ["MODEL-MODULES-ACYCLIC"]
        and item["subjects"]
        in (
            ["shop.cli.gamma", "shop.model.alpha", "shop.model.beta"],
            ["shop.model.alpha", "shop.model.beta"],
        )
        and (item["resolved_count"] > 0 or item["status"] == "contracted")
        for item in result["baseline_comparisons"]
    )


def test_package_receipt_does_not_resolve_omitted_descendant_module(tmp_path: Path, capsys) -> None:
    root = _repo(
        tmp_path,
        "package-receipt",
        {
            "shop/model/package/__init__.py": "def launch() -> int:\n    return 1\n",
            "shop/model/package/tasks.py": PROBE,
        },
    )
    baseline = _baseline_file(root, observed_violations(_observe(root)))
    (root / "shop/model/package/tasks.py").unlink()

    result, observation = _cli_report(
        root, tmp_path / "package-receipt-report", capsys, "--baseline", baseline.name
    )

    modules = observation.records("modules") or ()
    assert any(item.data.get("qualified_name") == "shop.model.package" for item in modules)
    assert not any(
        item.data.get("qualified_name") == "shop.model.package.tasks" for item in modules
    )
    assert any(
        item.data.get("qualified_name") == "shop.model.package.launch"
        for item in observation.records("symbols") or ()
    )
    # Current package scope is proved clean; that is not proof the old descendant is gone.
    assert _assessment(result, GETATTR_RULE)["status"] == "PASS"
    assert result["baseline_comparisons"] == [
        {
            "current_count": 0,
            "known_count": 1,
            "new_count": 0,
            "resolved_count": 0,
            "rules": [GETATTR_RULE],
            "shared_count": 0,
            "status": "unknown",
            "subjects": ["shop.model.package.tasks.read"],
        }
    ]


def test_executable_package_init_does_not_prove_omitted_namespace_cycle_absent(
    tmp_path: Path, capsys
) -> None:
    files = {
        "shop/model/alpha.py": "from shop.cli.beta import VALUE\nVALUE = 1\n",
        "shop/cli/beta.py": "from shop.model.alpha import VALUE\nVALUE = 1\n",
        "shop/store/__init__.py": "VALUE = 1\n",
    }
    root = _repo(tmp_path, "package-init-narrow-scan", files)
    _minimal_contract(
        root,
        [module_cycle_rule(components=["model", "cli", "store"])],
        {"model", "cli", "store"},
    )
    _, full_observation = _cli_report(root, tmp_path / "package-init-full", capsys)
    (known,) = observed_violations(full_observation)
    assert known.fingerprint.subjects == ("shop.cli.beta", "shop.model.alpha")
    baseline = _baseline_file(root, (known,))
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["shop/store"]\nnamespace = "shop"\n'
        'contract = "architecture-contract.json"\n'
    )

    result, observation = _cli_report(
        root,
        tmp_path / "package-init-narrow",
        capsys,
        "--baseline",
        str(baseline),
    )

    assert any(
        record.data.get("qualified_name") == "shop.store"
        for record in observation.records("modules") or ()
    )
    # The rule selects model and cli too; the store initializer cannot prove those scopes.
    cycle_assessment = _assessment(result, "MODEL-MODULES-ACYCLIC")
    assert cycle_assessment["status"] == "UNKNOWN"
    assert cycle_assessment["evaluation_proven"] is False
    assert result["exit_code"] == 0 and result["declared_rules"] == "PASS"
    assert [item["id"] for item in result["rule_assessments"] if item["status"] == "UNKNOWN"] == [
        "MODEL-MODULES-ACYCLIC"
    ]
    assert result["baseline_comparisons"] == [
        {
            "current_count": 0,
            "known_count": 1,
            "new_count": 0,
            "resolved_count": 0,
            "rules": ["MODEL-MODULES-ACYCLIC"],
            "shared_count": 0,
            "status": "unknown",
            "subjects": ["shop.cli.beta", "shop.model.alpha"],
        }
    ]


def test_html_banner_discloses_unknown_rule_when_aggregate_remains_pass(
    tmp_path: Path, capsys
) -> None:
    root = _repo(tmp_path, "unknown-cycle-summary", {})
    _minimal_contract(root, [module_cycle_rule(components=["model"])], {"model"})
    baseline = _baseline_file(root, observed_violations(_observe(root)))
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["shop/model"]\nnamespace = "shop"\n'
        'contract = "architecture-contract.json"\n'
    )

    result, observation = _cli_report(
        root,
        tmp_path / "unknown-cycle-report",
        capsys,
        "--baseline",
        str(baseline),
    )

    assert result["exit_code"] == 0
    assert result["declared_rules"] == "PASS"
    assert (tmp_path / "unknown-cycle-report" / "architecture.json").read_bytes() == (
        canonical_report_bytes(observation)
    )
    assert [item["id"] for item in result["rule_assessments"] if item["status"] == "UNKNOWN"] == [
        "MODEL-MODULES-ACYCLIC"
    ]
    assert not result["open_decisions"]
    page = (tmp_path / "unknown-cycle-report" / "architecture.report.html").read_text()
    assert "The scan completed. Overall verdict: PASS. Rules still UNKNOWN: 1." in page
    banner = page.split('<section class="decision-banner"', 1)[1].split("</section>", 1)[0]
    assert 'data-decision="unknown"' in banner
    assert 'aria-label="Decision: NOT CHECKED"' in banner


def test_replay_reports_mixed_boundary_failure_and_unknown_without_double_counting(
    tmp_path: Path, capsys
) -> None:
    variant_id = "class-a-boundary-types-mixed-evidence"
    _variant(variant_id)
    output = tmp_path / "mixed-evidence.json"

    replay_exit = demo_main(["--replay", variant_id, "--output", str(output)])
    validation, result = (json.loads(line) for line in capsys.readouterr().out.splitlines())

    assert validation["command"] == "validate"
    assert result["command"] == "report" and result["exit_code"] == 0
    assert replay_exit == max(validation["exit_code"], result["exit_code"])
    assessment = _assessment(result, "APP-TYPES-NOT-DICT")
    assert (assessment["status"], assessment["count"], assessment["undecided"]) == (
        "FAIL",
        1,
        1,
    )
    assert result["measurements"]["scalars"]["violations"] == 1

    observation = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    assert (
        len(
            [
                record
                for record in observation.records("violations") or ()
                if "APP-TYPES-NOT-DICT" in record.rule_ids
            ]
        )
        == 1
    )
    assert any(
        record.data.get("annotation") == "FutureOrder"
        for record in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in record.rule_ids
    )

    page = output.with_name("mixed-evidence.report.html").read_text()
    parser = _ReportFilterRows()
    parser.feed(page)
    rule_row = next(
        row for row in parser.rows if row.get("_text", "").lstrip().startswith("APP-TYPES-NOT-DICT")
    )
    detail_rows = [
        row
        for row in parser.rows
        if row.get("_text", "").lstrip().startswith("VIO-")
        and "APP-TYPES-NOT-DICT" in row.get("_text", "")
    ]
    assert rule_row["data-status"] == "FAIL" and rule_row.get("data-undecided") == "1"
    assert len(detail_rows) == 1 and detail_rows[0]["data-status"] == "FAIL"


def test_replay_keeps_partial_module_cycle_scope_unknown_and_baseline_unresolved(
    tmp_path: Path, capsys
) -> None:
    variant_id = "report-partial-module-cycle-scan"
    variant = _variant(variant_id)
    alpha = variant.files["shop/model/alpha.py"]
    beta = variant.files["shop/model/beta.py"]
    assert variant.baseline is not None
    assert isinstance(alpha, str) and "from shop.model import beta" in alpha
    assert isinstance(beta, str) and "from shop.model import alpha" in beta
    output = tmp_path / "partial-cycle.json"

    replay_exit = demo_main(["--replay", variant_id, "--output", str(output)])
    validation, result = (json.loads(line) for line in capsys.readouterr().out.splitlines())

    assert validation["command"] == "validate"
    assert result["command"] == "report"
    assert replay_exit == max(validation["exit_code"], result["exit_code"])
    assert result["scan_roots"] == ["shop/store"]
    assert result["open_decisions"] == []
    cycle = _assessment(result, "MODEL-MODULES-ACYCLIC")
    assert cycle["status"] == "UNKNOWN" and cycle["evaluation_proven"] is False
    comparisons = result["baseline_comparisons"]
    assert isinstance(comparisons, list)
    old_cycle = next(
        item
        for item in comparisons
        if item["rules"] == ["MODEL-MODULES-ACYCLIC"]
        and item["subjects"] == ["shop.model.alpha", "shop.model.beta"]
    )
    assert old_cycle["status"] == "unknown" and old_cycle["resolved_count"] == 0
    assert output.is_file() and output.stat().st_size > 0
    observation = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    assert not any(
        record.data.get("qualified_name") in {"shop.model.alpha", "shop.model.beta"}
        for record in observation.records("modules") or ()
    )
    assert output.with_name("partial-cycle.report.html").is_file()


def test_deleted_function_can_resolve_while_its_module_remains_observed(
    tmp_path: Path, capsys
) -> None:
    root = _repo(tmp_path, "deleted-function", {"shop/model/probe.py": PROBE})
    baseline = _baseline_file(root, observed_violations(_observe(root)))
    (root / "shop/model/probe.py").write_text("def healthy() -> int:\n    return 1\n")

    result, observation = _cli_report(
        root, tmp_path / "deleted-function-report", capsys, "--baseline", baseline.name
    )

    assert any(
        item.data.get("qualified_name") == "shop.model.probe"
        for item in observation.records("modules") or ()
    )
    assert not any(
        GETATTR_RULE in item.rule_ids for item in observation.records("violations") or ()
    )
    assert any(
        item["rules"] == [GETATTR_RULE] and item["resolved_count"] == 1
        for item in result["baseline_comparisons"]
    )


def test_real_html_keeps_mixed_fail_and_unknown_evidence_available_without_javascript(
    tmp_path: Path, capsys
) -> None:
    tour = _variant("tour")
    files = dict(tour.files)
    orders_path = "shop/app/orders.py"
    files[orders_path] = files[orders_path].replace(
        "store_dir: object,\n    order_id",
        "store_dir: object,\n    extra_path: FutureOrder,\n    order_id",
    )
    root = _prepare_repo(tmp_path, files, tour.fixture)
    result, _ = _cli_report(root, tmp_path / "html-report", capsys)
    page = (tmp_path / "html-report" / "architecture.report.html").read_text()
    parser = _ReportFilterRows()
    parser.feed(page)

    mixed = next(
        row for row in parser.rows if row.get("_text", "").lstrip().startswith("APP-TYPES-NOT-DICT")
    )
    clean = next(
        row for row in parser.rows if row.get("_text", "").lstrip().startswith("DEP-APP-NO-CLI")
    )
    assert parser.filters_hidden  # without JS, controls stay hidden but evidence rows are readable
    assert result["declared_rules"] == "FAIL"
    banner = page.split('<section class="decision-banner"', 1)[1].split("</section>", 1)[0]
    assert 'data-decision="fail"' in banner
    assert 'aria-label="Decision: FAIL"' in banner
    assert mixed["data-status"] == "FAIL"
    assert mixed.get("data-undecided") == "1"
    assert clean["data-status"] == "PASS" and clean.get("data-undecided") == "0"
    assert 'value="FAIL+UNKNOWN"' in page and 'value="UNKNOWN"' in page
    assert all("hidden" not in row for row in parser.rows)


def test_real_html_marks_failure_explicitly_and_permission_as_neutral(
    tmp_path: Path, capsys
) -> None:
    tour = _variant("tour")
    root = _prepare_repo(tmp_path, dict(tour.files), tour.fixture)
    _cli_report(root, tmp_path, capsys)
    page = (tmp_path / "architecture.report.html").read_text()
    parser = _ReportFilterRows()
    parser.feed(page)

    failure = next(
        row for row in parser.rows if row.get("_text", "").lstrip().startswith("APP-TYPES-NOT-DICT")
    )
    permission = next(row for row in parser.rows if row.get("data-kind") == "allowed_dependency")
    css = (Path(__file__).parents[1] / "src/archkeel/render/assets/archkeel-report.css").read_text()

    assert "FAIL" in failure["_text"] and failure.get("badge-status") == "fail"
    assert "DECLARATION" in permission["_text"] and permission.get("badge-status") == "info"
    assert '[data-status="fail"] {\n  color: var(--ck-fail);' in css
    assert '[data-status="info"] {\n  color: var(--ck-muted);' in css


def test_real_html_keeps_each_mobile_filter_label_with_its_control(tmp_path: Path, capsys) -> None:
    tour = _variant("tour")
    root = _prepare_repo(tmp_path, dict(tour.files), tour.fixture)
    _cli_report(root, tmp_path, capsys)
    parser = _ReportFilterRows()
    parser.feed((tmp_path / "architecture.report.html").read_text())

    assert len(parser.filter_fields) == 4
    assert all(control_owned_by_label for _label, control_owned_by_label in parser.filter_fields)


def test_real_report_scopes_root_intermediate_and_leaf_assessments_to_receipts(
    tmp_path: Path, capsys
) -> None:
    _write_three_levels(
        tmp_path,
        deep_rules=[_forbidden_edge()],
        source_import="from sample.layer.target.api import VALUE\n",
    )
    deep_contract_path = tmp_path / "contracts/two.json"
    deep_contract = json.loads(deep_contract_path.read_text())
    source = next(item for item in deep_contract["components"] if item["label"] == "source")
    source["requires"] = [{"component": "target", "rationale": "The probe crosses here."}]
    deep_contract_path.write_text(json.dumps(deep_contract))
    (tmp_path / "archkeel.toml").write_text(
        '[scan]\nroots = ["sample"]\nnamespace = "sample"\ncontract = "contract.json"\n'
    )
    (tmp_path / "docs/architecture/sample.md").write_text(
        f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"
        f"{TARGET_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"
    )
    _commit_tree(tmp_path)

    result, observation = _cli_report(tmp_path, tmp_path, capsys)
    assessments = {item["id"]: item for item in result["rule_assessments"]}
    receipts = {
        rule_id: record
        for record in observation.records("scope_observations") or ()
        if record.kind == "rule_evaluation"
        for rule_id in record.rule_ids
    }

    assert assessments["REQUIRES-COMPLETE"]["status"] == "UNKNOWN"
    assert assessments["app:REQUIRES-COMPLETE"]["status"] == "UNKNOWN"
    assert "REQUIRES-COMPLETE" not in receipts
    assert "app:REQUIRES-COMPLETE" not in receipts

    assert assessments["app:app:REQUIRES-COMPLETE"]["status"] == "PASS"
    assert assessments["app:app:REQUIRES-COMPLETE"]["evaluation_proven"] is True
    assert receipts["app:app:REQUIRES-COMPLETE"].data.get("scope") == "app"

    assert assessments["app:app:DEEP-NO-EDGE"]["status"] == "FAIL"
    assert assessments["app:app:DEEP-NO-EDGE"]["evaluation_proven"] is True
    assert receipts["app:app:DEEP-NO-EDGE"].data.get("scope") == "app"
