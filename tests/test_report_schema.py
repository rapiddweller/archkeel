# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The report v2 payload schema (AD-361)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema" / "report-2.0.schema.json").read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)
TABLES = (
    "nodes",
    "measures",
    "units",
    "variants",
    "edges",
    "crossings",
    "permissions",
    "violations",
    "unknowns",
    "findings",
    "carriers",
)
COUNTS = SCHEMA["$defs"]["Summary"]["properties"]["counts"]["required"]


def _minimal() -> dict[str, object]:
    """One system node, one module, one measure row: the smallest useful payload."""
    empty = {
        name: {column: [] for column in SCHEMA["properties"][name]["required"]} for name in TABLES
    }
    empty["nodes"] = {
        "level": [0, 3],
        "parent": [-1, 0],
        "key": [0, 1],
        "name": [0, 2],
        "path": [-1, 3],
        "package": [-1, -1],
        "modules": [1, 1],
        "units": [0, 0],
        "fan_in": [0, 0],
        "fan_out": [0, 0],
    }
    empty["measures"] = {
        "node": [0],
        "def": [3],
        "state": [1],
        "value": [-1],
        "of": [-1],
        "gap": [0],
        "budget": [-1],
        "budget_source": [-1],
        "baseline": [-1],
        "baseline_source": [-1],
        "verdict": [0],
    }
    return {
        "schema_version": "2.0.0",
        "run": {
            "language": "python",
            "source": {"git_head": None, "dirty": False, "scope": ["app/**/*.py"]},
            "contract": None,
            "coverage": {"files_discovered": 1, "files_read": 1, "files_parsed": 1},
            "target": True,
            "observation": "PASS",
            "not_ranked": [],
            "not_carried": [3, 4, 5, 6, 7, 8, 9],
            "payload_budget": {"max_bytes": 8000000},
        },
        "summary": {"status": "UNKNOWN", "counts": dict.fromkeys(COUNTS, 0)},
        "rules": [],
        "gaps": [{"gap": 0, "blocks": 1}],
        "components": [],
        "trend": [],
        "strings": ["", "module:app", "app", "app/__init__.py"],
        **{name: empty[name] for name in TABLES[:5]},
        "via": [],
        **{name: empty[name] for name in TABLES[5:8]},
        "violation_rules": [],
        "violation_subjects": [],
        "violation_evidence": [],
        **{name: empty[name] for name in TABLES[8:]},
    }


def test_the_schema_is_a_valid_draft_2020_12_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)

    assert VALIDATOR.is_valid(_minimal())


def test_code_lists_are_open_within_the_major_version() -> None:
    defs = SCHEMA["$defs"]
    lists = {name: item for name, item in defs.items() if "x-codes" in item}

    assert lists
    assert all(item["minimum"] == 0 and "maximum" not in item for item in lists.values())
    assert [m["id"] for m in defs["Measure"]["x-measures"]] == defs["Measure"]["x-codes"]
    assert [g["id"] for g in defs["Gap"]["x-gaps"]] == defs["Gap"]["x-codes"]
    assert set(defs["Relation"]["x-codes"]) >= {
        "calls",
        "implements",
        "uses_type",
        "fields",
        "signatures",
    }


def test_a_later_minor_version_with_appended_codes_still_validates() -> None:
    payload = copy.deepcopy(_minimal())
    payload["schema_version"] = "2.1.0"
    measures = payload["measures"]
    assert isinstance(measures, dict)
    measures["state"] = [9]

    assert VALIDATOR.is_valid(payload)


def test_the_top_level_key_order_is_the_canonical_order() -> None:
    assert list(_minimal()) == SCHEMA["required"]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (
            ("rules",),
            [{"id": "R", "kind": "k", "title": "", "verdict": "PASS", "evaluated": False}],
        ),
        (("measures", "verdict"), [-1]),
        (("strings",), ["", "", "app", "app/__init__.py"]),
        (("run", "producer"), "archkeel 9.9"),
        (("summary", "score"), 5),
        (("schema_version",), "3.0.0"),
        (("measures", "value"), [0.5]),
    ],
)
def test_the_schema_rejects(path: tuple[str, ...], value: object) -> None:
    payload = copy.deepcopy(_minimal())
    target: dict[str, object] = payload
    for key in path[:-1]:
        child = target[key]
        assert isinstance(child, dict)
        target = child
    if path == ("rules",):
        value = [
            dict(
                value[0],
                violations=0,
                undecided=0,
                reason="evaluated",
                rationale="",
                decided_by=None,
            )
        ]  # type: ignore[index]
    target[path[-1]] = value

    assert not VALIDATOR.is_valid(payload)
