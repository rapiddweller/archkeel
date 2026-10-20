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
    assert result.observation is not None, [
        (item.subject, item.unknown_claim, item.remedy) for item in result.diagnostics
    ]
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
    assert {item.data.get("role") for item in role_facts} >= {"write", "delete"}
    assert any(
        item.data.get("qualified_name") == "sample.consumer.retired_cursor"
        and item.data.get("record_kind") == "static_constant"
        for item in result.observation.records("symbols")
    )
    assert any(
        item.kind == "value_reference"
        and "sample.consumer.retired_cursor" in item.data.get("targets", ())
        for item in result.observation.records("references")
    )


def test_unread_local_definition_is_retained_as_unknown_candidate(tmp_path):
    from archkeel.ir.decisions import rule_assessments, unknown_positions_by_rule

    contract = _contract(
        {
            "mode": "retired",
            "symbols": ["sample.consumer.normalize.cursor"],
            "roles": ["definition"],
        }
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/consumer.py": (
                "def normalize(flag):\n    if flag:\n        cursor = 0\n    return None\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    assert any(
        item.kind == "source_role"
        and item.data.get("role") == "definition"
        and item.data.get("canonical_name") == "sample.consumer.normalize.cursor"
        and item.data.get("status") != "resolved"
        for item in result.observation.records("references")
    )
    [assessment] = [
        item
        for item in rule_assessments(
            result.observation,
            undecided_by_rule=unknown_positions_by_rule(result.observation),
        )
        if item.id == "ownership"
    ]
    assert assessment.status.value == "UNKNOWN", [
        (item.kind, item.data.entries) for item in result.observation.records("unknowns")
    ]


