# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""An exact suppression never grants permission to its neighbors (issue #228)."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_architecture_demo import _prepare_repo
from test_html_report import _native_audit

from archkeel.cli import main
from archkeel.ir.codec import (
    contract_bytes,
    decode_canonical_model,
    parse_contract,
    parse_observation,
)
from archkeel.ir.widening import contract_widenings
from fixtures.architecture_demo import CATALOG
from fixtures.architecture_demo import main as demo_main

ROOT = Path(__file__).parents[1]
ALLOWANCE = {
    "qualified_name": "sample.operations.execute_sql_script",
    "line": 4,
    "statement": "client.execute_sql_script(query)",
    "tag": "[attr-defined]",
}
SOURCE = (
    "from typing import Any, cast\n\n"
    "def execute_sql_script(client: Any, query: str) -> None:\n"
    "    client.execute_sql_script(query)  # type: ignore[attr-defined]\n"
    "    cast(str, query)\n"
    "    getattr(client, 'other')\n"
    "    client.execute_sql_script(query)  # type: ignore[attr-defined]\n\n"
    "def neighboring_function() -> None:\n"
    "    value = 1  # type: ignore[assignment]\n"
)
RULE = {
    "kind": "forbidden_construct",
    "source": "sample",
    "constructs": ["type_ignore", "cast", "any_annotation", "getattr"],
    "allowed_type_ignores": [ALLOWANCE],
}


def _contract(allowances: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "2.1.0",
        "components": [],
        "rules": [
            {
                **RULE,
                "id": "RULE",
                "rationale": "Native SQL call.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
                "allowed_type_ignores": allowances,
            }
        ],
    }


@pytest.mark.parametrize(
    "allowance",
    [
        {**ALLOWANCE, "unknown": True},
        {key: value for key, value in ALLOWANCE.items() if key != "line"},
        {**ALLOWANCE, "line": True},
        {**ALLOWANCE, "line": 0},
        {**ALLOWANCE, "qualified_name": ""},
        {**ALLOWANCE, "statement": ""},
        {**ALLOWANCE, "tag": ""},
    ],
)
def test_invalid_allowance_rejected_by_parser_and_schema(allowance: dict[str, object]) -> None:
    raw = _contract([allowance])
    with pytest.raises(ValueError):
        parse_contract(raw)
    schema = json.loads((ROOT / "schema/architecture-contract.schema.json").read_bytes())
    assert list(Draft202012Validator(schema).iter_errors(raw))


def test_allowance_round_trips_and_new_permission_widens() -> None:
    before = parse_contract(_contract([]))
    after = parse_contract(_contract([ALLOWANCE]))
    assert parse_contract(json.loads(contract_bytes(after))) == after
    assert contract_widenings(before, after)
    assert not contract_widenings(after, before)
    changed = parse_contract(_contract([{**ALLOWANCE, "line": 7}]))
    assert contract_widenings(after, changed)


def test_duplicate_allowances_are_rejected() -> None:
    raw = _contract([ALLOWANCE, ALLOWANCE])
    with pytest.raises(ValueError, match="unique"):
        parse_contract(raw)
    schema = json.loads((ROOT / "schema/architecture-contract.schema.json").read_bytes())
    assert list(Draft202012Validator(schema).iter_errors(raw))


def test_empty_allowance_preserves_legacy_contract_encoding() -> None:
    encoded = json.loads(contract_bytes(parse_contract(_contract([]))))
    assert "allowed_type_ignores" not in encoded["rules"][0]


_LINES = SOURCE.split("\n")[:-1]


@pytest.mark.parametrize(
    ("variant", "violation_count"),
    [("class-a-type-ignore-exact", 0), ("class-a-type-ignore-neighbors", 5)],
)
def test_real_git_demo_cli_reports_matched_exception(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], variant: str, violation_count: int
) -> None:
    output = tmp_path / "architecture.json"
    exit_code = demo_main(["--replay", variant, "--output", str(output)])
    assert exit_code == (2 if violation_count else 0)
    validation, report = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert report["exit_code"] == 0
    assert validation["exit_code"] == exit_code
    observation = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    assert observation.source.git_head
    assert len(observation.records("violations") or ()) == violation_count
    matches = [
        item
        for item in observation.records("typing_signals") or ()
        if item.kind == "type_ignore_allowance"
    ]
    assert len(matches) == 1
    assert matches[0].rule_ids == ("CONSTRUCT-NO-DYNAMIC",)
    html = output.with_suffix(".report.html").read_text()
    _native_audit(html, observation, output.name)
    assert matches[0].data.get("tag") == "[attr-defined]"
    assert matches[0].provenance == ("docs/architecture/shop.md",)


@pytest.mark.parametrize("broad", ["second_occurrence", "changed_tag", "module", "prefix"])
def test_against_cli_rejects_broader_suppression_permission(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], broad: str
) -> None:
    variant = next(item for item in CATALOG if item.id == "class-a-type-ignore-exact")
    root = _prepare_repo(tmp_path, dict(variant.files))
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_bytes())
    rule = next(item for item in contract["rules"] if item["id"] == "CONSTRUCT-NO-DYNAMIC")
    allowance = rule["allowed_type_ignores"][0]
    if broad == "second_occurrence":
        rule["allowed_type_ignores"].append({**allowance, "line": 8})
    elif broad == "changed_tag":
        rule["allowed_type_ignores"][0] = {**allowance, "tag": "[attr-defined, assignment]"}
        source = root / "shop/model/probe_sql.py"
        source.write_text(
            source.read_text().replace("[attr-defined]", "[attr-defined, assignment]")
        )
    else:
        rule["allowed_type_ignores"] = []
        rule["exact_sources" if broad == "module" else "allowed_sources"] = [
            "shop.model.probe_sql" if broad == "module" else "shop.model"
        ]
    path.write_text(json.dumps(contract))
    assert main(["validate", "--root", str(root), "--against", "main", "--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["failures"]
    assert "gained" in " ".join(result["failures"])
