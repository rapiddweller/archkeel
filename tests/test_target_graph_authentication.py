# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Core authenticates declaration revisions and rejects forged or unavailable target facts."""

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from test_target_graph import (
    _contract,
    _nested_repository,
    _permission_contract,
    _physical_contract,
    _repository,
)

from archkeel.check.report import run_report
from archkeel.check.run import observe_revision
from archkeel.check.uml import assemble_uml
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    decode_canonical_model,
    load_inside_contract_tree,
    parse_contract,
    parse_observation,
    value_bytes,
)
from archkeel.ir.graph_codec import parse_target
from archkeel.ir.target_graph import declared_graph, declared_tree_graph
from archkeel.ir.target_records import recorded_target_graph


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0"])
def test_core_records_known_signature_failure_and_unknown_unavailable_uml_facts(
    tmp_path: Path,
    version: str,
) -> None:
    root, config = _repository(tmp_path)
    contract = _contract()
    contract["declarations"]["uml"]["schema_version"] = version
    (root / "contract.json").write_text(json.dumps(contract))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert result.exit_code == 0
    assert result.observation_complete == "PASS"
    assert result.declared_rules == "FAIL"
    assert encoded is not None
    observation = parse_observation(decode_canonical_model(json.loads(encoded)))
    intent = next(
        item for item in observation.records("declarations") or () if item.kind == "uml_target"
    )
    assert (
        parse_target(json.loads(value_bytes(intent.data.get("target"))))
        == parse_contract(contract).declarations.uml
    )
    assert any(item.kind == "uml_conformance" for item in observation.records("unknowns") or ())
    assert any(item.kind == "uml_conformance" for item in observation.records("violations") or ())


@pytest.mark.parametrize("newest_level", [None, "contract.json", "inside.json", "leaf.json"])
def test_core_uses_the_newest_declared_format_when_combining_inside_targets(tmp_path, newest_level):
    root, config = _nested_repository(tmp_path)
    root_contract = json.loads((root / config.contract).read_bytes())
    root_contract.setdefault("declarations", {})["uml"] = {"schema_version": "1.0.0"}
    (root / config.contract).write_text(json.dumps(root_contract))
    path = root / (newest_level or config.contract)
    contract = json.loads(path.read_bytes())
    contract["declarations"]["uml"]["schema_version"] = "1.1.0" if newest_level else "1.0.0"
    path.write_text(json.dumps(contract))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert result.exit_code == 0 and encoded is not None
    observation = parse_observation(decode_canonical_model(json.loads(encoded)))
    intent = next(
        item for item in observation.records("declarations") or () if item.kind == "uml_target"
    )
    assert parse_target(json.loads(value_bytes(intent.data.get("target")))).schema_version == (
        "1.1.0" if newest_level else "1.0.0"
    )


def test_snapshot_core_reads_target_from_the_materialized_declaration_revision(
    tmp_path: Path,
) -> None:
    root, config = _repository(tmp_path)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    result = observe_revision(observe, root, revision, config, declared_at=revision)
    assert result.diagnostics == ()
    assert result.observation is not None
    assert any(
        item.kind == "uml_target" for item in result.observation.records("declarations") or ()
    )


def test_core_rejects_changed_target_bytes_after_observation(tmp_path: Path) -> None:
    root, config = _repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    changed = _contract()
    changed["declarations"]["uml"]["entities"][0]["responsibilities"] = ["A changed target."]
    (root / config.contract).write_text(json.dumps(changed))
    result = assemble_uml(original, root, config.contract)
    assert result.diagnostics
    assert "authenticated contract" in result.diagnostics[0].unknown_claim


def test_core_refuses_a_contract_symlink_outside_its_declaration_root(tmp_path: Path) -> None:
    root, config = _repository(tmp_path / "repository")
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    path = root / config.contract
    outside = tmp_path / "outside.json"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    result = assemble_uml(original, root, config.contract)
    assert result.diagnostics
    assert "escapes its declaration root" in result.diagnostics[0].unknown_claim