def test_dynamic_module_binding_is_a_real_definition_anchor(tmp_path):
    from archkeel.ir.decisions import rule_assessments

    contract = _contract(
        {
            "mode": "retired",
            "symbols": ["sample.consumer.TARGETS"],
            "roles": ["definition"],
        }
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/consumer.py": "TARGETS = build_targets()\n",
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
    assert assessment.count == 1


def test_annotation_references_are_typed_across_module_class_and_local_scopes(tmp_path):
    contract = _contract(
        {
            "mode": "retired",
            "symbols": ["sample.consumer.OptionKey.PAGE_SIZE"],
            "roles": ["read"],
        }
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/consumer.py": (
                "from enum import Enum\n"
                "class OptionKey(Enum): PAGE_SIZE = 1\n"
                "module_value: OptionKey.PAGE_SIZE\n"
                "class Holder:\n"
                "    class_value: OptionKey.PAGE_SIZE\n"
                "    def read(self, selected: OptionKey.PAGE_SIZE) -> OptionKey.PAGE_SIZE:\n"
                "        local: OptionKey.PAGE_SIZE\n"
                "        return selected\n"
                "value = OptionKey.PAGE_SIZE\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    references = [
        item
        for item in result.observation.records("references")
        if item.kind in {"value_reference", "attribute_reference"}
        and item.data.get("expression") == "OptionKey.PAGE_SIZE"
    ]
    assert references
    assert {item.data.get("reference_context") for item in references} == {"annotation", "value"}
    annotations = [
        item for item in references if item.data.get("reference_context") == "annotation"
    ]
    assert len(annotations) >= 5
    assert all(item.data.get("reference_context") == "annotation" for item in annotations)


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
    assert result.observation is not None, [item.unknown_claim for item in result.diagnostics]
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


def test_parameter_default_cannot_borrow_another_callable_source_witness(tmp_path):
    import copy

    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload, parse_observation
    from archkeel.ir.facts import stable_id

    contract = _contract(
        {
            "mode": "confined",
            "value_owner": "sample.defaults.FALLBACK_REGION",
            "parameters": [
                "sample.consumer.normalize.region",
                "sample.consumer.bad.region",
            ],
            "roles": ["parameter_default"],
        }
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/defaults.py": 'FALLBACK_REGION = "ZZ"\n',
            "sample/consumer.py": (
                "from .defaults import FALLBACK_REGION\n"
                "def normalize(region=FALLBACK_REGION): return region\n"
                'def bad(region="ZZ"): return region\n'
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    changed = copy.deepcopy(observation_payload(result.observation))
    roles = [
        item
        for item in changed["references"]
        if item["kind"] == "source_role" and item["data"].get("role") == "parameter_default"
    ]
    donor = next(item for item in roles if item["data"].get("expression_kind") == "reference")
    recipient = next(item for item in roles if item["data"].get("expression_kind") == "literal")
    recipient["evidence_ids"] = donor["evidence_ids"]
    recipient["data"].pop("constant", None)
    for field in (
        "expression_kind",
        "expression",
        "status",
        "targets",
        "line",
        "column",
        "end_line",
        "end_column",
    ):
        recipient["data"][field] = donor["data"][field]
    source = next(item for item in changed["evidence"] if item["id"] == donor["evidence_ids"][0])
    recipient["id"] = stable_id(
        "SOURCE-ROLE",
        source["file"],
        recipient["data"]["line"],
        recipient["data"]["column"],
        recipient["data"]["end_line"],
        recipient["data"]["end_column"],
        recipient["data"]["role"],
        recipient["data"]["canonical_name"],
    )
    with pytest.raises(ValueError, match="parameter default source witness"):
        parse_observation(changed)
    saved = tmp_path / "tampered.json"
    saved.write_bytes(canonical_report_bytes(changed))
    replay = run_saved_report(saved)
    assert any(
        "parameter default source witness" in item.unknown_claim for item in replay.diagnostics
    )


def test_multiline_parameter_default_remains_an_unsupported_unknown(tmp_path):
    from archkeel.ir.decisions import rule_assessments

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
            "sample/defaults.py": 'FALLBACK_REGION = "ZZ"\n',
            "sample/consumer.py": (
                "from .defaults import FALLBACK_REGION\n"
                "def normalize(\n"
                "    region=FALLBACK_REGION,\n"
                "):\n"
                "    return region\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    roles = [
        item
        for item in result.observation.records("references")
        if item.kind == "source_role" and item.data.get("role") == "parameter_default"
    ]
    assert len(roles) == 1
    assert roles[0].data.get("expression_kind") == "unsupported"
    assert roles[0].data.get("status") != "resolved"
    unknowns = [
        item
        for item in result.observation.records("unknowns")
        if item.kind == "source_ownership_limit" and "ownership" in item.rule_ids
    ]
    assert len(unknowns) == 1
    [assessment] = [
        item
        for item in rule_assessments(result.observation, undecided_by_rule={"ownership": 1})
        if item.id == "ownership"
    ]
    assert assessment.status.value == "UNKNOWN"


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


@pytest.mark.parametrize(
    ("representation", "mutation"),
    [
        ("json", "delete"),
        ("json", "change"),
        ("json", "relocate"),
        ("columnar", "delete"),
        ("columnar", "change"),
        ("columnar", "relocate"),
    ],
)
def test_source_ownership_receipt_binds_fail_and_unknown_results(
    tmp_path, representation, mutation
):
    import copy

    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import (
        encode_canonical_model,
        observation_payload,
        parse_observation,
    )
    from archkeel.ir.decisions import rule_assessments, unknown_positions_by_rule

    contract = _contract(
        {
            "mode": "retired",
            "symbols": [
                "sample.consumer.retired_cursor",
                "sample.consumer.normalize.cursor",
            ],
            "roles": ["definition"],
        }
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/consumer.py": (
                "retired_cursor = 0\n"
                "def normalize(flag):\n    if flag:\n        cursor = 0\n    return None\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    original = observation_payload(result.observation)
    [assessment] = [
        row
        for row in rule_assessments(
            result.observation,
            undecided_by_rule=unknown_positions_by_rule(result.observation),
        )
        if row.id == "ownership"
    ]
    assert assessment.status.value == "FAIL" and assessment.evaluation_proven
    assert any(item.kind == "source_ownership" for item in result.observation.records("violations"))
    assert any(
        item.kind == "source_ownership_limit" for item in result.observation.records("unknowns")
    )

    altered = copy.deepcopy(original)
    if mutation == "delete":
        altered["violations"].clear()
    elif mutation == "change":
        altered["violations"][0]["title"] += " changed"
    else:
        moved = altered["violations"].pop()
        moved["evidence_class"] = "UNKNOWN"
        altered["unknowns"].append(moved)

    if representation == "json":
        observation = parse_observation(altered)
        [replayed] = [
            row
            for row in rule_assessments(
                observation, undecided_by_rule=unknown_positions_by_rule(observation)
            )
            if row.id == "ownership"
        ]
    else:
        saved = tmp_path / "altered-columnar.json"
        saved.write_text(json.dumps(encode_canonical_model(altered)))
        [replayed] = [
            row for row in run_saved_report(saved).rule_assessments if row.id == "ownership"
        ]
    assert replayed.status.value in {"FAIL", "UNKNOWN"} and not replayed.evaluation_proven


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
    assert assessment.status == "FAIL" and assessment.count == 1 and assessment.evaluation_proven


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
        if record["kind"] == "value_reference"
        and record["data"].get("declaration_role") == "definition"
        and record["data"].get("targets") == ["sample.consumer.second.value"]
    )
    first["data"]["targets"] = ["sample.consumer.second.value"]
    first["data"]["declaration_id"] = second_anchor["data"]["declaration_id"]
    with pytest.raises(ValueError, match="declaration"):
        parse_observation(changed)

    changed_anchor = copy.deepcopy(observation_payload(result.observation))
    first_anchor = next(
        record
        for record in changed_anchor["references"]
        if record["kind"] == "value_reference"
        and record["data"].get("declaration_role") == "definition"
        and record["data"].get("targets") == ["sample.consumer.first.value"]
    )
    second_anchor = next(
        record
        for record in changed_anchor["references"]
        if record["kind"] == "value_reference"
        and record["data"].get("declaration_role") == "definition"
        and record["data"].get("targets") == ["sample.consumer.second.value"]
    )
    assert (
        first_anchor["data"]["declaration_evidence_ids"]
        != second_anchor["data"]["declaration_evidence_ids"]
    )
    first_anchor["data"]["declaration_evidence_ids"] = second_anchor["data"][
        "declaration_evidence_ids"
    ]
    with pytest.raises(ValueError, match="local definition witness"):
        parse_observation(changed_anchor)


def test_module_comprehension_local_uses_the_module_declaration_anchor(tmp_path):
    contract = _contract(
        {"mode": "retired", "symbols": ["sample.consumer.MAPPING"], "roles": ["definition"]}
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/consumer.py": (
                "MAPPING = {value: position for position, value in enumerate(VALUES)}\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics


def test_default_and_fallback_targets_need_matching_reference_evidence(tmp_path):
    import copy

    from archkeel.ir.codec import observation_payload, parse_observation

    contract = _contract(
        {
            "mode": "confined",
            "value_owner": "sample.defaults.FALLBACK_REGION",
            "parameters": ["sample.consumer.normalize.region"],
            "roles": ["parameter_default", "fallback"],
        }
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/defaults.py": ("FALLBACK_REGION = 'EU'\n"),
            "sample/consumer.py": (
                "from sample.defaults import FALLBACK_REGION\n"
                "def normalize(region=FALLBACK_REGION):\n"
                "    return region or 'ZZ'\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, [
        (item.subject, item.unknown_claim, item.remedy) for item in result.diagnostics
    ]
    changed = copy.deepcopy(observation_payload(result.observation))
    role = next(
        record
        for record in changed["references"]
        if record["kind"] == "source_role" and record["data"].get("role") == "fallback"
    )
    role["data"].update(
        expression_kind="reference",
        expression="FALLBACK_REGION",
        status="resolved",
        targets=["sample.defaults.FALLBACK_REGION"],
    )
    with pytest.raises(ValueError, match="source role target lacks matching reference evidence"):
        parse_observation(changed)


def test_source_ownership_schemas_describe_current_contract_and_saved_observation(tmp_path):
    import copy
    import json

    from jsonschema import Draft202012Validator, ValidationError
    from referencing import Registry, Resource

    from archkeel.ir.codec import observation_payload, parse_observation

    schemas = [json.loads(path.read_bytes()) for path in (ROOT / "schema").glob("*.json")]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    contract = _contract(
        {
            "mode": "retired",
            "symbols": ["sample.consumer.old"],
            "roles": ["definition", "read", "write", "delete"],
        }
    )
    Draft202012Validator(
        json.loads((ROOT / "schema/architecture-contract-3.12.schema.json").read_bytes()),
        registry=registry,
    ).validate(contract)
    with pytest.raises(ValidationError):
        Draft202012Validator(
            json.loads((ROOT / "schema/architecture-contract-3.8.schema.json").read_bytes()),
            registry=registry,
        ).validate(contract)
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/consumer.py": "old = 1\ndef read(): return old\n",
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    observation = observation_payload(result.observation)
    Draft202012Validator(
        json.loads((ROOT / "schema/architecture-ir-decoded-2.8.schema.json").read_bytes()),
        registry=registry,
    ).validate(observation)
    Draft202012Validator.check_schema(
        json.loads((ROOT / "schema/command-result-9.0.schema.json").read_bytes())
    )
    older = copy.deepcopy(observation)
    older["schema_version"] = "2.6.0"
    with pytest.raises(
        ValueError,
        match=(
            "(source_role records require|source_ownership requires) "
            "observation schema_version 2.7.0"
        ),
    ):
        parse_observation(older)
    old_context = copy.deepcopy(observation)
    old_context["schema_version"] = "2.6.0"
    old_context["declarations"] = [
        item for item in old_context["declarations"] if item["kind"] != "source_ownership"
    ]
    old_context["references"] = [
        item for item in old_context["references"] if item["kind"] != "source_role"
    ]
    with pytest.raises(
        ValueError, match="reference_context requires observation schema_version 2.7.0"
    ):
        parse_observation(old_context)


def test_builtin_value_without_source_declaration_remains_unknown(tmp_path):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes

    contract = _contract(
        {
            "mode": "confined",
            "owner": "sample.consumer",
            "symbols": ["builtins.list"],
            "roles": ["value_transfer"],
        }
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {"sample/__init__.py": "", "sample/consumer.py": 'FUNCTIONS = {"copy": list}\n'},
        contract,
    )
    assert result.observation is not None, result.diagnostics
    roles = [
        (item.data.get("role"), item.data.get("canonical_name"), item.data.get("status"))
        for item in result.observation.records("references")
        if item.kind == "source_role"
    ]
    assert roles
    assert any(
        item.kind == "source_ownership_limit" for item in result.observation.records("unknowns")
    )
    saved = tmp_path / "architecture.json"
    saved.write_bytes(canonical_report_bytes(result.observation))
    [assessment] = [
        item for item in run_saved_report(saved).rule_assessments if item.id == "ownership"
    ]
    assert assessment.status == "UNKNOWN", roles


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
        "schema_version": "3.12.0",
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
    assert assessment.status == "FAIL" and assessment.count == 1 and assessment.evaluation_proven


def test_mounted_source_receipt_cannot_claim_sibling_scope_with_recomputed_binding(tmp_path):
    import copy

    from archkeel.ir.codec import observation_payload, parse_observation
    from archkeel.ir.decisions import (
        dependency_binding_id,
        rule_assessments,
        rule_evaluation_binding_id,
    )

    contract = _contract({"mode": "retired", "symbols": ["sample.old"], "roles": ["definition"]})
    contract["rules"] = []
    contract["components"] = [
        _component("core", ["sample.core"], inside="inside.json"),
        _component("outside", ["sample.outside"]),
    ]
    inside = {
        "schema_version": "3.12.0",
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
    changed = copy.deepcopy(observation_payload(result.observation))
    [receipt] = [
        item
        for item in changed["scope_observations"]
        if item["kind"] == "rule_evaluation" and item["rule_ids"] == ["core:inside_ownership"]
    ]
    receipt["subjects"] = ["sample.outside.consumer"]
    receipt["data"]["source_ownership_scope_proof"]["source_modules"] = ["sample.outside.consumer"]

    forged = parse_observation(changed)
    [forged_receipt] = [
        item
        for item in forged.records("scope_observations")
        if item.kind == "rule_evaluation" and item.rule_ids == ("core:inside_ownership",)
    ]
    proof = receipt["data"]["source_ownership_scope_proof"]
    proof["binding_id"] = rule_evaluation_binding_id(
        dependency_binding_id(
            forged.sections,
            forged.coverage.failures,
            forged.evidence,
            include_source_ownership=True,
        ),
        forged_receipt,
        forged.schema_version,
    )
    replayed = parse_observation(changed)
    [assessment] = [
        item
        for item in rule_assessments(replayed, undecided_by_rule={})
        if item.id == "core:inside_ownership"
    ]
    assert assessment.status == "FAIL" and not assessment.evaluation_proven


def test_partial_root_scan_cannot_prove_complete_source_ownership(tmp_path):
    from archkeel.ir.decisions import rule_assessments

    contract = _contract(
        {
            "mode": "retired",
            "symbols": ["sample.core.retired_cursor"],
            "roles": ["definition"],
        }
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/safe/__init__.py": "other = 1\n",
            "sample/core/__init__.py": "",
            "sample/core/consumer.py": "retired_cursor = 1\n",
        },
        contract,
        roots=("sample/safe",),
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = [
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.id == "ownership"
    ]
    assert assessment.status == "UNKNOWN" and not assessment.evaluation_proven


@pytest.mark.parametrize("layout_root", ["src", "src/sample"])
def test_src_layout_root_source_ownership_replays_as_proven(tmp_path, layout_root):
    import json

    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload
    from archkeel.ir.decisions import rule_assessments

    contract = _contract(
        {"mode": "retired", "symbols": ["sample.consumer.retired_cursor"], "roles": ["definition"]}
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "src/sample/__init__.py": "",
            "src/sample/consumer.py": "active_cursor = 1\n",
            "src/sample/safe.py": "active_cursor = 2\n",
        },
        contract,
        roots=(layout_root,),
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = [
        row
        for row in rule_assessments(result.observation, undecided_by_rule={})
        if row.id == "ownership"
    ]
    assert assessment.status == "PASS" and assessment.evaluation_proven

    ordinary = tmp_path / "ordinary.json"
    ordinary.write_text(json.dumps(observation_payload(result.observation)))
    [ordinary_assessment] = [
        row for row in run_saved_report(ordinary).rule_assessments if row.id == "ownership"
    ]
    columnar = tmp_path / "columnar.json"
    columnar.write_bytes(canonical_report_bytes(result.observation))
    [columnar_assessment] = [
        row for row in run_saved_report(columnar).rule_assessments if row.id == "ownership"
    ]
    assert ordinary_assessment == columnar_assessment == assessment


def test_src_layout_partial_root_scan_stays_unknown_on_replay(tmp_path):
    import json

    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload
    from archkeel.ir.decisions import rule_assessments

    contract = _contract(
        {"mode": "retired", "symbols": ["sample.consumer.retired_cursor"], "roles": ["definition"]}
    )
    contract["components"] = [_component("all", ["sample"])]
    result = _observe_tree(
        tmp_path,
        {
            "src/sample/__init__.py": "",
            "src/sample/consumer.py": "active_cursor = 1\n",
            "src/sample/safe/__init__.py": "",
            "src/sample/safe/other.py": "retired_cursor = 2\n",
        },
        contract,
        roots=("src/sample/safe",),
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = [
        row
        for row in rule_assessments(result.observation, undecided_by_rule={})
        if row.id == "ownership"
    ]
    assert assessment.status == "UNKNOWN" and not assessment.evaluation_proven
    ordinary = tmp_path / "ordinary.json"
    ordinary.write_text(json.dumps(observation_payload(result.observation)))
    columnar = tmp_path / "columnar.json"
    columnar.write_bytes(canonical_report_bytes(result.observation))
    for saved in (ordinary, columnar):
        [replayed] = [
            row for row in run_saved_report(saved).rule_assessments if row.id == "ownership"
        ]
        assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


def test_src_layout_mounted_partial_root_keeps_sibling_unknown(tmp_path):
    import json

    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload
    from archkeel.ir.decisions import rule_assessments

    contract = _contract(
        {
            "mode": "retired",
            "symbols": ["sample.core.consumer.retired_cursor"],
            "roles": ["definition"],
        }
    )
    contract["rules"] = []
    contract["components"] = [
        _component("core", ["sample.core"], inside="inside.json"),
        _component("outside", ["sample.outside"]),
    ]
    inside = {
        "schema_version": "3.12.0",
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
            "src/sample/__init__.py": "",
            "src/sample/core/__init__.py": "",
            "src/sample/core/consumer.py": "active_cursor = 1\n",
            "src/sample/core/safe/__init__.py": "",
            "src/sample/core/safe/other.py": "retired_cursor = 2\n",
            "src/sample/outside/__init__.py": "",
        },
        contract,
        roots=("src/sample/core/safe",),
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = [
        row
        for row in rule_assessments(result.observation, undecided_by_rule={})
        if row.id == "core:inside_ownership"
    ]
    assert assessment.status == "UNKNOWN" and not assessment.evaluation_proven
    ordinary = tmp_path / "ordinary.json"
    ordinary.write_text(json.dumps(observation_payload(result.observation)))
    columnar = tmp_path / "columnar.json"
    columnar.write_bytes(canonical_report_bytes(result.observation))
    for saved in (ordinary, columnar):
        [replayed] = [
            row
            for row in run_saved_report(saved).rule_assessments
            if row.id == "core:inside_ownership"
        ]
        assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


def test_src_layout_mounted_source_ownership_replays_as_proven(tmp_path):
    import json

    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload
    from archkeel.ir.decisions import rule_assessments

    contract = _contract(
        {
            "mode": "retired",
            "symbols": ["sample.core.consumer.retired_cursor"],
            "roles": ["definition"],
        }
    )
    contract["rules"] = []
    contract["components"] = [_component("core", ["sample.core"], inside="inside.json")]
    inside = {
        "schema_version": "3.12.0",
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
            "src/sample/__init__.py": "",
            "src/sample/core/__init__.py": "",
            "src/sample/core/consumer.py": "active_cursor = 1\n",
            "src/sample/outside/__init__.py": "",
        },
        contract,
        roots=("src",),
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = [
        row
        for row in rule_assessments(result.observation, undecided_by_rule={})
        if row.id == "core:inside_ownership"
    ]
    assert assessment.status == "PASS" and assessment.evaluation_proven
    ordinary = tmp_path / "ordinary.json"
    ordinary.write_text(json.dumps(observation_payload(result.observation)))
    columnar = tmp_path / "columnar.json"
    columnar.write_bytes(canonical_report_bytes(result.observation))
    for saved in (ordinary, columnar):
        [replayed] = [
            row
            for row in run_saved_report(saved).rule_assessments
            if row.id == "core:inside_ownership"
        ]
        assert replayed == assessment
