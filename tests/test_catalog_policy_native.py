# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Catalog arguments and required source reads use admitted enum declarations."""

import copy
import json
from pathlib import Path

import pytest

from archkeel.check.evaluation.rules import profile_failures
from archkeel.cli.observe import observe
from archkeel.ir.codec import parse_contract
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.model import module_references
from archkeel.ir.profiles import DART, TYPESCRIPT
from archkeel.ir.renames import renamed_contract


def _raw(*rules):
    return {
        "schema_version": "3.14.0",
        "components": [],
        "rules": [
            {
                "id": f"CATALOG-{index}",
                "kind": rule["kind"],
                "rationale": "Use only canonical catalog entries.",
                "provenance": ["docs/architecture/catalog.md"],
                "decided_by": "architect",
                **rule,
            }
            for index, rule in enumerate(rules)
        ],
    }


def _run(
    tmp_path: Path,
    *,
    caller: str,
    rules,
    catalog_suffix: str = "",
    extra_files: dict[str, str] | None = None,
    mounted: bool = False,
):
    config = (
        "from enum import StrEnum\n"
        "class OptionKey(StrEnum):\n"
        "    PAGE_SIZE = 'page_size'\n"
        "    RETIRED = 'retired'\n"
        "class ExtraKey(StrEnum):\n"
        "    NEW = 'new'\n"
        "class ConstantKey:\n"
        "    API_TOKEN = 'api_token'\n"
        "__all__ = ['OptionKey', 'read_option']\n"
        "def read_option(key: str) -> None: pass\n" + catalog_suffix
    )
    contract = _raw(*rules)
    if mounted:
        contract["components"] = [
            {
                "id": "COMP-CONSUMER",
                "label": "consumer",
                "role": "component",
                "packages": ["sample.consumer"],
                "responsibilities": [],
                "forbidden_responsibilities": [],
                "provenance": ["docs/architecture/catalog.md"],
            }
        ]
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "docs/architecture/catalog.md": "Synthetic catalog decision.\n",
        "contract.json": json.dumps(
            {
                "schema_version": "3.14.0",
                "components": [
                    {
                        "id": "COMP-SAMPLE",
                        "label": "sample",
                        "role": "component",
                        "packages": ["sample.consumer"],
                        "responsibilities": [],
                        "forbidden_responsibilities": [],
                        "provenance": ["docs/architecture/catalog.md"],
                        "inside": "inside.json",
                    }
                ],
                "rules": [],
            }
            if mounted
            else contract
        ),
        "sample/__init__.py": "",
        "sample/catalog.py": config,
        "sample/consumer.py": caller,
        **(extra_files or {}),
    }
    if mounted:
        files["inside.json"] = json.dumps(contract)
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    result = observe(
        tmp_path,
        roots=("sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert result.observation is not None, result.diagnostics
    return result, rule_assessments(result.observation, undecided_by_rule={})


def _argument(source="sample.consumer"):
    return {
        "kind": "catalog_argument",
        "source": source,
        "target": "sample.consumer.read_option",
        "parameter": "key",
        "catalog": "sample.catalog.OptionKey",
    }


def _use(source="sample.consumer", member="PAGE_SIZE", *, target=None, parameter=None):
    rule = {
        "kind": "catalog_use",
        "source": source,
        "catalog": "sample.catalog.OptionKey",
        "member": member,
    }
    if target is not None:
        rule["target"] = target
    if parameter is not None:
        rule["parameter"] = parameter
    return rule


def _read_option_use(member="PAGE_SIZE"):
    return _use(target="sample.consumer.read_option", parameter="key", member=member)


@pytest.mark.parametrize("profile", [DART, TYPESCRIPT])
def test_catalog_rules_are_rejected_by_non_python_profiles(profile):
    contract = parse_contract(_raw(_argument(), _use()))

    failures = profile_failures(contract, profile, ())

    assert {item["rule_ids"][0] for item in failures} == {"CATALOG-0", "CATALOG-1"}
    assert all("rule kind catalog_" in item["title"] for item in failures)


def test_catalog_selector_references_are_renamed_as_canonical_module_references():
    contract = parse_contract(
        _raw(
            {
                **_argument("sample.consumer"),
                "catalog": "sample.catalog.OptionKey",
                "overlays": ["sample.catalog.ExtraKey"],
            },
            {
                **_use("sample.consumer"),
                "overlays": ["sample.catalog.ExtraKey"],
                "target": "sample.consumer.read_option",
                "parameter": "key",
            },
        )
    )
    references = {item.pointer: item for item in module_references(contract)}

    assert references["/rules/0/source"].value == "sample.consumer"
    assert references["/rules/0/target"].value == "sample.consumer.read_option"
    assert references["/rules/0/catalog"].value == "sample.catalog.OptionKey"
    assert references["/rules/0/overlays/0"].value == "sample.catalog.ExtraKey"
    assert references["/rules/1/source"].value == "sample.consumer"
    assert references["/rules/1/catalog"].value == "sample.catalog.OptionKey"
    assert references["/rules/1/overlays/0"].value == "sample.catalog.ExtraKey"
    assert references["/rules/1/target"].value == "sample.consumer.read_option"
    assert all(item.held for item in references.values())

    renamed = renamed_contract(contract, {"sample": "renamed"})
    moved = {item.pointer: item.value for item in module_references(renamed)}
    assert moved["/rules/0/source"] == "renamed.consumer"
    assert moved["/rules/0/target"] == "renamed.consumer.read_option"
    assert moved["/rules/0/catalog"] == "renamed.catalog.OptionKey"
    assert moved["/rules/0/overlays/0"] == "renamed.catalog.ExtraKey"


@pytest.mark.parametrize(
    "fields",
    [
        {"target": "sample.consumer.read_option"},
        {"parameter": "key"},
    ],
)
def test_catalog_use_read_operation_selectors_must_be_paired(fields):
    with pytest.raises(ValueError, match="target and .*parameter must be provided together"):
        parse_contract(_raw({**_use(), **fields}))


def test_python_decoded_2_9_schema_keeps_source_role_binding_proofs():
    from test_result_schema import _validator

    references = _validator("command-result-9.0.schema.json").evolve(
        schema={
            "$ref": ("urn:archkeel:architecture-ir:python-decoded:2.9.0#/properties/references")
        }
    )
    record = {
        "id": "REF-example",
        "evidence_class": "FACT",
        "area": "references",
        "kind": "source_role",
        "title": "Source definition role",
        "subjects": [],
        "evidence_ids": ["EVD-example"],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {
            "source_scope": "sample.consumer",
            "source_module": "sample.consumer",
            "expression": "cursor",
            "status": "resolved",
            "targets": [],
            "use": "source_role",
            "role": "definition",
            "canonical_name": "sample.consumer.cursor",
            "declaration_id": "DECL-example",
            "declaration_role": "definition",
            "declaration_evidence_ids": ["EVD-declaration"],
            "declaration_status": "resolved",
            "local_source_binding": True,
            "column": 0,
        },
    }

    assert references.is_valid([record])
    unresolved_source_role = copy.deepcopy(record)
    unresolved_source_role["data"]["status"] = "unresolved"
    assert references.is_valid([unresolved_source_role])

    unresolved_declaration = copy.deepcopy(record)
    unresolved_declaration["data"]["declaration_status"] = "unresolved"
    assert not references.is_valid([unresolved_declaration])

    invalid_default = copy.deepcopy(record)
    invalid_default["data"]["role"] = "parameter_default"
    assert not references.is_valid([invalid_default])
    invalid_default["data"]["parameter"] = "cursor"
    invalid_default["data"]["expression_kind"] = "reference"
    assert references.is_valid([invalid_default])

    transferred_reference = copy.deepcopy(record)
    transferred_reference["kind"] = "value_reference"
    transferred_reference["data"].update(
        {
            "use": "value",
            "reference_context": "value",
            "transfer_kind": "dictionary_value",
        }
    )
    assert not references.is_valid([transferred_reference])


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize(
    "call",
    [
        'read_option(\n        "page_size"\n    )',
        'unknown_operation(\n        "page_size"\n    )',
    ],
)
def test_selected_multiline_and_unbound_calls_remain_unknown(tmp_path, mounted, call):
    _, rows = _run(
        tmp_path,
        mounted=mounted,
        caller=(f"def read_option(key: str) -> None: pass\ndef consume():\n    {call}\n"),
        rules=[_argument()],
    )
    assert rows[0].status == "UNKNOWN"


@pytest.mark.parametrize(
    ("caller", "expected"),
    [
        pytest.param(
            "from .catalog import OptionKey\ndef consume():\n    print(OptionKey.PAGE_SIZE)\n",
            "PASS",
        ),
        pytest.param(
            "from typing import TYPE_CHECKING\n"
            "from .catalog import OptionKey as Keys\n"
            "if TYPE_CHECKING:\n    TYPE_KEY = Keys.PAGE_SIZE\n"
            "def consume():\n    pass\n",
            "PASS",
        ),
        (
            "from .catalog import OptionKey\ndef consume():\n    pass\n",
            "FAIL",
        ),
        (
            "from .catalog import OptionKey\ndef consume():\n"
            '    """OptionKey.PAGE_SIZE"""\n    pass\n',
            "FAIL",
        ),
        (
            "from .catalog import OptionKey\ndef consume(value: OptionKey.PAGE_SIZE):\n    pass\n",
            "FAIL",
        ),
        pytest.param(
            "from .catalog import OptionKey\ndef consume():\n    selected: OptionKey.PAGE_SIZE\n",
            "FAIL",
        ),
        (
            "from .catalog import OptionKey\ndef consume():\n    # OptionKey.PAGE_SIZE\n    pass\n",
            "FAIL",
        ),
    ],
)
def test_selected_catalog_entry_requires_a_genuine_source_read(tmp_path, caller, expected):
    _, rows = _run(tmp_path, caller=caller, rules=[_use()])
    assert rows[0].status == expected


# The reference collector reads the prefix of a chain it does not resolve (#731).


# A class read is not a member read, also when its alias has the name of a member.


# A member read through a module that imports the enum is a member read (#731).
