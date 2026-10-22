# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Full reports preserve canonical UNKNOWN evidence for independent assessment."""

import copy
import json
import shutil
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from test_report_agent_json import _root
from test_report_filter import CONFIG
from test_result_schema import current_validator as current_validator

from archkeel.check.report import run_report, run_saved_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, result_bytes, result_payload
from archkeel.ir.facts_codec import parse_record
from tools.architecture_graph_schema import command_schema


@pytest.mark.parametrize("component_selected", [False, True])
def test_full_saved_query_preserves_every_original_unknown_record_without_repository(
    tmp_path, monkeypatch, component_selected, current_validator
):
    root = _root(tmp_path, "mixed")
    live, packet = run_report(
        root, config=CONFIG, analyzer=observe, only_architecture=True, full_architecture=True
    )
    expected = decode_canonical_model(json.loads(packet))["unknowns"]
    assert expected
    payload = result_payload(live)
    assert payload["recorded_unknowns"] == expected
    assert not list(current_validator.iter_errors(payload))
    saved = tmp_path / "architecture.json"
    saved.write_bytes(packet)
    component = live.architecture_projection.components[0].id if component_selected else None
    shutil.rmtree(root)

    def forbidden(*args, **kwargs):
        raise AssertionError("saved queries must not collect or evaluate")

    monkeypatch.setattr("archkeel.check.report.observe_repository", forbidden)
    monkeypatch.setattr("archkeel.check.observation.assemble_observation", forbidden)
    outputs = []
    for _ in range(2):
        queried = run_saved_report(
            saved, only_architecture=True, full_architecture=True, component=component
        )
        assert queried.exit_code == 0
        outputs.append(result_bytes(queried))
    assert outputs[0] == outputs[1]
    queried_payload = json.loads(outputs[0])
    assert queried_payload["recorded_unknowns"] == expected
    assert not list(current_validator.iter_errors(queried_payload))
    if not component_selected:
        assert outputs[0] == result_bytes(live)
    assert saved.read_bytes() == packet
    assert list(tmp_path.iterdir()) == [saved]


@pytest.mark.parametrize("broken", [False, True])
def test_full_unknown_inventory_distinguishes_empty_from_unavailable(
    tmp_path, broken, current_validator
):
    root = _root(tmp_path, "clean")
    if broken:
        (root / "shop/app/broken.py").write_text("def broken(:\n")
    result, _ = run_report(
        root, config=CONFIG, analyzer=observe, only_architecture=True, full_architecture=True
    )
    if not broken:
        assert result.observation is not None
        empty = replace(
            result.observation,
            sections=tuple(
                replace(section, records=()) if section.name == "unknowns" else section
                for section in result.observation.sections
            ),
        )
        result = replace(result, observation=empty)
    payload = result_payload(result)
    assert payload["recorded_unknowns"] is None if broken else payload["recorded_unknowns"] == []
    assert not list(current_validator.iter_errors(payload))


def test_compact_and_unrelated_results_do_not_gain_observation_or_unknown_details(tmp_path):
    root = _root(tmp_path, "mixed")
    for architecture in (False, True):
        result, _ = run_report(
            root, config=CONFIG, analyzer=observe, only_architecture=architecture
        )
        assert result.observation is None
        payload = result_payload(result)
        assert "recorded_unknowns" not in payload
        assert result_bytes(result) == result_bytes(replace(result, observation=None))


def test_full_record_schema_rejects_wrong_evidence_class_and_missing_record_fields(
    tmp_path, current_validator
):
    root = _root(tmp_path, "mixed")
    result, _ = run_report(
        root, config=CONFIG, analyzer=observe, only_architecture=True, full_architecture=True
    )
    payload = result_payload(result)
    assert payload["recorded_unknowns"]
    for field in payload["recorded_unknowns"][0]:
        missing = copy.deepcopy(payload)
        del missing["recorded_unknowns"][0][field]
        assert list(current_validator.iter_errors(missing)), field
    wrong_class = copy.deepcopy(payload)
    wrong_class["recorded_unknowns"][0]["evidence_class"] = "FACT"
    assert list(current_validator.iter_errors(wrong_class))
    legacy = copy.deepcopy(payload)
    del legacy["recorded_unknowns"]
    legacy["schema_version"] = "1.0.0"
    assert not list(current_validator.iter_errors(legacy))


