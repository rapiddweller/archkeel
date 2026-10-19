# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Physical text limits need their own complete, snapshot-bound inventory proof."""

import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from archkeel.check.declarations import project_rule_declaration
from archkeel.check.evaluation.repository_files import repository_file_results
from archkeel.ir.codec import contract_bytes, parse_contract
from archkeel.ir.codec_repository_files import repository_inventory_payload
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts import AnalyzerInfo, Evidence, SourceInfo
from archkeel.ir.facts_codec import parse_record, record_payload
from archkeel.ir.model import ContractInfo, Coverage, Observation, Section, Verdict
from archkeel.ir.repository_files import (
    RepositoryFileClassification,
    RepositoryFileDigest,
    RepositoryFileExclusion,
    RepositoryFileExclusionKind,
    RepositoryFileFact,
    RepositoryFileGap,
    RepositoryFileGapReason,
    RepositoryFileInventory,
    RepositoryFileScope,
    RepositoryFileSelection,
    RepositoryManifestInput,
    repository_path_selected,
)
from archkeel.ir.widening import contract_widening_changes

SHA = "a" * 64
SOURCE = SourceInfo("head", False, "source-digest", ("src",))


def _raw():
    return {
        "schema_version": "3.8.0",
        "components": [],
        "rules": [
            {
                "id": "MAX500",
                "kind": "max_file_lines",
                "max_lines": 500,
                "selection": {
                    "scopes": [
                        {
                            "root": ".",
                            "suffixes": [".py"],
                            "exact_filenames": ["Makefile"],
                            "shebang": True,
                        },
                        {
                            "root": ".github/workflows",
                            "suffixes": [".yml", ".yaml"],
                            "exact_filenames": [],
                            "shebang": False,
                        },
                    ],
                    "exclusions": [],
                },
                "rationale": "Keep owned sources readable",
                "provenance": ["AGENTS.md"],
                "decided_by": "architect",
            }
        ],
    }


def _inventory(rule, lines=500):
    return RepositoryFileInventory(
        rule.selection,
        ("src/main.py",),
        ("src/main.py",),
        (RepositoryFileFact("src/main.py", SHA, "TEXT", lines),),
        (),
        (),
        (),
        "head",
        False,
        (RepositoryFileClassification("src/main.py", SHA, "TEXT", False),),
    )


def _observation(rule, inventory, *, source=SOURCE, declaration=None):
    declared = declaration or project_rule_declaration(rule)
    violations, limits, receipts = repository_file_results(
        rule,
        inventory,
        scope="root",
        source=source,
        contract_digest="contract",
        declaration=declared,
    )
    witnesses = (
        (
            *inventory.files,
            *inventory.excluded_files,
            *inventory.manifest_inputs,
            *inventory.classifications,
        )
        if inventory
        else ()
    )
    return Observation(
        "2.1.0",
        AnalyzerInfo("test", "1", "code"),
        source,
        ContractInfo("architecture-contract.json", "contract", "3.8.0"),
        Coverage(Verdict.FAIL, 0, 0, 0, None, None, None, None, 0, None, ()),
        tuple(
            Section(name, tuple(parse_record(record) for record in records))
            for name, records in (
                ("declarations", [declared]),
                ("violations", violations),
                ("unknowns", limits),
                ("scope_observations", receipts),
            )
        ),
        tuple(
            Evidence(item.evidence_id, item.path, 1, 1, 0, f"sha256:{item.sha256}")
            for item in {item.evidence_id: item for item in witnesses}.values()
        ),
    )


def _row(observation):
    undecided = Counter(rule for item in observation.records("unknowns") for rule in item.rule_ids)
    [row] = rule_assessments(observation, undecided_by_rule=undecided)
    return row


@pytest.mark.parametrize("lines,status", [(0, "PASS"), (499, "PASS"), (500, "PASS"), (501, "FAIL")])
def test_limit_is_independent_of_language_parser_coverage(lines, status):
    [rule] = parse_contract(_raw()).rules
    row = _row(_observation(rule, _inventory(rule, lines)))
    assert row.status == status and row.evaluation_proven
    assert row.count == (lines > 500)


