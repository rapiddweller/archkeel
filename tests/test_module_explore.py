# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Explore reads native Core ownership, sites and findings without deciding permissions."""

import json
from dataclasses import asdict, replace

import pytest
from test_target_graph import _nested_repository, _repository

from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.facts import EvidenceClass, Record, RecordData
from archkeel.ir.module_explore import module_exploration
from archkeel.ir.report_graph import architecture_report


def _sample(
    tmp_path,
    *,
    ambiguous=False,
    unowned_importer=False,
    own_importer=False,
    permitted=False,
    extra_files=None,
    core_exact=(),
    peer_exact=(),
    uml=False,
    other_component=False,
    other_requires_core=False,
    extra_rules=(),
    complete_requires=True,
    rule_include_type_checking=True,
    core_public=None,
):
    root, config = _repository(tmp_path)
    contract = json.loads((root / config.contract).read_bytes())
    contract.pop("declarations")
    contract["components"][0]["requires"] = []
    contract["components"][0]["exact_modules"] = list(core_exact)
    if core_public is not None:
        contract["components"][0]["public"] = list(core_public)
    peer = dict(contract["components"][0])
    peer.update(id="peer", label="peer", packages=["sample.peer"], namespace="sample.peer")
    peer["requires"] = [{"component": "core", "rationale": "Read the core interface."}]
    if not permitted:
        peer["requires"] = []
    peer["exact_modules"] = list(peer_exact)
    contract["components"].append(peer)
    if other_component:
        other = dict(contract["components"][0])
        other.update(
            id="other",
            label="other",
            packages=["sample.other"],
            namespace="sample.other",
            exact_modules=[],
            requires=(
                [{"component": "core", "rationale": "Read the core interface."}]
                if other_requires_core
                else []
            ),
        )
        contract["components"].append(other)
    if ambiguous:
        contract["components"][0].pop("namespace")
        contract["components"].append(
            dict(contract["components"][0], id="overlap", label="overlap")
        )
    rules = []
    if complete_requires:
        rule = {
            "id": "dependencies",
            "kind": "complete_requires",
            "rationale": "Each crossing must be explicitly granted.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
        if not rule_include_type_checking:
            rule["include_type_checking"] = False
        rules.append(rule)
    contract["rules"] = rules + list(extra_rules)
    if uml:
        contract["declarations"] = {
            "uml": {
                "schema_version": "1.0.0",
                "entities": [
                    {
                        "id": name + "-module",
                        "kind": "module",
                        "qualified_name": "sample." + name,
                        "parent_id": name,
                        "language": "python",
                        "presence": "planned",
                        "responsibilities": ["Own the module."],
                        "provenance": ["docs/target.md"],
                    }
                    for name in ("core", "peer")
                ],
                "scopes": [
                    {
                        "scope_id": "peer-module",
                        "mode": "closed",
                        "relationship_kinds": ["imports"],
                        "rationale": "Declare each module import.",
                        "provenance": ["docs/target.md"],
                    }
                ],
            }
        }
    (root / config.contract).write_text(json.dumps(contract))
    (root / "sample/peer.py").write_text("import sample.core\nimport sample.core\n")
    (root / "sample/unowned.py").write_text("import sample.core\n" if unowned_importer else "")
    if own_importer:
        (root / "sample/core.py").write_text("import sample.core\n")
    for path, text in (extra_files or {}).items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    _, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    return parse_observation(decode_canonical_model(json.loads(encoded)))


def _root(model):
    return next(level for level in module_exploration(model) if level.parent_id is None)


def test_sparse_cells_keep_orientation_repeated_sites_and_core_failure(tmp_path):
    model = _sample(tmp_path)
    level = _root(model)
    names = {module.id: module.name for module in level.modules}
    assert len(level.cells) == 1
    cell = level.cells[0]
    assert (names[cell.source_id], names[cell.target_id]) == ("sample.peer", "sample.core")
    assert cell.import_sites == 2
    assert len(cell.relationship_ids) == 2
    assert cell.status == "FAIL"
    assert cell.finding_ids and cell.reasons and cell.evidence_ids
    report = architecture_report(model)
    assert set(cell.relationship_ids) <= {item.id for item in report.observed.relationships}
    assert set(cell.evidence_ids) <= {item.id for item in model.evidence}
    assert cell.permission == "UNKNOWN"
    assert "module import" in cell.permission_reason
    assert set(level.component_ids) == {"core", "peer"}


def test_no_failure_does_not_authenticate_module_permission(tmp_path):
    model = _sample(tmp_path, permitted=True)
    cell = _root(model).cells[0]
    assert cell.status == cell.permission == "UNKNOWN"
    assert not cell.finding_ids


@pytest.mark.parametrize(
    ("include_type_checking", "expected"), [(True, "PASS"), (False, "UNKNOWN")]
)
def test_mixed_import_sites_require_evaluation_for_each_site(
    tmp_path, include_type_checking, expected
):
    model = _sample(
        tmp_path,
        permitted=True,
        core_exact=("sample.unowned",),
        rule_include_type_checking=include_type_checking,
        extra_files={
            "sample/peer.py": (
                "import sample.core\n"
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n    import sample.core\n"
            )
        },
    )
    (cell,) = _root(model).cells
    imports = {item.id: item for item in model.records("imports") or ()}
    typed_sites = [
        identity
        for identity in cell.relationship_ids
        if imports[identity].data.get("under_type_checking") is True
    ]
    runtime_sites = [
        identity
        for identity in cell.relationship_ids
        if imports[identity].data.get("under_type_checking") is False
    ]
    assert cell.import_sites == len(cell.relationship_ids) == 2
    assert len(runtime_sites) == len(typed_sites) == 1
    assert cell.status == expected, cell.reasons


def test_runtime_finding_still_fails_cell_with_skipped_type_only_site(tmp_path):
    model = _sample(
        tmp_path,
        core_exact=("sample.unowned",),
        rule_include_type_checking=False,
        extra_files={
            "sample/peer.py": (
                "import sample.core\n"
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n    import sample.core\n"
            )
        },
    )
    (cell,) = _root(model).cells
    assert cell.import_sites == 2
    assert cell.status == "FAIL"
    assert cell.finding_ids


def test_missing_observed_site_cannot_borrow_weighted_pair_receipt(tmp_path, monkeypatch):
    import archkeel.ir.module_explore as module_explore

    model = _sample(tmp_path, permitted=True, core_exact=("sample.unowned",))
    report = architecture_report(model)
    assert report.observed is not None
    observed = replace(
        report.observed,
        relationships=tuple(
            item for item in report.observed.relationships if item.kind != "imports"
        ),
    )
    monkeypatch.setattr(
        module_explore, "architecture_report", lambda _: replace(report, observed=observed)
    )
    (cell,) = _root(model).cells
    assert cell.import_sites == 2
    assert cell.status == "UNKNOWN"


def test_forbidden_allowed_source_cannot_cover_skipped_import_sites(tmp_path):
    model = _sample(
        tmp_path,
        permitted=True,
        complete_requires=False,
        extra_rules=[
            {
                "id": "source-rule",
                "kind": "forbidden_dependency",
                "source": "sample.peer",
                "target": "sample.core",
                "include_type_checking": True,
                "allowed_sources": ["sample.peer"],
                "rationale": "Record the allowed source exception.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        ],
    )
    (cell,) = _root(model).cells
    assert cell.status == "UNKNOWN"


def test_interface_without_target_public_scope_cannot_prove_import_site(tmp_path):
    model = _sample(
        tmp_path,
        permitted=True,
        complete_requires=False,
        extra_rules=[
            {
                "id": "interface",
                "kind": "interface_boundary",
                "include_type_checking": True,
                "rationale": "Imports use the target interface.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        ],
    )
    (cell,) = _root(model).cells
    assert cell.status == "UNKNOWN"


@pytest.mark.parametrize(
    ("kind", "include_type_checking", "expected"),
    [
        ("complete_requires", True, "PASS"),
        ("complete_requires", False, "UNKNOWN"),
        ("forbidden_dependency", True, "PASS"),
        ("forbidden_dependency", False, "UNKNOWN"),
        ("interface_boundary", True, "PASS"),
        ("interface_boundary", False, "UNKNOWN"),
        ("sibling_isolation", True, "FAIL"),
        ("sibling_isolation", False, "UNKNOWN"),
    ],
)
def test_native_rule_evidence_tracks_type_only_site_applicability(
    tmp_path, kind, include_type_checking, expected
):
    rule = {
        "id": "site-rule",
        "kind": kind,
        "include_type_checking": include_type_checking,
        "rationale": "Evaluate the import sites under this rule.",
        "provenance": ["docs/target.md"],
        "decided_by": "architect",
    }
    options = {
        "complete_requires": {},
        "forbidden_dependency": {
            "source": "sample.peer",
            "target": "sample.core",
            "target_symbol": "OTHER",
        },
        "interface_boundary": {},
        "sibling_isolation": {"members": ["sample.peer", "sample.core"]},
    }[kind]
    rule.update(options)
    model = _sample(
        tmp_path,
        permitted=True,
        complete_requires=kind == "complete_requires",
        rule_include_type_checking=include_type_checking,
        extra_rules=[] if kind == "complete_requires" else [rule],
        extra_files={
            "sample/peer.py": (
                "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import sample.core\n"
            )
        },
        core_exact=("sample.unowned",),
        **({"core_public": ["sample.core"]} if kind == "interface_boundary" else {}),
    )
    cell = _root(model).cells[0]
    assert cell.import_sites == 1
    assert cell.status == expected, cell.reasons


def test_nested_interface_receipt_survives_ancestor_membership(tmp_path):
    root, config = _nested_repository(tmp_path)
    outer = json.loads((root / config.contract).read_bytes())
    outer["components"][0].update(packages=["sample"], namespace="sample")
    (root / config.contract).write_text(json.dumps(outer))
    inner = json.loads((root / "inside.json").read_bytes())
    inner.pop("declarations")
    service = inner["components"][0]
    service.pop("inside")
    service["public"] = ["sample.core"]
    inner["components"].append(
        dict(
            service,
            id="PEER",
            label="peer",
            packages=["sample.peer"],
            namespace="sample.peer",
            public=None,
            requires=[],
        )
    )
    inner["rules"] = [
        {
            "id": "interface",
            "kind": "interface_boundary",
            "rationale": "Imports use the target interface.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    ]
    (root / "inside.json").write_text(json.dumps(inner))
    (root / "sample/peer.py").write_text("import sample.core\n")
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    memberships = {item.component_id: set(item.module_ids) for item in report.memberships}
    level = next(item for item in module_exploration(model) if item.parent_id == "ROOT")
    (cell,) = level.cells
    assert sum(cell.target_id in module_ids for module_ids in memberships.values()) > 1
    assert cell.status == "PASS", cell.reasons


def test_sibling_rule_excluding_type_only_site_cannot_prove_it(tmp_path):
    model = _sample(
        tmp_path,
        complete_requires=False,
        extra_rules=[
            {
                "id": "siblings",
                "kind": "sibling_isolation",
                "members": ["sample.peer", "sample.core"],
                "include_type_checking": False,
                "rationale": "Keep these packages isolated.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        ],
        extra_files={
            "sample/peer.py": (
                "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import sample.core\n"
            )
        },
    )
    (cell,) = _root(model).cells
    assert cell.import_sites == 1
    assert cell.status == "UNKNOWN"


def test_complete_applicable_rule_receipt_proves_cell_status_without_permission(tmp_path):
    model = _sample(tmp_path, permitted=True)
    section = next(item for item in model.sections if item.name == "scope_observations")
    evidence_id = model.evidence[0].id
    receipt = Record(
        "RULE-EVALUATION-test",
        EvidenceClass.FACT,
        "rules",
        "rule_evaluation",
        "dependencies evaluator completed",
        ("sample.peer", "sample.core"),
        (evidence_id,),
        ("dependencies",),
        (),
        (),
        RecordData((("scope", "root"),)),
    )
    sections = tuple(
        replace(item, records=(*item.records, receipt)) if item.name == section.name else item
        for item in model.sections
    )
    cell = _root(replace(model, sections=sections)).cells[0]
    assert cell.status == "PASS"
    assert cell.permission == "UNKNOWN"
    assert cell.evidence_ids == _root(model).cells[0].evidence_ids
    assert any("dependencies: complete evaluator receipt" in item for item in cell.reasons)
    assert receipt.id not in cell.assessment_ids


def test_cell_status_uses_local_finding_when_global_rule_fails_elsewhere(tmp_path):
    model = _sample(
        tmp_path,
        permitted=True,
        other_component=True,
        extra_files={
            "sample/other.py": "value = 1\n",
            "sample/peer.py": "import sample.core\nimport sample.other\n",
        },
    )
    section = next(item for item in model.sections if item.name == "scope_observations")
    receipt = Record(
        "RULE-EVALUATION-test",
        EvidenceClass.FACT,
        "rules",
        "rule_evaluation",
        "dependencies evaluator completed",
        ("sample.peer", "sample.core"),
        (),
        ("dependencies",),
        (),
        (),
        RecordData((("scope", "root"),)),
    )
    model = replace(
        model,
        sections=tuple(
            replace(item, records=(*item.records, receipt)) if item.name == section.name else item
            for item in model.sections
        ),
    )
    report = architecture_report(model)
    assert report.observed is not None
    cells = _root(model).cells
    modules = {item.id: item.name for item in _root(model).modules}
    by_target = {modules[item.target_id]: item for item in cells}
    assert by_target["sample.core"].status == "PASS"
    assert by_target["sample.other"].status == "FAIL"
    assert any(
        item.kind == "complete_requires" and item.status == "FAIL" for item in report.findings
    )


def test_one_native_fixture_keeps_pass_fail_and_unknown_cells(tmp_path):
    model = _sample(
        tmp_path,
        permitted=True,
        other_component=True,
        other_requires_core=True,
        extra_rules=[
            {
                "id": "other-core-check",
                "kind": "forbidden_dependency",
                "source": "sample.other",
                "target": "sample.core",
                "include_type_checking": True,
                "allowed_sources": ["sample.other"],
                "rationale": "Record the exception for the undecided pair.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        ],
        extra_files={
            "sample/other.py": "import sample.core\n",
            "sample/peer.py": "import sample.core\nimport sample.other\n",
        },
    )
    receipt = Record(
        "RULE-EVALUATION-test",
        EvidenceClass.FACT,
        "rules",
        "rule_evaluation",
        "dependencies evaluator completed for sample.peer to sample.core",
        ("sample.peer", "sample.core"),
        (),
        ("dependencies",),
        (),
        (),
        RecordData((("scope", "root"),)),
    )
    model = replace(
        model,
        sections=tuple(
            replace(section, records=(*section.records, receipt))
            if section.name == "scope_observations"
            else section
            for section in model.sections
        ),
    )
    level = _root(model)
    names = {item.id: item.name for item in level.modules}
    statuses = {(names[cell.source_id], names[cell.target_id]): cell.status for cell in level.cells}
    assert statuses["sample.peer", "sample.core"] == "PASS"
    assert statuses["sample.peer", "sample.other"] == "FAIL"
    assert statuses["sample.other", "sample.core"] == "UNKNOWN"
    cell = next(
        item
        for item in level.cells
        if names[item.source_id] == "sample.other" and names[item.target_id] == "sample.core"
    )
    assert any(reason.startswith("dependencies:") for reason in cell.reasons)


def test_requires_alone_does_not_prove_module_cell_when_rule_receipt_is_missing(tmp_path):
    model = _sample(tmp_path, permitted=True)
    sections = tuple(
        replace(
            section,
            records=tuple(
                record
                for record in section.records
                if not (record.kind == "rule_evaluation" and record.rule_ids == ("dependencies",))
            ),
        )
        if section.name == "scope_observations"
        else section
        for section in model.sections
    )
    cell = _root(replace(model, sections=sections)).cells[0]
    assert cell.status == "UNKNOWN"
    assert any(reason.startswith("dependencies:") for reason in cell.reasons)


def test_forbidden_rule_receipt_scoped_to_source_proves_import_cell(tmp_path):
    model = _sample(
        tmp_path,
        permitted=True,
        complete_requires=False,
        core_exact=("sample.unowned",),
        extra_rules=[
            {
                "id": "source-rule",
                "kind": "forbidden_dependency",
                "source": "sample.peer",
                "target": "sample.core",
                "include_type_checking": True,
                "target_symbol": "OTHER",
                "rationale": "Record the allowed source exception.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        ],
        extra_files={
            "sample/peer.py": "from sample.core import VALUE\n",
            "sample/core.py": "VALUE = 1\n",
        },
    )
    level = _root(model)
    (cell,) = level.cells
    receipt = next(
        record
        for record in model.records("scope_observations")
        if record.kind == "rule_evaluation" and record.rule_ids == ("source-rule",)
    )
    assert receipt.subjects == ("sample.peer",)
    assert cell.status == "PASS", cell.reasons


@pytest.mark.parametrize("receipt_state", ["missing", "incomplete"])
def test_forbidden_rule_cell_stays_unknown_without_complete_source_receipt(tmp_path, receipt_state):
    model = _sample(
        tmp_path,
        permitted=True,
        complete_requires=False,
        core_exact=("sample.unowned",),
        extra_rules=[
            {
                "id": "source-rule",
                "kind": "forbidden_dependency",
                "source": "sample.peer",
                "target": "sample.core",
                "include_type_checking": True,
                "target_symbol": "OTHER",
                "rationale": "Record the allowed source exception.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        ],
        extra_files={
            "sample/peer.py": "from sample.core import VALUE\n",
            "sample/core.py": "VALUE = 1\n",
        },
    )
    sections = []
    for section in model.sections:
        if section.name != "scope_observations":
            sections.append(section)
            continue
        records = []
        for record in section.records:
            if record.kind != "rule_evaluation" or record.rule_ids != ("source-rule",):
                records.append(record)
            elif receipt_state == "incomplete":
                records.append(
                    replace(
                        record,
                        data=RecordData((*record.data.entries, ("assessment_complete", False))),
                    )
                )
        sections.append(replace(section, records=tuple(records)))
    cell = _root(replace(model, sections=tuple(sections))).cells[0]
    assert cell.status == "UNKNOWN"
    assert any(reason.startswith("source-rule:") for reason in cell.reasons)


def test_sibling_rule_uses_module_selectors_when_import_evaluation_is_incomplete(tmp_path):
    model = _sample(
        tmp_path,
        permitted=True,
        core_exact=("sample.unowned",),
        extra_rules=[
            {
                "id": "siblings",
                "kind": "sibling_isolation",
                "members": ["sample.peer", "sample.core"],
                "rationale": "Keep these packages isolated.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        ],
    )
    sections = []
    for section in model.sections:
        records = []
        for record in section.records:
            if record.evidence_class == EvidenceClass.VIOLATION and "siblings" in record.rule_ids:
                continue
            if record.kind == "rule_evaluation" and record.rule_ids == ("siblings",):
                record = replace(
                    record,
                    data=RecordData((*record.data.entries, ("assessment_complete", False))),
                )
            records.append(record)
        sections.append(replace(section, records=tuple(records)))
    cell = _root(replace(model, sections=tuple(sections))).cells[0]
    assert cell.status == "UNKNOWN", cell.reasons
    assert any(reason.startswith("siblings:") for reason in cell.reasons)


def test_recorded_native_graph_assessment_keeps_fail_reason_and_evidence(tmp_path):
    model = _sample(tmp_path, permitted=True, uml=True)
    report = architecture_report(model)
    cell = _root(model).cells[0]
    matched = [item for item in report.comparison.assessments if item.id in cell.assessment_ids]
    assert matched and any(item.status == "FAIL" for item in matched)
    assert cell.status == "FAIL" and cell.permission == "UNKNOWN"
    assert all(item.reason in cell.reasons for item in matched)
    assert all(set(item.evidence_ids) <= set(cell.evidence_ids) for item in matched)


@pytest.mark.parametrize("ambiguous", [False, True])
def test_unowned_and_ambiguous_modules_are_retained_with_unknown_ownership(tmp_path, ambiguous):
    model = _sample(tmp_path, ambiguous=ambiguous)
    level = _root(model)
    modules = {item.name: item for item in level.modules}
    unowned = modules["sample.unowned"]
    assert unowned.component_id is None and unowned.ownership_status == "UNKNOWN"
    assert unowned.candidate_ids == ()
    no_owner = {
        identity
        for hint in level.hint_candidates
        if hint.kind == "no_owner"
        for identity in hint.module_ids
    }
    assert unowned.id in no_owner
    if ambiguous:
        core = modules["sample.core"]
        assert core.component_id is None and core.ownership_status == "UNKNOWN"
        assert core.candidate_ids == ("core", "overlap")
        assert core.id not in no_owner
        assert not any(hint.kind == "used_elsewhere" for hint in level.hint_candidates)


@pytest.mark.parametrize("change", ["partial", "absent_imports", "absent_edges"])
def test_incomplete_import_signals_keep_counts_unknown_and_suppress_absence_hints(tmp_path, change):
    model = _sample(tmp_path)
    if change == "partial":
        model = replace(model, coverage=replace(model.coverage, status="FAIL"))
    else:
        missing = "imports" if change == "absent_imports" else "dependency_edges"
        model = replace(
            model, sections=tuple(section for section in model.sections if section.name != missing)
        )
    level = _root(model)
    assert level.import_status == "UNKNOWN" and level.import_reason
    assert not any(hint.kind == "used_elsewhere" for hint in level.hint_candidates)
    assert all(module.fan_in is None and module.fan_out is None for module in level.modules)


@pytest.mark.parametrize("change", ["unowned_importer", "own_importer"])
def test_used_elsewhere_does_not_ignore_an_unowned_or_own_component_importer(tmp_path, change):
    level = _root(_sample(tmp_path, **{change: True}))
    assert level.import_status == "PASS"
    assert not any(hint.kind == "used_elsewhere" for hint in level.hint_candidates)


def test_resolved_self_import_keeps_unrelated_coverage_and_original_sites(tmp_path):
    model = _sample(tmp_path, extra_files={"sample/unowned.py": "import sample.unowned\n"})
    level = _root(model)
    modules = {item.name: item for item in level.modules}
    diagonal = next(cell for cell in level.cells if cell.source_id == cell.target_id)
    assert level.import_status == "PASS"
    assert diagonal.import_sites == len(diagonal.relationship_ids) == 1
    assert diagonal.evidence_ids
    assert modules["sample.unowned"].fan_in == modules["sample.unowned"].fan_out == 0
    assert modules["sample.core"].fan_in == 1
    assert any(hint.kind == "used_elsewhere" for hint in level.hint_candidates)


def test_native_self_import_preserves_its_core_graph_failure(tmp_path):
    model = _sample(
        tmp_path,
        permitted=True,
        uml=True,
        extra_files={
            "sample/peer.py": "import sample.core\nimport sample.peer\n",
        },
    )
    level = _root(model)
    diagonal = next(cell for cell in level.cells if cell.source_id == cell.target_id)
    assert level.import_status == "PASS"
    assert diagonal.import_sites == 1 and diagonal.status == "FAIL"
    assert diagonal.finding_ids and diagonal.assessment_ids and diagonal.reasons
    assert diagonal.evidence_ids and diagonal.permission == "UNKNOWN"


def test_used_elsewhere_candidate_is_a_grouped_question_with_real_sites(tmp_path):
    level = _root(
        _sample(
            tmp_path,
            core_exact=("sample.extra",),
            extra_files={
                "sample/extra.py": "value = 1\n",
                "sample/peer.py": "import sample.core\n" * 2 + "import sample.extra\n" * 3,
            },
        )
    )
    hint = next(hint for hint in level.hint_candidates if hint.kind == "used_elsewhere")
    assert hint.component_ids == ("core", "peer")
    assert len(hint.module_ids) == 2
    assert hint.count == 5 and len(hint.relationship_ids) == 5
    assert hint.evidence_ids and hint.question.endswith("?")
    assert hint.question == (
        "Do sample.core, sample.extra belong to peer, or are they core's intended "
        "interface for peer?"
    )
    assert hint.provisional is True


def test_proposed_hub_threshold_has_native_counts_and_stable_top_three(tmp_path):
    heavy = tuple(f"sample.h{index}" for index in range(4))
    users = tuple(f"sample.user{index}" for index in range(10))
    files = {
        name.replace(".", "/") + ".py": "\n".join(
            f"def f{index}(): return {index}" for index in range(40)
        )
        for name in heavy
    }
    files.update(
        {
            name.replace(".", "/") + ".py": "\n".join(f"import {module}" for module in heavy)
            for name in users
        }
    )
    level = _root(_sample(tmp_path, extra_files=files, core_exact=heavy, peer_exact=users))
    modules = {item.id: item for item in level.modules}
    hints = [item for item in level.hint_candidates if item.kind == "hub"]
    assert [modules[hint.module_ids[0]].name for hint in hints] == list(heavy[:3])
    assert [hint.count for hint in hints] == [10] * 3
    assert all(hint.question.endswith("?") and hint.provisional for hint in hints)
    assert not any(hint.kind == "heavy" for hint in level.hint_candidates)
    assert (
        modules[
            next(hint.module_ids[0] for hint in level.hint_candidates if hint.kind == "hub")
        ].fan_in
        == 10
    )


def test_native_ambiguous_import_target_retains_uncertain_sites_and_suppresses_absence(tmp_path):
    model = _sample(tmp_path, extra_files={"sample/__init__.py": "class core:\n    pass\n"})
    level = _root(model)
    assert level.import_status == "UNKNOWN" and level.uncertain_relationship_ids
    assert not any(hint.kind in {"used_elsewhere", "hub"} for hint in level.hint_candidates)


def test_missing_target_keeps_observed_modules_as_unknown(tmp_path):
    model = _sample(tmp_path)
    model = replace(
        model,
        sections=tuple(
            replace(
                section,
                records=tuple(
                    item
                    for item in section.records
                    if item.kind not in {"architecture_target", "uml_target"}
                ),
            )
            for section in model.sections
        ),
    )
    level = _root(model)
    assert len(level.modules) == len(model.records("modules"))
    assert all(
        item.component_id is None and item.ownership_status == "UNKNOWN" for item in level.modules
    )
    assert level.import_status == "UNKNOWN" and not level.hint_candidates


def test_forged_owner_reference_keeps_existing_core_rejection(tmp_path):
    model = _sample(tmp_path)
    model = replace(
        model,
        sections=tuple(
            replace(
                section,
                records=tuple(
                    replace(
                        item,
                        data=RecordData(
                            tuple(
                                (key, ("missing-owner",) if key == "owner_ids" else value)
                                for key, value in item.data.entries
                            )
                        ),
                    )
                    if item.kind == "architecture_target"
                    else item
                    for item in section.records
                ),
            )
            for section in model.sections
        ),
    )
    with pytest.raises(ValueError, match="owner"):
        module_exploration(model)


def test_unavailable_source_evidence_does_not_create_a_working_matrix(tmp_path):
    model = replace(_sample(tmp_path), evidence=())
    level = _root(model)
    assert level.import_status == "UNKNOWN" and level.import_reason
    assert not level.cells and not level.hint_candidates


def test_level_modules_come_from_authenticated_parent_membership(tmp_path):
    root, config = _nested_repository(tmp_path)
    _, encoded = run_report(root, config=config, analyzer=observe)
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    report = architecture_report(model)
    memberships = {item.component_id: set(item.module_ids) for item in report.memberships}
    levels = module_exploration(model)
    for level in levels:
        if level.parent_id is not None:
            assert {item.id for item in level.modules} == memberships[level.parent_id]
            assert all(
                component.parent_id == level.parent_id
                for component in report.target.component_intents
                if component.component_id in level.component_ids
            )
    assert {level.parent_id for level in levels} == {None, "ROOT", "core:core"}


@pytest.mark.parametrize("unowned, status", [(False, "PASS"), (True, "UNKNOWN")])
def test_inner_import_rule_matches_scope_label_to_native_parent_id(tmp_path, unowned, status):
    root, config = _nested_repository(tmp_path)
    outer = json.loads((root / config.contract).read_bytes())
    outer["components"][0].update(packages=["sample"], namespace="sample")
    (root / config.contract).write_text(json.dumps(outer))
    inner = json.loads((root / "inside.json").read_bytes())
    inner.pop("declarations")
    service = inner["components"][0]
    service.pop("inside")
    service["requires"] = [{"component": "peer", "rationale": "Use the peer boundary."}]
    inner["components"].append(
        dict(
            service,
            id="PEER",
            label="peer",
            packages=["sample.peer"],
            namespace="sample.peer",
            requires=[],
        )
    )
    inner["rules"] = [
        {
            "id": "dependencies",
            "kind": "complete_requires",
            "rationale": "Evaluate each inner crossing.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    ]
    (root / "inside.json").write_text(json.dumps(inner))
    (root / "sample/core.py").write_text("import sample.peer\n")
    (root / "sample/peer.py").write_text("VALUE = 1\n")
    if unowned:
        (root / "sample/extra.py").write_text("VALUE = 1\n")
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    level = next(level for level in module_exploration(model) if level.parent_id == "ROOT")
    assert len(level.cells) == 1
    assert level.cells[0].status == status
    assert any("core:dependencies:" in reason for reason in level.cells[0].reasons)


def test_output_is_byte_identical_when_record_order_changes(tmp_path):
    model = _sample(tmp_path)
    shuffled = replace(
        model,
        sections=tuple(
            replace(section, records=tuple(reversed(section.records))) for section in model.sections
        ),
    )

    def encode(levels):
        return json.dumps([asdict(level) for level in levels], sort_keys=True)

    assert encode(module_exploration(model)) == encode(module_exploration(shuffled))


def test_unknown_symbol_count_stays_unknown(tmp_path):
    model = _sample(tmp_path)
    model = replace(
        model,
        sections=tuple(
            replace(
                section,
                records=tuple(
                    replace(
                        record,
                        data=RecordData(
                            tuple(
                                (key, None if key == "symbol_count" else value)
                                for key, value in record.data.entries
                            )
                        ),
                    )
                    for record in section.records
                ),
            )
            if section.name == "modules"
            else section
            for section in model.sections
        ),
    )
    level = _root(model)
    assert all(module.symbols is None for module in level.modules)
    assert not any(hint.kind == "heavy" for hint in level.hint_candidates)


def test_a_missing_module_weight_does_not_turn_imports_into_zero_usage(tmp_path):
    model = _sample(tmp_path)
    model = replace(
        model,
        sections=tuple(
            replace(section, records=()) if section.name == "dependency_edges" else section
            for section in model.sections
        ),
    )
    level = _root(model)
    assert len(level.cells) == 1 and len(level.cells[0].relationship_ids) == 2
    assert level.cells[0].import_sites is None and level.import_status == "UNKNOWN"
    assert not any(hint.kind == "used_elsewhere" for hint in level.hint_candidates)


def test_partial_native_symbol_count_preserves_coverage_and_suppresses_heavy(tmp_path):
    model = _sample(
        tmp_path,
        extra_files={
            "sample/core.py": "\n".join(f"def function_{index}(): pass" for index in range(40)),
        },
    )
    level = _root(model)
    module = next(item for item in level.modules if item.name == "sample.core")
    report = architecture_report(model)
    coverage = tuple(
        item
        for item in report.observed.coverage
        if item.scope_id == module.id and item.entity_kinds
    )
    assert module.symbols == 40 and module.symbol_coverage == coverage
    assert any(item.status == "partial" and item.reason for item in module.symbol_coverage)
    assert not any(hint.kind == "heavy" for hint in level.hint_candidates)


def test_unknown_symbol_count_does_not_hide_other_observed_counts(tmp_path):
    model = _sample(
        tmp_path,
        extra_files={
            "sample/core.py": "\n".join(f"def f{index}(): pass" for index in range(40)),
        },
    )
    model = replace(
        model,
        sections=tuple(
            replace(
                section,
                records=tuple(
                    replace(
                        record,
                        data=RecordData(
                            tuple(
                                (key, None if key == "symbol_count" else value)
                                for key, value in record.data.entries
                            )
                        ),
                    )
                    if record.data.get("qualified_name") == "sample.peer"
                    else record
                    for record in section.records
                ),
            )
            if section.name == "modules"
            else section
            for section in model.sections
        ),
    )
    level = _root(model)
    modules = {item.name: item for item in level.modules}
    assert modules["sample.core"].symbols == 40 and modules["sample.peer"].symbols is None
    assert not any(hint.kind == "heavy" for hint in level.hint_candidates)
