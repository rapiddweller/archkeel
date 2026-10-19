# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Saved text-rule proof cannot omit classified scripts or invent manifest exclusions."""

import hashlib
import json
from dataclasses import replace

import pytest
from test_max_file_lines import SHA, _inventory, _observation, _raw, _row

from archkeel.ir.codec import parse_contract
from archkeel.ir.facts_codec import parse_record, record_payload
from archkeel.ir.repository_files import (
    RepositoryFileClassification,
    RepositoryFileDigest,
    RepositoryFileExclusion,
    RepositoryFileExclusionKind,
    RepositoryManifestInput,
)


def _claim_completed(observation):
    sections = []
    for section in observation.sections:
        if section.name == "unknowns":
            sections.append(replace(section, records=()))
            continue
        records = []
        for record in section.records:
            if record.kind == "rule_evaluation":
                raw = record_payload(record)
                raw["data"]["assessment_complete"] = True
                record = parse_record(raw)
            records.append(record)
        sections.append(replace(section, records=tuple(records)))
    return replace(observation, sections=tuple(sections))


@pytest.mark.parametrize("has_classification", [False, True])
def test_an_omitted_shebang_candidate_cannot_replay_as_complete(has_classification):
    [rule] = parse_contract(_raw()).rules
    inventory = _inventory(rule)
    classifications = inventory.classifications
    if has_classification:
        classifications += (RepositoryFileClassification("bin/run", SHA, "SCRIPT", True),)
    inventory = replace(
        inventory, expected_paths=("src/main.py", "bin/run"), classifications=classifications
    )
    observation = _claim_completed(_observation(rule, inventory))
    row = _row(observation)
    assert row.status == "UNKNOWN" and not row.evaluation_proven and row.undecided == 0


def _manifest_inventory(granted_path):
    [rule] = parse_contract(_raw()).rules
    content = json.dumps({"path": granted_path, "sha256": SHA})
    digest = hashlib.sha256(content.encode()).hexdigest()
    selection = replace(
        rule.selection,
        exclusions=(
            RepositoryFileExclusion(
                RepositoryFileExclusionKind.MANIFEST,
                "registry.json",
                digest,
                "Generated fixtures",
                ("LICENSE",),
            ),
        ),
    )
    rule = replace(rule, selection=selection)
    inventory = replace(
        _inventory(rule),
        expected_paths=("src/main.py", "vendor.py", "registry.json"),
        selected_paths=("src/main.py", "vendor.py"),
        excluded_files=(RepositoryFileDigest("vendor.py", SHA, "VENDOR"),),
        manifest_inputs=(RepositoryManifestInput("registry.json", digest, "MANIFEST", content),),
        classifications=(
            RepositoryFileClassification("src/main.py", SHA, "TEXT", False),
            RepositoryFileClassification("vendor.py", SHA, "VENDOR", False),
            RepositoryFileClassification("registry.json", digest, "MANIFEST", False),
        ),
    )
    return rule, inventory


@pytest.mark.parametrize("granted_path,status", [("vendor.py", "PASS"), ("other.py", "UNKNOWN")])
def test_a_pinned_manifest_grants_only_its_actual_path_digest_entries(granted_path, status):
    rule, inventory = _manifest_inventory(granted_path)
    row = _row(_claim_completed(_observation(rule, inventory)))
    assert row.status == status and row.evaluation_proven is (status == "PASS")


def test_changing_manifest_content_without_its_pinned_hash_is_rejected():
    _, inventory = _manifest_inventory("vendor.py")
    with pytest.raises(ValueError, match="pinned digest"):
        replace(
            inventory.manifest_inputs[0], content=json.dumps({"path": "other.py", "sha256": SHA})
        )


def test_classification_hash_must_equal_the_counted_file_hash():
    [rule] = parse_contract(_raw()).rules
    inventory = replace(
        _inventory(rule),
        classifications=(RepositoryFileClassification("src/main.py", "b" * 64, "TEXT", False),),
    )
    row = _row(_claim_completed(_observation(rule, inventory)))
    assert row.status == "UNKNOWN" and not row.evaluation_proven


def test_missing_manifest_content_cannot_replay_a_previously_complete_receipt():
    rule, inventory = _manifest_inventory("vendor.py")
    observation = _observation(rule, inventory)
    sections = []
    for section in observation.sections:
        records = []
        for record in section.records:
            if record.kind == "repository_file_inventory":
                raw = record_payload(record)
                del raw["data"]["manifest_inputs"][0]["content"]
                record = parse_record(raw)
            records.append(record)
        sections.append(replace(section, records=tuple(records)))
    row = _row(replace(observation, sections=tuple(sections)))
    assert row.status == "UNKNOWN" and not row.evaluation_proven