def test_zero_limit_is_valid_and_only_accepts_empty_file():
    [rule] = parse_contract(_raw()).rules
    rule = replace(rule, max_lines=0)
    assert _row(_observation(rule, _inventory(rule, 0))).status == "PASS"
    assert _row(_observation(rule, _inventory(rule, 1))).status == "FAIL"


@pytest.mark.parametrize("missing", ["inventory", "empty", "unread", "omitted", "gap"])
def test_missing_inputs_never_certify_pass(missing):
    [rule] = parse_contract(_raw()).rules
    inventory = _inventory(rule)
    if missing == "inventory":
        inventory = None
    elif missing == "empty":
        inventory = replace(inventory, expected_paths=(), selected_paths=(), files=())
    elif missing == "unread":
        inventory = replace(inventory, files=())
    elif missing == "omitted":
        inventory = replace(inventory, expected_paths=("src/main.py", "src/omitted.py"))
    else:
        inventory = replace(
            inventory, gaps=(RepositoryFileGap("src/main.py", RepositoryFileGapReason.READ),)
        )
    row = _row(_observation(rule, inventory))
    assert row.status == "UNKNOWN" and not row.evaluation_proven and row.undecided == 1


def test_known_violation_survives_an_independent_unread_file():
    [rule] = parse_contract(_raw()).rules
    inventory = replace(
        _inventory(rule, 501),
        expected_paths=("src/main.py", "src/unread.py"),
        selected_paths=("src/main.py", "src/unread.py"),
        gaps=(RepositoryFileGap("src/unread.py", RepositoryFileGapReason.READ),),
    )
    row = _row(_observation(rule, inventory))
    assert row.status == "FAIL" and row.count == 1 and row.undecided == 1
    assert not row.evaluation_proven


@pytest.mark.parametrize(
    "mutation",
    [
        "generic",
        "rule_id",
        "limit",
        "selection",
        "snapshot",
        "source_digest",
        "contract",
        "schema",
        "inventory",
        "missing_evidence",
    ],
)
def test_receipt_cannot_be_replayed_for_different_proof_inputs(mutation):
    [rule] = parse_contract(_raw()).rules
    observation = _observation(rule, _inventory(rule))
    sections = list(observation.sections)
    if mutation in {"generic", "inventory"}:
        records = list(sections[-1].records)
        payload = record_payload(records[-1 if mutation == "generic" else 0])
        if mutation == "generic":
            payload["data"] = {"scope": "root", "assessment_complete": True}
        else:
            payload["data"]["files"][0]["physical_lines"] = 1
        records[-1 if mutation == "generic" else 0] = parse_record(payload)
        sections[-1] = replace(sections[-1], records=tuple(records))
        observation = replace(observation, sections=tuple(sections))
    elif mutation in {"rule_id", "limit", "selection"}:
        changed = (
            replace(rule, id="OTHER") if mutation == "rule_id" else replace(rule, max_lines=501)
        )
        if mutation == "selection":
            changed = replace(
                rule, selection=RepositoryFileSelection((RepositoryFileScope("src", (".py",)),))
            )
        sections[0] = replace(
            sections[0], records=(parse_record(project_rule_declaration(changed)),)
        )
        observation = replace(observation, sections=tuple(sections))
    elif mutation == "snapshot":
        observation = replace(observation, source=replace(SOURCE, git_head="different"))
    elif mutation == "source_digest":
        observation = replace(observation, source=replace(SOURCE, source_digest="different"))
    elif mutation == "contract":
        observation = replace(
            observation, contract=replace(observation.contract, digest="different")
        )
    elif mutation == "schema":
        observation = replace(observation, schema_version="2.2.0")
    else:
        observation = replace(observation, evidence=())
    row = _row(observation)
    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize(
    "path,content,selected",
    [
        ("src/a.py", b"", True),
        ("Makefile", b"", True),
        ("bin/run", b"#!/bin/sh\n", True),
        (".github/workflows/ci.yml", b"", True),
        ("docs/example.yml", b"", False),
        ("x/Makefile.other", b"", False),
        ("bin/plain", b"", False),
    ],
)
def test_each_scope_owns_its_suffix_and_basename_and_shebang_selection(path, content, selected):
    [rule] = parse_contract(_raw()).rules
    assert repository_path_selected(rule.selection, path, content) is selected


