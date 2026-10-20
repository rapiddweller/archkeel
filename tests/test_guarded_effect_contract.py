import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from archkeel.ir.codec import contract_bytes, parse_contract
from archkeel.ir.model import (
    ForbiddenEffectUnderConditionRule,
    module_references,
)
from archkeel.ir.renames import renamed_contract

ROOT = Path(__file__).parents[1]


def _contract(*, version="3.13.0", condition=None):
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_text())
    raw["schema_version"] = version
    raw["rules"] = [
        {
            "id": "NO-RANDOM-WHEN-SEEDED",
            "kind": "forbidden_effect_under_condition",
            "source": "sample.core",
            "target": "secrets.token_hex",
            "condition": condition
            or {"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
            "rationale": "Seeded execution must not consume nondeterministic bytes.",
            "provenance": ["docs/policy.md"],
            "decided_by": "architect",
        }
    ]
    return raw


@pytest.mark.parametrize(
    "selector",
    [
        {"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
        {"kind": "member", "owner": "sample.core.Generator", "name": "seeded"},
    ],
)
def test_guarded_effect_rule_round_trips_exact_condition_selector(selector):
    contract = parse_contract(_contract(condition=selector))

    rule = contract.rules[0]
    assert isinstance(rule, ForbiddenEffectUnderConditionRule)
    assert rule.condition.kind == selector["kind"]
    assert rule.condition.owner == selector["owner"]
    assert rule.condition.name == selector["name"]
    assert parse_contract(json.loads(contract_bytes(contract))) == contract
    schema = json.loads((ROOT / "schema/architecture-contract-3.13.schema.json").read_text())
    assert Draft202012Validator(schema).is_valid(json.loads(contract_bytes(contract)))


@pytest.mark.parametrize(
    "selector",
    [
        {"kind": "local", "owner": "sample.core.generate", "name": "seeded"},
        {"kind": "parameter", "owner": "sample.core.generate", "name": "seeded", "typo": True},
        {"kind": "member", "owner": "sample.core.Generator", "name": ""},
    ],
)
def test_guarded_effect_rule_rejects_untyped_or_extra_selector_fields(selector):
    with pytest.raises(ValueError):
        parse_contract(_contract(condition=selector))


def test_guarded_effect_rule_requires_its_contract_feature_version():
    with pytest.raises(ValueError, match="forbidden_effect_under_condition"):
        parse_contract(_contract(version="3.7.0"))

    old_schema = json.loads((ROOT / "schema/architecture-contract-3.7.schema.json").read_text())
    assert not Draft202012Validator(old_schema).is_valid(_contract(version="3.7.0"))


def test_guarded_effect_rule_fields_are_registered_for_module_renames():
    contract = parse_contract(_contract())
    references = {reference.pointer: reference for reference in module_references(contract)}
    assert references["/rules/0/source"].value == "sample.core"
    assert references["/rules/0/source"].held
    assert references["/rules/0/target"].value == "secrets.token_hex"
    assert not references["/rules/0/target"].held
    assert references["/rules/0/condition/owner"].value == "sample.core.generate"

    moved = renamed_contract(contract, {"sample.core": "moved.core"})
    rule = moved.rules[0]
    assert isinstance(rule, ForbiddenEffectUnderConditionRule)
    assert rule.source == "moved.core"
    assert rule.target == "secrets.token_hex"
    assert rule.condition.owner == "moved.core.generate"
