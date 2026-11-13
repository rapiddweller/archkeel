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


def _contract(rule, version="3.12.0"):
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


def test_value_owner_module_rename_preserves_the_qualified_constant_name():
    from archkeel.ir.renames import renamed_contract

    contract = parse_contract(
        _contract(
            {
                "mode": "confined",
                "value_owner": "sample.defaults.FALLBACK_REGION",
                "parameters": ["sample.consumer.normalize.region"],
                "roles": ["parameter_default"],
            }
        )
    )

    moved = renamed_contract(contract, {"sample.defaults": "sample.settings"})

    assert moved.rules[0].value_owner == "sample.settings.FALLBACK_REGION"


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


def test_source_ownership_requires_contract_3_12():
    with pytest.raises(
        ValueError, match="source_ownership requires contract schema_version 3.12.0"
    ):
        parse_contract(
            _contract(
                {"mode": "retired", "symbols": ["sample.old"], "roles": ["definition"]}, "3.11.0"
            )
        )
    from dataclasses import replace

    from archkeel.ir.codec import contract_bytes
    from archkeel.ir.contract_version import ContractVersion

    current = parse_contract(
        _contract({"mode": "retired", "symbols": ["sample.old"], "roles": ["definition"]})
    )
    with pytest.raises(
        ValueError, match="source_ownership requires contract schema_version 3.12.0"
    ):
        contract_bytes(replace(current, schema_version=ContractVersion.V3_11))


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


def _observe_tree(tmp_path, files, contract, *, roots=("sample",)):
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
        roots=roots,
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )


def test_unknown_reference_context_cannot_certify_a_source_read():
    from archkeel.check.evaluation.rules import source_ownership_unknowns

    [rule] = parse_contract(
        _contract(
            {
                "mode": "retired",
                "symbols": ["sample.consumer.PAGE_SIZE"],
                "roles": ["read"],
            }
        )
    ).rules
    reference = {
        "id": "REF-1",
        "evidence_class": "FACT",
        "area": "call_hierarchy",
        "kind": "attribute_reference",
        "title": "Reference PAGE_SIZE",
        "subjects": ["sample.consumer"],
        "evidence_ids": ["E-1"],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {
            "source_module": "sample.consumer",
            "source_scope": "sample.consumer",
            "expression": "PAGE_SIZE",
            "reference_context": "unknown",
            "status": "resolved",
            "targets": ["sample.consumer.PAGE_SIZE"],
        },
    }
    [unknown] = source_ownership_unknowns([reference], [], [rule], frozenset({"sample.consumer"}))
    assert unknown["kind"] == "source_ownership_limit"
    assert unknown["evidence_ids"] == ["E-1"]


# The reference collector reads a write target and the prefix of an unresolved chain (#731).
