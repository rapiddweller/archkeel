# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-ownership rules use a closed role and source-owner grammar."""

import json
from pathlib import Path

import pytest

from archkeel.ir.architecture_graph import ArchitectureRuleKind
from archkeel.ir.codec import contract_bytes, parse_contract

ROOT = Path(__file__).parents[1]


def _contract(rule, version="3.8.0"):
    value = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    value["schema_version"] = version
    value["rules"] = [
        {
            "id": "ownership",
            "kind": "source_ownership",
            "source": "sample.consumer",
            "rationale": "Keep one canonical owner.",
            "provenance": ["docs/architecture/decisions/ad-249-source-ownership-defaults.md"],
            "decided_by": "architect",
            **rule,
        }
    ]
    return value


def test_retired_symbol_rule_roundtrips_typed_roles():
    contract = parse_contract(
        _contract(
            {
                "mode": "retired",
                "symbols": ["sample.consumer.retired_cursor"],
                "roles": ["definition", "read", "write", "delete"],
            }
        )
    )
    [rule] = contract.rules
    assert rule.kind is ArchitectureRuleKind.SOURCE_OWNERSHIP
    assert rule.mode == "retired"
    assert rule.roles == ("definition", "read", "write", "delete")
    assert parse_contract(json.loads(contract_bytes(contract))) == contract


def test_confined_default_rule_names_parameter_and_source_value_owner():
    contract = parse_contract(
        _contract(
            {
                "mode": "confined",
                "value_owner": "sample.defaults.FALLBACK_REGION",
                "parameters": ["sample.consumer.normalize.region"],
                "roles": ["parameter_default", "fallback"],
            }
        )
    )
    [rule] = contract.rules
    assert rule.value_owner == "sample.defaults.FALLBACK_REGION"
    assert rule.parameters == ("sample.consumer.normalize.region",)
    assert rule.roles == ("parameter_default", "fallback")


def test_confined_callable_transfer_requires_an_owner():
    contract = parse_contract(
        _contract(
            {
                "mode": "confined",
                "owner": "sample.storage",
                "symbols": ["random.random"],
                "roles": ["value_transfer"],
            }
        )
    )
    assert contract.rules[0].owner == "sample.storage"


@pytest.mark.parametrize(
    "rule",
    [
        {"mode": "retired", "symbols": ["sample.old"], "roles": ["value_transfer"]},
        {"mode": "confined", "symbols": ["sample.old"], "roles": ["definition"]},
        {
            "mode": "confined",
            "owner": "sample.owner",
            "symbols": ["sample.old"],
            "roles": ["definition", "mystery"],
        },
        {
            "mode": "confined",
            "owner": "sample.owner",
            "value_owner": "sample.defaults.VALUE",
            "symbols": ["sample.old"],
            "roles": ["definition"],
        },
        {
            "mode": "confined",
            "parameters": [
                "sample.consumer.normalize.region",
                "sample.consumer.bad.region",
            ],
            "roles": ["fallback"],
        },
    ],
)
def test_invalid_mode_role_owner_combinations_are_rejected(rule):
    with pytest.raises(ValueError):
        parse_contract(_contract(rule))


def test_source_ownership_requires_contract_3_8():
    with pytest.raises(ValueError, match="source_ownership requires contract schema_version 3.8.0"):
        parse_contract(
            _contract(
                {"mode": "retired", "symbols": ["sample.old"], "roles": ["definition"]}, "3.7.0"
            )
        )


def _component(label, packages, *, inside=None):
    component = {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": packages,
        "responsibilities": [f"Own {label}."],
        "forbidden_responsibilities": [],
        "provenance": ["docs/architecture/decisions/ad-249-source-ownership-defaults.md"],
    }
    if inside is not None:
        component["inside"] = inside
    return component


def _source_rule(**fields):
    return {
        "id": "ownership",
        "kind": "source_ownership",
        "source": "sample.consumer",
        "rationale": "Keep one canonical owner.",
        "provenance": ["docs/architecture/decisions/ad-249-source-ownership-defaults.md"],
        "decided_by": "architect",
        **fields,
    }