def test_core_assembly_does_not_duplicate_its_own_declarations(tmp_path: Path) -> None:
    root, config = _repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assembled = assemble_uml(original, root, config.contract)
    assert assemble_uml(assembled, root, config.contract) == assembled


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0"])
def test_legacy_target_uses_the_standard_graph_without_adding_a_rule(tmp_path, version):
    from archkeel.ir.decisions import rule_assessments

    raw = _permission_contract()
    raw["schema_version"] = version
    del raw["declarations"]["uml"]
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(raw))
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assert original.observation is not None and not original.diagnostics
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    targets = [
        record for record in model.records("declarations") if record.kind == "architecture_target"
    ]
    assert len(targets) == 1
    assert recorded_target_graph(model, targets[0]) == declared_graph(
        parse_contract(raw), contract_path=config.contract
    )
    assert rule_assessments(model, undecided_by_rule={}) == rule_assessments(
        original.observation, undecided_by_rule={}
    )
    assert model.records("scope_observations") == original.observation.records("scope_observations")
    assert model.records("violations") == original.observation.records("violations")
    assert model.records("unknowns") == original.observation.records("unknowns")
    assert not any(record.kind == "uml_target" for record in model.records("declarations"))
    assembled = assemble_uml(original, root, config.contract)
    assert assemble_uml(assembled, root, config.contract) == assembled


@pytest.mark.parametrize("explicit_uml", [False, True])
def test_target_producers_preserve_canonical_component_metadata_order(tmp_path, explicit_uml):
    raw = _permission_contract(_physical_contract())
    if not explicit_uml:
        raw["schema_version"] = "2.1.0"
        del raw["declarations"]["uml"]
    owner = raw["components"][0]
    owner.update(
        packages=["sample.extra", "sample.core"],
        responsibilities=["Z: own storage.", "A: own operations."],
        public=["sample.core:Service", "sample.core:Port"],
        planned=["sample.core:Later", "sample.core:Future"],
        forbidden_responsibilities=["Z: parse sources.", "A: write SVG."],
        provenance=["docs/target.md", "docs/other.md"],
    )
    root, config = _repository(tmp_path)
    raw["rules"][0]["provenance"] = list(owner["provenance"])
    raw["rules"][0]["allowed_children"].reverse()
    (root / "docs/other.md").write_text("Independent boundary intent.\n")
    (root / config.contract).write_text(json.dumps(raw))
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    kind = "uml_target" if explicit_uml else "architecture_target"
    declaration = next(record for record in model.records("declarations") if record.kind == kind)
    expected = declared_graph(parse_contract(raw), contract_path=config.contract)
    assert recorded_target_graph(model, declaration) == expected
    for key in (
        "packages",
        "responsibilities",
        "public",
        "planned",
        "forbidden_responsibilities",
        "provenance",
    ):
        owner[key].reverse()
    raw["rules"][0]["provenance"].reverse()
    raw["rules"][0]["allowed_children"].reverse()
    assert declared_graph(parse_contract(raw), contract_path=config.contract) == expected