def test_same_kind_and_scope_records_keep_distinct_ids_titles_and_nested_data(
    tmp_path, current_validator
):
    root = _root(tmp_path, "mixed")
    result, packet = run_report(
        root, config=CONFIG, analyzer=observe, only_architecture=True, full_architecture=True
    )
    assert result.observation is not None
    first = result.observation.records("unknowns")[0]
    nested = {"qualified_name": "module:Reader.load", "position": "return", "paths": [["item", 1]]}
    original = decode_canonical_model(json.loads(packet))["unknowns"][0]
    expected_second = {
        **original,
        "id": first.id + "-second",
        "title": "Distinct record",
        "data": {**original["data"], "nested": nested},
    }
    second = parse_record(expected_second)
    modified = replace(
        result.observation,
        sections=tuple(
            replace(section, records=(first, second)) if section.name == "unknowns" else section
            for section in result.observation.sections
        ),
    )
    payload = result_payload(replace(result, observation=modified))
    assert payload["recorded_unknowns"] == [original, expected_second]
    assert not list(current_validator.iter_errors(payload))


def test_full_output_has_separate_version_and_preserves_legacy_consumers(
    tmp_path, current_validator
):
    root = _root(tmp_path, "mixed")
    result, _ = run_report(
        root, config=CONFIG, analyzer=observe, only_architecture=True, full_architecture=True
    )
    payload = result_payload(result)
    assert payload["schema_version"] == "2.0.0"
    old = current_validator.evolve(schema={"$ref": "urn:archkeel:architecture-command:1.0.0"})
    current = current_validator.evolve(schema={"$ref": "urn:archkeel:architecture-command:2.0.0"})
    assert current.is_valid(payload) and current_validator.is_valid(payload)
    assert not old.is_valid(payload)
    assert not current_validator.evolve(
        schema={"$ref": "urn:archkeel:command-result:6.0.0"}
    ).is_valid(payload)
    legacy = copy.deepcopy(payload)
    legacy["schema_version"] = "1.0.0"
    assert not old.is_valid(legacy)
    del legacy["recorded_unknowns"]
    assert old.is_valid(legacy) and current_validator.is_valid(legacy)
    compact, _ = run_report(root, config=CONFIG, analyzer=observe, only_architecture=True)
    compact_payload = result_payload(compact)
    assert compact_payload["schema_version"] == "1.0.0"
    assert old.is_valid(compact_payload) and current_validator.is_valid(compact_payload)
    assert not current.is_valid(compact_payload)
    unrelated, _ = run_report(root, config=CONFIG, analyzer=observe)
    assert current_validator.is_valid(result_payload(unrelated))


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "1.0.0"},
        {"schema_version": "3.0.0"},
        {"report_filter": None},
        {"report_filter": {}},
        {"report_filter": {"full_architecture": False}},
    ],
)
def test_new_full_schema_rejects_wrong_version_and_missing_full_filter(
    tmp_path, current_validator, change
):
    root = _root(tmp_path, "mixed")
    result, _ = run_report(
        root, config=CONFIG, analyzer=observe, only_architecture=True, full_architecture=True
    )
    payload = result_payload(result)
    assert payload["schema_version"] == "2.0.0"
    assert not current_validator.is_valid({**payload, **change})
    del payload["recorded_unknowns"]
    assert not current_validator.is_valid(payload)


def test_published_legacy_schemas_remain_byte_exact():
    root = Path(__file__).parents[1] / "schema"
    assert sha256((root / "architecture-command.schema.json").read_bytes()).hexdigest() == (
        "8c365e57e039b64ed8bde1061324a29742e28d20718aef181e8ac8f38eb8d8f6"
    )
    assert sha256((root / "command-result.schema.json").read_bytes()).hexdigest() == (
        "d71145ef1c7b9ec8b80b1446fe3ca6f1aa61efd94939a73a2031f6832f5ff975"
    )
    assert sha256((root / "command-result-10.0.schema.json").read_bytes()).hexdigest() == (
        "b3bf8fc8cd1b498726a7b2bebb5b9d0281ef2cc4520ac304e3027ee91ed674f5"
    )
    assert json.loads((root / "architecture-command-2.0.schema.json").read_bytes()) == (
        command_schema()
    )