def _observe_tree(tmp_path, files, contract):
    import json

    from archkeel.cli.observe import observe

    all_files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "docs/architecture/decisions/ad-249-source-ownership-defaults.md": "Decision.\n",
        "contract.json": json.dumps(contract),
        **files,
    }
    for relative, source in all_files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    return observe(
        tmp_path,
        roots=("sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )


def test_retired_definition_read_write_delete_roles_fail(tmp_path):
    from archkeel.ir.decisions import rule_assessments

    contract = _contract(
        {
            "mode": "retired",
            "symbols": ["sample.consumer.retired_cursor"],
            "roles": ["definition", "read", "write", "delete"],
        }
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/consumer.py": (
                "retired_cursor = 0\nretired_cursor += 1\n"
                "def read(): return retired_cursor\n"
                "del retired_cursor\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = [
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.id == "ownership"
    ]
    assert assessment.status == "FAIL"
    assert assessment.count >= 4
    role_facts = [
        item for item in result.observation.records("references") if item.kind == "source_role"
    ]
    assert {item.data.get("role") for item in role_facts} >= {"definition", "write", "delete"}
    assert any(
        item.kind == "value_reference"
        and "sample.consumer.retired_cursor" in item.data.get("targets", ())
        for item in result.observation.records("references")
    )


def test_inline_parameter_default_and_fallback_duplicate_canonical_value(tmp_path):
    import copy

    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload, parse_observation
    from archkeel.ir.decisions import rule_assessments

    contract = _contract(
        {
            "mode": "confined",
            "value_owner": "sample.defaults.FALLBACK_REGION",
            "parameters": [
                "sample.consumer.normalize.region",
                "sample.consumer.bad.region",
            ],
            "roles": ["parameter_default", "fallback"],
        }
    )
    contract["rules"] = [
        _source_rule(
            **{
                key: value
                for key, value in contract["rules"][0].items()
                if key not in {"id", "kind", "source", "rationale", "provenance", "decided_by"}
            }
        )
    ]
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/defaults.py": 'FALLBACK_REGION = "ZZ"\n',
            "sample/consumer.py": (
                "from .defaults import FALLBACK_REGION\n"
                "def normalize(region=FALLBACK_REGION): "
                "return (region or FALLBACK_REGION).upper()\n"
                'def bad(region="ZZ"): return (region or "ZZ").upper()\n'
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = [
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.id == "ownership"
    ]
    assert assessment.status == "FAIL"
    assert assessment.count == 2
    [receipt] = [
        item
        for item in result.observation.records("scope_observations")
        if item.kind == "rule_evaluation" and item.rule_ids == ("ownership",)
    ]
    assert receipt.data.get("source_ownership_scope_proof") is not None
    saved = tmp_path / "architecture.json"
    saved.write_bytes(canonical_report_bytes(result.observation))
    [replayed] = [
        item for item in run_saved_report(saved).rule_assessments if item.id == "ownership"
    ]
    assert replayed == assessment
    changed = copy.deepcopy(observation_payload(result.observation))
    changed["references"] = [
        item for item in changed["references"] if item["kind"] != "source_role"
    ]
    stale = parse_observation(changed)
    [stale_assessment] = [
        item for item in rule_assessments(stale, undecided_by_rule={}) if item.id == "ownership"
    ]
    assert stale_assessment.status == "FAIL" and not stale_assessment.evaluation_proven


def test_missing_canonical_default_owner_is_unknown_not_a_guess(tmp_path):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes

    contract = _contract(
        {
            "mode": "confined",
            "value_owner": "sample.defaults.FALLBACK_REGION",
            "parameters": ["sample.consumer.normalize.region"],
            "roles": ["parameter_default"],
        }
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/consumer.py": "def normalize(region=0): return region\n",
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    assert not [
        item for item in result.observation.records("violations") if item.kind == "source_ownership"
    ]
    assert any(
        item.kind == "source_ownership_limit" for item in result.observation.records("unknowns")
    )
    saved = tmp_path / "architecture.json"
    saved.write_bytes(canonical_report_bytes(result.observation))
    [assessment] = [
        item for item in run_saved_report(saved).rule_assessments if item.id == "ownership"
    ]
    assert assessment.status == "UNKNOWN"


def test_alias_reads_resolve_to_the_owned_symbol_without_matching_shadowing(tmp_path):
    from archkeel.ir.decisions import rule_assessments

    contract = _contract(
        {
            "mode": "retired",
            "symbols": ["sample.storage.retired_cursor"],
            "roles": ["read"],
        }
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/storage.py": "def retired_cursor(): return 0\n",
            "sample/consumer.py": (
                "from .storage import retired_cursor as cursor\n"
                "def use(): return cursor\n"
                "def shadow():\n    cursor = 0\n    return cursor\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = [
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.id == "ownership"
    ]
    assert assessment.status == "FAIL" and assessment.count == 1


def test_same_named_local_declarations_cannot_exchange_read_evidence(tmp_path):
    import copy

    from archkeel.ir.codec import observation_payload, parse_observation

    contract = _contract(
        {"mode": "retired", "symbols": ["sample.consumer.first.value"], "roles": ["read"]}
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/consumer.py": (
                "def first():\n    value = 1\n    return value\n"
                "def second():\n    value = 2\n    return value\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    changed = copy.deepcopy(observation_payload(result.observation))
    references = changed["references"]
    first = next(
        record
        for record in references
        if record["kind"] == "value_reference"
        and record["data"].get("local_source_binding") is True
        and record["data"].get("source_scope") == "sample.consumer.first"
    )
    second_anchor = next(
        record
        for record in references
        if record["kind"] == "source_role"
        and record["data"].get("role") == "definition"
        and record["data"].get("canonical_name") == "sample.consumer.second.value"
    )
    first["data"]["targets"] = ["sample.consumer.second.value"]
    first["data"]["declaration_id"] = second_anchor["data"]["declaration_id"]
    with pytest.raises(ValueError, match="lexical scope"):
        parse_observation(changed)

    changed_anchor = copy.deepcopy(observation_payload(result.observation))
    definitions = [
        record
        for record in changed_anchor["references"]
        if record["kind"] == "source_role" and record["data"].get("role") == "definition"
    ]
    first_definition = next(
        record
        for record in definitions
        if record["data"].get("canonical_name") == "sample.consumer.first.value"
    )
    second_definition = next(
        record
        for record in definitions
        if record["data"].get("canonical_name") == "sample.consumer.second.value"
    )
    first_definition["data"]["canonical_name"] = "sample.consumer.second.value"
    first_definition["data"]["targets"] = ["sample.consumer.second.value"]
    first_definition["data"]["declaration_id"] = second_definition["data"]["declaration_id"]
    with pytest.raises(ValueError, match="lexical declaration owner"):
        parse_observation(changed_anchor)


def test_dictionary_callable_alias_and_lambda_transfer_are_detected(tmp_path):
    from archkeel.ir.decisions import rule_assessments

    contract = _contract(
        {
            "mode": "confined",
            "owner": "sample.storage",
            "symbols": ["random.random"],
            "roles": ["value_transfer"],
        }
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/consumer.py": (
                "from random import random as raw_draw\n"
                'DIRECT = {"draw": raw_draw}\n'
                'WRAPPED = {"draw": lambda: raw_draw()}\n'
                'HELPER = {"draw": wrap(raw_draw)}\n'
            ),
            "sample/storage.py": "",
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = [
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.id == "ownership"
    ]
    assert assessment.status == "FAIL" and assessment.count == 2
    assert any(
        item.kind == "source_ownership_limit" for item in result.observation.records("unknowns")
    )


def test_mounted_ownership_scope_does_not_leak_to_sibling_modules(tmp_path):
    from archkeel.ir.decisions import rule_assessments

    contract = _contract(
        {
            "mode": "retired",
            "symbols": ["sample.old"],
            "roles": ["definition"],
        }
    )
    contract["rules"] = []
    contract["components"] = [
        _component("core", ["sample.core"], inside="inside.json"),
        _component("outside", ["sample.outside"]),
    ]
    inside = {
        "schema_version": "3.8.0",
        "components": [_component("consumer", ["sample.core.consumer"])],
        "rules": [
            _source_rule(
                id="inside_ownership",
                source="sample.core.consumer",
                mode="retired",
                symbols=["sample.core.consumer.retired_cursor"],
                roles=["definition"],
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "inside.json": json.dumps(inside),
            "sample/__init__.py": "",
            "sample/core/__init__.py": "",
            "sample/core/consumer.py": "retired_cursor = 1\n",
            "sample/outside/__init__.py": "",
            "sample/outside/consumer.py": "retired_cursor = 1\n",
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = [
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.id == "core:inside_ownership"
    ]
    assert assessment.status == "FAIL" and assessment.count == 1