@pytest.mark.parametrize("value", [True, False, -1, 1.5, "500", None])
def test_invalid_limits_are_rejected_by_codec(value):
    raw = _raw()
    raw["rules"][0]["max_lines"] = value
    with pytest.raises(ValueError):
        parse_contract(raw)


@pytest.mark.parametrize("path", ["", "/root", "../src", "a/../b", "a//b", "a\\b", "C:/src"])
def test_scope_paths_must_be_normalized_and_relative(path):
    raw = _raw()
    raw["rules"][0]["selection"]["scopes"][0]["root"] = path
    with pytest.raises(ValueError):
        parse_contract(raw)


def test_version_roundtrip_and_schema_admit_only_new_feature_version():
    raw = _raw()
    schema = json.loads(
        (Path(__file__).parents[1] / "schema/architecture-contract-3.8.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(raw)
    contract = parse_contract(raw)
    assert parse_contract(json.loads(contract_bytes(contract))) == contract
    raw["schema_version"] = "3.7.0"
    with pytest.raises(ValueError, match="3.8.0"):
        parse_contract(raw)
    with pytest.raises(ValueError, match="3.8.0"):
        contract_bytes(replace(contract, schema_version="3.7.0"))


@pytest.mark.parametrize(
    "change,widens",
    [
        ("raise", True),
        ("lower", False),
        ("remove", True),
        ("scope", True),
        ("expand", False),
        ("exclude", True),
    ],
)
def test_widening_tracks_limit_selection_and_exact_exclusion_permissions(change, widens):
    before = parse_contract(_raw())
    [rule] = before.rules
    if change in {"raise", "lower"}:
        after = replace(before, rules=(replace(rule, max_lines=501 if change == "raise" else 499),))
    elif change == "remove":
        after = replace(before, rules=())
    elif change == "scope":
        after = replace(
            before,
            rules=(
                replace(
                    rule, selection=RepositoryFileSelection((RepositoryFileScope("src", (".py",)),))
                ),
            ),
        )
    elif change == "expand":
        selection = replace(
            rule.selection, scopes=(*rule.selection.scopes, RepositoryFileScope(".", (".js",)))
        )
        after = replace(before, rules=(replace(rule, selection=selection),))
    else:
        exclusion = RepositoryFileExclusion(
            RepositoryFileExclusionKind.FILE, "vendor.py", SHA, "Vendored", ("LICENSE",)
        )
        after = replace(
            before,
            rules=(replace(rule, selection=replace(rule.selection, exclusions=(exclusion,))),),
        )
    assert bool(contract_widening_changes(before, after)) is widens


def test_inventory_digest_covers_excluded_bytes_manifest_inputs_and_snapshot():
    [rule] = parse_contract(_raw()).rules
    inventory = _inventory(rule)
    changed = replace(
        inventory,
        manifest_inputs=(
            RepositoryManifestInput(
                "manifest.json", hashlib.sha256(b"{}").hexdigest(), "MANIFEST", "{}"
            ),
        ),
    )
    assert changed.digest != inventory.digest
    assert replace(inventory, snapshot_dirty=True).digest != inventory.digest
    assert repository_inventory_payload(inventory)["digest"] == inventory.digest


def test_mounted_rule_receipt_binds_the_actual_parent_declaration():
    from archkeel.check.declarations import project_inside_declarations
    from archkeel.ir.codec_inside import _scoped_inside_contract

    mounted = _scoped_inside_contract("PARENT", parse_contract(_raw()))
    [rule] = mounted.rules
    [declaration] = project_inside_declarations("PARENT", mounted, "inside.json")
    observation = _observation(rule, _inventory(rule), declaration=declaration)
    assert _row(observation).status == "PASS"
    changed = record_payload(observation.sections[0].records[0])
    changed["data"]["parent_id"] = "OTHER"
    sections = (
        replace(observation.sections[0], records=(parse_record(changed),)),
        *observation.sections[1:],
    )
    assert _row(replace(observation, sections=sections)).status == "UNKNOWN"


def test_stale_snapshot_files_do_not_create_current_violations():
    [rule] = parse_contract(_raw()).rules
    stale = replace(_inventory(rule, 501), snapshot_head="old")
    row = _row(_observation(rule, stale))
    assert row.status == "UNKNOWN" and row.count == 0 and row.undecided == 1


@pytest.mark.parametrize("value", [True, False, -1])
def test_direct_models_reject_boolean_and_negative_counts(value):
    [rule] = parse_contract(_raw()).rules
    with pytest.raises(ValueError):
        replace(rule, max_lines=value)
    with pytest.raises(ValueError):
        RepositoryFileFact("src/main.py", SHA, "TEXT", value)


@pytest.mark.parametrize("kind", list(RepositoryFileExclusionKind))
def test_pinned_exclusions_need_matching_witnesses(kind):
    [rule] = parse_contract(_raw()).rules
    content = json.dumps({"path": "vendor.py", "sha256": SHA})
    digest = hashlib.sha256(content.encode()).hexdigest()
    path = "vendor.py" if kind is RepositoryFileExclusionKind.FILE else "registry.json"
    exclusion = RepositoryFileExclusion(
        kind,
        path,
        SHA if kind is RepositoryFileExclusionKind.FILE else digest,
        "Generated",
        ("LICENSE",),
    )
    rule = replace(rule, selection=replace(rule.selection, exclusions=(exclusion,)))
    inventory = replace(
        _inventory(rule),
        expected_paths=("src/main.py", "vendor.py", "registry.json"),
        selected_paths=("src/main.py", "vendor.py"),
        excluded_files=(RepositoryFileDigest("vendor.py", SHA, "VENDOR"),),
        classifications=(
            RepositoryFileClassification("src/main.py", SHA, "TEXT", False),
            RepositoryFileClassification("vendor.py", SHA, "VENDOR", False),
            RepositoryFileClassification("registry.json", digest, "MANIFEST", False),
        ),
        manifest_inputs=(RepositoryManifestInput("registry.json", digest, "MANIFEST", content),)
        if kind is RepositoryFileExclusionKind.MANIFEST
        else (),
    )
    assert _row(_observation(rule, inventory)).status == "PASS"
    if kind is RepositoryFileExclusionKind.FILE:
        bad = replace(
            inventory, excluded_files=(RepositoryFileDigest("vendor.py", "b" * 64, "VENDOR"),)
        )
    else:
        bad = replace(inventory, manifest_inputs=())
    assert _row(_observation(rule, bad)).status == "UNKNOWN"


def test_file_rule_cannot_receive_a_generic_module_receipt():
    from archkeel.check.evaluation.rules import rule_evaluation_facts, rule_scopes
    from archkeel.ir.profiles import PYTHON

    contract = parse_contract(_raw())
    assert rule_scopes(contract.rules[0]) == {}
    assert (
        rule_evaluation_facts(
            contract,
            profile=PYTHON,
            scope="root",
            modules=[],
            source_modules=None,
            blank_modules=frozenset(),
            receipt_scope_complete=True,
        )
        == []
    )


def test_receipt_does_not_turn_a_removed_known_violation_into_pass():
    [rule] = parse_contract(_raw()).rules
    observation = _observation(rule, _inventory(rule, 501))
    sections = tuple(
        replace(section, records=()) if section.name == "violations" else section
        for section in observation.sections
    )
    row = _row(replace(observation, sections=sections))
    assert row.status == "UNKNOWN" and not row.evaluation_proven


def maximal_file_lines_rule():
    rule = _raw()["rules"][0]
    rule["selection"]["exclusions"] = [
        {
            "kind": "file",
            "path": "vendor.py",
            "sha256": SHA,
            "rationale": "Pinned generated source",
            "provenance": ["LICENSE"],
        }
    ]
    return rule