@pytest.mark.parametrize("change", ["responsibilities", "requires", "public", "role"])
def test_core_authenticates_legacy_owner_intent_before_graph_projection(tmp_path, change):
    raw = _permission_contract()
    raw["schema_version"] = "2.1.0"
    del raw["declarations"]["uml"]
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(raw))
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    model = original.observation
    assert model is not None and not original.diagnostics
    values = {
        "responsibilities": ("Invented responsibility.",),
        "requires": (),
        "public": ("sample.core:Invented",),
        "role": "foundation",
    }
    sections = tuple(
        replace(
            section,
            records=tuple(
                replace(
                    record,
                    data=replace(
                        record.data,
                        entries=tuple(
                            (key, value) for key, value in record.data.entries if key != change
                        )
                        + ((change, values[change]),),
                    ),
                )
                if record.id == "core"
                else record
                for record in section.records
            ),
        )
        for section in model.sections
    )
    result = assemble_uml(
        replace(original, observation=replace(model, sections=sections)), root, config.contract
    )
    assert result.diagnostics and "authenticated contract" in result.diagnostics[0].unknown_claim


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0"])
def test_legacy_inside_levels_and_physical_intent_share_one_graph(tmp_path, version):
    import hashlib

    root, config = _nested_repository(tmp_path)
    for path in (config.contract, "inside.json", "leaf.json"):
        raw = json.loads((root / path).read_bytes())
        raw["schema_version"] = version
        raw.get("declarations", {}).pop("uml", None)
        (root / path).write_text(json.dumps(raw))
    payload = (root / config.contract).read_bytes()
    tree = load_inside_contract_tree(
        config.contract,
        parse_contract(json.loads(payload)),
        hashlib.sha256(payload).hexdigest(),
        config.contract,
        lambda path: ((root / path).read_bytes(), path),
    )
    assert not tree.issues
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and not result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    targets = [
        record for record in model.records("declarations") if record.kind == "architecture_target"
    ]
    assert len(targets) == 1
    graph = recorded_target_graph(model, targets[0])
    assert graph == declared_tree_graph(tree, root_path=config.contract)
    assert len(graph.component_intents) == 3
    assert {item.parent_id for item in graph.component_intents} == {
        None,
        tree.mounts[0].parent.id,
        tree.mounts[1].parent.id,
    }
    assert len(graph.module_inventories) == 2
    assert any(not item.modules for item in graph.module_inventories)
    assert len(graph.layout_rules) == 1
    assert all(item.kind == "component" for item in graph.entities)
    assert not any(record.kind == "uml_conformance" for record in model.records("unknowns") or ())


def test_incomplete_legacy_inside_report_does_not_claim_a_complete_target_graph(tmp_path):
    root, config = _nested_repository(tmp_path, "2.1.0")
    (root / "inside.json").unlink()
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None and result.diagnostics and result.exit_code == 2
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    assert any(
        record.kind == "inside_contract_incomplete" for record in model.records("unknowns") or ()
    )
    assert not any(record.kind == "architecture_target" for record in model.records("declarations"))


@pytest.mark.parametrize("change", ["title", "owners", "target", "extra"])
def test_adapter_cannot_forge_a_compiled_legacy_target(tmp_path, change):
    raw = _permission_contract()
    raw["schema_version"] = "2.1.0"
    del raw["declarations"]["uml"]
    root, config = _repository(tmp_path)
    (root / config.contract).write_text(json.dumps(raw))
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assembled = assemble_uml(original, root, config.contract)
    model = assembled.observation
    assert model is not None and not assembled.diagnostics
    declaration = next(
        record for record in model.records("declarations") if record.kind == "architecture_target"
    )
    changed = replace(declaration, title="Invented") if change == "title" else declaration
    if change in ("owners", "target"):
        field = "owner_ids" if change == "owners" else "target"
        value = () if change == "owners" else None
        changed = replace(
            declaration,
            data=replace(
                declaration.data,
                entries=tuple(
                    (key, value if key == field else entry)
                    for key, entry in declaration.data.entries
                ),
            ),
        )
    sections = tuple(
        replace(
            section,
            records=(
                *tuple(
                    changed if record.id == declaration.id else record for record in section.records
                ),
                *((replace(declaration, id="invented"),) if change == "extra" else ()),
            ),
        )
        if section.name == "declarations"
        else section
        for section in model.sections
    )
    result = assemble_uml(
        replace(assembled, observation=replace(model, sections=sections)), root, config.contract
    )
    assert result.diagnostics


def test_core_rejects_a_conflicting_declaration_in_adapter_output(tmp_path: Path) -> None:
    root, config = _repository(tmp_path)
    original = observe(
        root,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
    )
    assembled = assemble_uml(original, root, config.contract)
    model = assembled.observation
    assert model is not None
    sections = tuple(
        replace(
            section,
            records=tuple(
                replace(record, title="Tampered") if record.kind == "uml_target" else record
                for record in section.records
            ),
        )
        for section in model.sections
    )
    forged = replace(assembled, observation=replace(model, sections=sections))
    result = assemble_uml(forged, root, config.contract)
    assert result.diagnostics
    assert "conflicts" in result.diagnostics[0].unknown_claim
