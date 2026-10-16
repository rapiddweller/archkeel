# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Native call evidence refines structural review candidates without inventing certainty."""

import json
from dataclasses import replace
import pytest
from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.duplication import MINIMUM_SHAPE_NODES, repeated_logic
from archkeel.ir.facts import Record
from archkeel.ir.facts_codec import freeze_data, thaw_data
from archkeel.ir.model import Observation, Verdict

_OWNER = "shop.model.converters"
_OUTSIDE = "shop.app.converters"

_MODEL = """from enum import StrEnum

class First(StrEnum):
    VALUE = "value"

class Second(StrEnum):
    VALUE = "value"

class Third(StrEnum):
    VALUE = "value"

def a_first(value: str) -> First:
    converted = First(str(value))
    return converted

def z_second(value: str) -> Second:
    converted = Second(str(value))
    return converted
"""

_APP = """from shop.model.converters import First, Second, Third
from shop.model.converters import First as FirstAlias

def same(value: str) -> First:
    converted = First(str(value))
    return converted

def aliased(value: str) -> First:
    converted = FirstAlias(str(value))
    return converted

def different(value: str) -> Third:
    converted = Third(str(value))
    return converted

def second(value: str) -> Second:
    converted = Second(str(value))
    return converted
"""


@pytest.fixture(scope="module")
def converter_observation(tmp_path_factory: pytest.TempPathFactory) -> Observation:
    root = _prepare_repo(
        tmp_path_factory.mktemp("converters"),
        {"shop/model/converters.py": _MODEL, "shop/app/converters.py": _APP},
    )
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    symbols = [
        row
        for row in observation.records("symbols") or ()
        if row.data.get("qualified_name")
        in {f"{_OWNER}.a_first", f"{_OWNER}.z_second", f"{_OUTSIDE}.different"}
    ]
    assert len(symbols) == 3
    assert len({row.data.get("shape") for row in symbols}) == 1
    assert all(row.data.get("shape_nodes") >= MINIMUM_SHAPE_NODES for row in symbols)
    assert observation.coverage.status == Verdict.PASS
    assert observation.coverage.calls_analyzed == len(observation.records("calls") or ())
    return observation


def _pairs(observation: Observation) -> dict[str, str]:
    return {
        item.outside: item.inside
        for item in repeated_logic(observation).candidates
        if item.outside.startswith(f"{_OUTSIDE}.")
    }


def _with_calls(observation: Observation, records: tuple[Record, ...]) -> Observation:
    return replace(
        observation,
        sections=tuple(
            replace(section, records=records) if section.name == "calls" else section
            for section in observation.sections
        ),
    )


@pytest.mark.parametrize("name", ["same", "aliased"])
def test_same_converter_and_its_import_alias_remain_candidates(
    converter_observation: Observation, name: str
) -> None:
    assert _pairs(converter_observation)[f"{_OUTSIDE}.{name}"] == f"{_OWNER}.a_first"


def test_distinct_canonical_converter_is_not_the_same_owned_logic(
    converter_observation: Observation,
) -> None:
    assert f"{_OUTSIDE}.different" not in _pairs(converter_observation)


def test_the_first_compatible_inside_function_is_used(
    converter_observation: Observation,
) -> None:
    assert _pairs(converter_observation)[f"{_OUTSIDE}.second"] == f"{_OWNER}.z_second"


def test_record_order_does_not_change_call_correspondence(
    converter_observation: Observation,
) -> None:
    reordered = _with_calls(
        converter_observation, tuple(reversed(converter_observation.records("calls") or ()))
    )
    assert _pairs(reordered) == _pairs(converter_observation)


@pytest.mark.parametrize(
    "fault",
    [
        "missing_status",
        "ambiguous",
        "truncated",
        "missing_target",
        "missing_evidence",
        "duplicate_position",
        "wrong_definition",
        "missing_record",
    ],
)
def test_unproven_call_evidence_preserves_the_original_candidate(
    converter_observation: Observation, fault: str
) -> None:
    records = converter_observation.records("calls") or ()
    row = next(
        item
        for item in records
        if item.data.get("source_scope") == f"{_OUTSIDE}.different"
        and item.data.get("expression") == "Third"
    )
    data = thaw_data(row.data)
    changed = row
    match fault:
        case "missing_status":
            del data["status"]
        case "ambiguous":
            data.update(
                status="partially_resolved",
                targets=[f"{_OWNER}.Third", f"{_OWNER}.First"],
                candidate_count=2,
            )
        case "truncated":
            data.update(candidates_truncated=True, candidate_count=2)
        case "missing_target":
            data.update(targets=[], candidate_count=0)
        case "missing_evidence":
            changed = replace(row, evidence_ids=())
        case "duplicate_position":
            sibling = next(
                item
                for item in records
                if item.data.get("source_scope") == f"{_OUTSIDE}.different" and item.id != row.id
            )
            changed = replace(row, evidence_ids=sibling.evidence_ids)
        case "wrong_definition":
            data["source_definition_id"] = "not-the-native-definition"
        case "missing_record":
            missing = _with_calls(
                converter_observation, tuple(item for item in records if item.id != row.id)
            )
            assert f"{_OUTSIDE}.different" in _pairs(missing)
            return
    changed = replace(changed, data=freeze_data(data))
    incomplete = _with_calls(
        converter_observation, tuple(changed if item.id == row.id else item for item in records)
    )
    assert _pairs(incomplete)[f"{_OUTSIDE}.different"] == f"{_OWNER}.a_first"


def test_equal_reduced_counts_do_not_prove_correspondence_when_both_sides_lose_calls(
    converter_observation: Observation,
) -> None:
    """Removing different sites must not align the remaining enum and builtin calls."""
    records = converter_observation.records("calls") or ()
    removed = {
        row.id
        for row in records
        if (
            row.data.get("source_scope") == f"{_OWNER}.a_first"
            and row.data.get("expression") == "str"
        )
        or (
            row.data.get("source_scope") == f"{_OUTSIDE}.different"
            and row.data.get("expression") == "Third"
        )
    }
    assert len(removed) == 2
    incomplete = _with_calls(
        converter_observation, tuple(row for row in records if row.id not in removed)
    )
    assert _pairs(incomplete)[f"{_OUTSIDE}.different"] == f"{_OWNER}.a_first"


def test_missing_call_section_and_incomplete_collection_retain_candidates(
    converter_observation: Observation,
) -> None:
    without_calls = replace(
        converter_observation,
        sections=tuple(
            section for section in converter_observation.sections if section.name != "calls"
        ),
    )
    incomplete = replace(
        converter_observation,
        coverage=replace(converter_observation.coverage, status=Verdict.FAIL),
    )
    for observation in (without_calls, incomplete):
        assert _pairs(observation)[f"{_OUTSIDE}.different"] == f"{_OWNER}.a_first"


def test_ambiguous_function_definition_retains_the_candidate(
    converter_observation: Observation,
) -> None:
    sections = []
    for section in converter_observation.sections:
        if section.name == "symbols":
            row = next(
                item
                for item in section.records
                if item.data.get("qualified_name") == f"{_OUTSIDE}.different"
            )
            section = replace(
                section, records=(*section.records, replace(row, id=f"{row.id}-other-definition"))
            )
        sections.append(section)
    ambiguous = replace(converter_observation, sections=tuple(sections))
    assert _pairs(ambiguous)[f"{_OUTSIDE}.different"] == f"{_OWNER}.a_first"
