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
from archkeel.ir.facts import RecordData
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
):
    root, config = _repository(tmp_path)
    contract = json.loads((root / config.contract).read_bytes())
    contract.pop("declarations")
    contract["components"][0]["requires"] = []
    contract["components"][0]["exact_modules"] = list(core_exact)
    peer = dict(contract["components"][0])
    peer.update(id="peer", label="peer", packages=["sample.peer"], namespace="sample.peer")
    peer["requires"] = [{"component": "core", "rationale": "Read the core interface."}]
    if not permitted:
        peer["requires"] = []
    peer["exact_modules"] = list(peer_exact)
    contract["components"].append(peer)
    if ambiguous:
        contract["components"][0].pop("namespace")
        contract["components"].append(
            dict(contract["components"][0], id="overlap", label="overlap")
        )
    contract["rules"] = [
        {
            "id": "dependencies",
            "kind": "complete_requires",
            "rationale": "Each crossing must be explicitly granted.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
    ]
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
