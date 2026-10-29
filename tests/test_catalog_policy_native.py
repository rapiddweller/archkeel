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
from archkeel.ir.decisions import rule_assessments, unknown_positions_by_rule
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


def test_python_catalog_literal_values_are_versioned_in_observation_schemas(tmp_path):
    from test_result_schema import _validator

    from archkeel.ir.codec import observation_payload

    result, _ = _run(
        tmp_path,
        caller="def consume():\n    pass\n",
        rules=[],
    )
    raw = observation_payload(result.observation)
    raw["references"] = []
    owner = next(
        row
        for row in raw["symbols"]
        if row["data"].get("qualified_name") == "sample.catalog.OptionKey"
    )
    assert owner["data"]["attribute_declarations"][0]["literal_value"] == "page_size"
    validator = _validator("command-result-9.0.schema.json")
    current = validator.evolve(schema={"$ref": "urn:archkeel:architecture-ir:python-decoded:2.9.0"})
    assert current.is_valid(raw)

    historical = copy.deepcopy(raw)
    historical["schema_version"] = "2.8.0"
    old = validator.evolve(schema={"$ref": "urn:archkeel:architecture-ir:python-decoded:2.8.0"})
    assert not old.is_valid(historical)


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


def test_mounted_catalog_receipt_uses_only_its_physical_source_domain(tmp_path):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import observation_payload

    (tmp_path / "sample").mkdir()
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "docs/architecture").mkdir(parents=True)
    (tmp_path / "docs/architecture/catalog.md").write_text("Mounted catalog policy.\n")
    (tmp_path / "sample/__init__.py").write_text("")
    (tmp_path / "sample/consumer.py").write_text(
        "from enum import StrEnum\n"
        "class OptionKey(StrEnum):\n    PAGE_SIZE = 'page_size'\n"
        "def read_option(key: str) -> None: pass\n"
        "def consume():\n    read_option('page_size')\n"
    )
    (tmp_path / "sample/other.py").write_text(
        "def unrelated(value: str) -> None: pass\ndef outside_mount():\n    unrelated('outside')\n"
    )
    (tmp_path / "contract.json").write_text(
        json.dumps(
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
        )
    )
    (tmp_path / "inside.json").write_text(
        json.dumps(
            {
                **_raw(
                    {
                        "kind": "catalog_argument",
                        "source": "sample",
                        "source_match": "prefix",
                        "target": "sample.consumer.read_option",
                        "parameter": "key",
                        "catalog": "sample.consumer.OptionKey",
                    }
                ),
                "components": [
                    {
                        "id": "COMP-CONSUMER",
                        "label": "consumer",
                        "role": "component",
                        "packages": ["sample.consumer"],
                        "responsibilities": [],
                        "forbidden_responsibilities": [],
                        "provenance": ["docs/architecture/catalog.md"],
                    }
                ],
            }
        )
    )

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
    assessments = rule_assessments(result.observation, undecided_by_rule={})
    assessment = next(row for row in assessments if row.id.endswith("CATALOG-0"))
    assert assessment.status == "PASS" and assessment.evaluation_proven, (
        assessment,
        [
            (item.kind, item.title, item.subjects)
            for item in result.observation.records("violations") or ()
        ],
        [
            (item.kind, item.title, item.subjects)
            for item in result.observation.records("unknowns") or ()
        ],
    )
    receipt = next(
        record
        for record in result.observation.records("scope_observations") or ()
        if record.kind == "rule_evaluation"
        and len(record.rule_ids) == 1
        and record.rule_ids[0].endswith("CATALOG-0")
    )
    call_modules = {
        record.id: record.data.get("source_module")
        for record in result.observation.records("calls") or ()
    }
    selected_call_modules = {
        call_modules[item] for item in receipt.fact_ids if item in call_modules
    }
    assert selected_call_modules == {"sample.consumer"}

    saved = tmp_path / "mounted-catalog.json"
    saved.write_text(json.dumps(observation_payload(result.observation)))
    replay = run_saved_report(saved)
    replayed = next(row for row in replay.rule_assessments if row.id.endswith("CATALOG-0"))
    assert replayed.status == "PASS" and replayed.evaluation_proven


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        ('"page_size"', "PASS"),
        ('key="page_size"', "PASS"),
        ("OptionKey.PAGE_SIZE", "PASS"),
        ('"unknown"', "FAIL"),
        ("key", "UNKNOWN"),
    ],
)
def test_bound_operation_argument_uses_canonical_enum_values(tmp_path, actual, expected):
    result, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey\n"
            "def read_option(key: str) -> None: pass\n"
            "def consume(key):\n"
            f"    read_option({actual})\n"
        ),
        rules=[_argument()],
    )
    assert rows[0].status == expected
    if expected == "FAIL":
        assert result.observation.records("violations")[0].kind == "catalog_argument"


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        ('"page_size"', "PASS"),
        ('key="page_size"', "PASS"),
        ("key", "UNKNOWN"),
        ('"not_a_catalog_entry"', "FAIL"),
    ],
)
@pytest.mark.parametrize("mounted", [False, True])
def test_selected_read_call_arguments_count_as_catalog_use(tmp_path, actual, expected, mounted):
    _, rows = _run(
        tmp_path,
        mounted=mounted,
        caller=(
            "def read_option(key: str) -> None: pass\n"
            "def consume(key):\n"
            f"    read_option({actual})\n"
        ),
        rules=[_read_option_use()],
    )
    assert rows[0].status == expected


def test_selected_read_call_accepts_the_displayed_variadic_formal(tmp_path):
    rule = _read_option_use()
    rule["parameter"] = "*keys"
    _, rows = _run(
        tmp_path,
        caller=(
            "def read_option(*keys: str) -> None: pass\n"
            "def consume():\n"
            '    read_option("page_size")\n'
        ),
        rules=[rule],
    )
    assert rows[0].status == "PASS" and rows[0].evaluation_proven


def test_declared_overlay_enum_member_counts_as_catalog_argument(tmp_path):
    rule = _argument()
    rule["overlays"] = ["sample.catalog.ExtraKey"]
    _, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import ExtraKey\n"
            "def read_option(key: str) -> None: pass\n"
            "def consume():\n"
            "    read_option(ExtraKey.NEW)\n"
        ),
        rules=[rule],
    )
    assert rows[0].status == "PASS"


def test_same_invalid_variadic_actuals_keep_distinct_catalog_violations(tmp_path):
    result, rows = _run(
        tmp_path,
        caller=(
            "def read_option(*key: str) -> None: pass\n"
            "def consume():\n"
            '    read_option("unknown", "unknown")\n'
        ),
        rules=[_argument()],
    )
    assert rows[0].status == "FAIL" and rows[0].count == 2
    violations = result.observation.records("violations") or ()
    assert len([item for item in violations if item.kind == "catalog_argument"]) == 2
    assert len({item.id for item in violations if item.kind == "catalog_argument"}) == 2


def test_declared_overlay_enum_member_counts_as_selected_catalog_use(tmp_path):
    rule = _read_option_use(member="NEW")
    rule["overlays"] = ["sample.catalog.ExtraKey"]
    _, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import ExtraKey\n"
            "def read_option(key: str) -> None: pass\n"
            "def consume():\n"
            "    read_option(ExtraKey.NEW)\n"
        ),
        rules=[rule],
    )
    assert rows[0].status == "PASS"


@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize("mounted", [False, True])
def test_ambiguous_overlay_import_keeps_catalog_use_unknown(tmp_path, columnar, mounted):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import encode_canonical_model, observation_payload

    rule = _use(member="NEW")
    rule["overlays"] = ["sample.catalog.ExtraKey"]
    result, rows = _run(
        tmp_path,
        mounted=mounted,
        caller=(
            "from .catalog import OptionKey\n"
            "from .catalog import ExtraKey as Keys\n"
            "from .other import ExtraKey as Keys\n"
            "def consume():\n"
            "    print(OptionKey.PAGE_SIZE)\n"
            "    print(Keys.NEW)\n"
        ),
        rules=[rule],
        extra_files={"sample/other.py": "class ExtraKey: NEW = 'new'\n"},
    )

    assert rows[0].status == "UNKNOWN"
    assert not rows[0].evaluation_proven
    payload = observation_payload(result.observation)
    saved = tmp_path / f"ambiguous-overlay-{columnar}.json"
    saved.write_text(json.dumps(encode_canonical_model(payload) if columnar else payload))
    replay = run_saved_report(saved)
    replayed = next(row for row in replay.rule_assessments if row.id.endswith("CATALOG-0"))
    assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


def test_duplicate_literal_across_catalog_owners_does_not_prove_selected_use(tmp_path):
    rule = _read_option_use(member="PAGE_SIZE")
    rule["overlays"] = ["sample.catalog.OtherKey"]
    _, rows = _run(
        tmp_path,
        caller=(
            "def read_option(key: str) -> None: pass\n"
            "def consume():\n"
            '    read_option("page_size")\n'
        ),
        rules=[rule],
        catalog_suffix=("class OtherKey(StrEnum):\n    NEW = 'page_size'\n"),
    )
    assert rows[0].status == "UNKNOWN"
    assert not rows[0].evaluation_proven


def test_ambiguous_owner_reference_does_not_prove_selected_call_use(tmp_path):
    _, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey as Keys\n"
            "from .other import OptionKey as Keys\n"
            "def read_option(key: str) -> None: pass\n"
            "def consume():\n"
            "    read_option(Keys.PAGE_SIZE)\n"
        ),
        rules=[_read_option_use()],
        extra_files={"sample/other.py": "class OptionKey: PAGE_SIZE = 'page_size'\n"},
    )
    assert rows[0].status == "UNKNOWN"
    assert not rows[0].evaluation_proven


def test_missing_foreign_catalog_owner_cannot_be_replaced_by_same_named_member(tmp_path):
    rule = _read_option_use()
    rule["catalog"] = "sample.missing.OptionKey"
    _, rows = _run(
        tmp_path,
        caller=(
            "def read_option(key: str) -> None: pass\n"
            "def consume():\n"
            '    read_option("page_size")\n'
        ),
        rules=[rule],
    )
    assert rows[0].status == "UNKNOWN"
    assert not rows[0].evaluation_proven


def test_unknown_selected_entry_value_does_not_prove_nonuse(tmp_path):
    _, rows = _run(
        tmp_path,
        caller=(
            'def read_option(key: str) -> None: pass\ndef consume():\n    read_option("other")\n'
        ),
        rules=[{**_read_option_use(member="RETIRED"), "catalog": "sample.catalog.PartialKey"}],
        catalog_suffix=(
            "from enum import Enum\n"
            "class PartialKey(Enum):\n"
            "    PAGE_SIZE = 'page_size'\n"
            "    RETIRED = 42\n"
        ),
    )
    assert rows[0].status == "UNKNOWN"
    assert not rows[0].evaluation_proven


def test_known_catalog_use_is_retained_with_an_unknown_entry_value(tmp_path):
    rule = _read_option_use()
    rule["catalog"] = "sample.catalog.BasicKey"
    rule["member"] = None
    rule["overlays"] = ["sample.catalog.PartialKey"]
    result, rows = _run(
        tmp_path,
        caller=(
            "def read_option(key: str) -> None: pass\n"
            "def consume():\n"
            '    read_option("page_size")\n'
            '    read_option("other")\n'
        ),
        rules=[rule],
        catalog_suffix=(
            "class BasicKey(StrEnum):\n"
            "    PAGE_SIZE = 'page_size'\n"
            "from enum import Enum\n"
            "class PartialKey(Enum):\n"
            "    RETIRED = 42\n"
        ),
    )
    assert rows[0].status == "UNKNOWN"
    assert not rows[0].evaluation_proven
    known_owner = next(
        item
        for item in result.observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.catalog.BasicKey"
    )
    assert all(
        known_owner.id not in item.fact_ids
        for item in result.observation.records("unknowns") or ()
        if item.kind == "catalog_limit"
    )


@pytest.mark.parametrize("mounted", [False, True])
def test_unrelated_same_text_call_does_not_count_as_catalog_use(tmp_path, mounted):
    _, rows = _run(
        tmp_path,
        mounted=mounted,
        caller=(
            "def read_option(key: str) -> None: pass\n"
            "def unrelated(key: str) -> None: pass\n"
            "def consume():\n"
            '    unrelated("page_size")\n'
        ),
        rules=[_read_option_use()],
    )
    assert rows[0].status == "FAIL"


def test_unrelated_call_does_not_enter_catalog_argument_policy(tmp_path):
    _, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey\n"
            "def read_option(key: str) -> None: pass\n"
            "def consume(key):\n"
            '    read_option("page_size")\n'
            '    print("not a catalog argument")\n'
        ),
        rules=[_argument()],
    )
    assert rows[0].status == "PASS"


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize(("selected", "expected"), [("page_size", "PASS"), ("unknown", "FAIL")])
def test_unrelated_multiline_call_does_not_poison_catalog_argument(
    tmp_path, mounted, selected, expected
):
    _, rows = _run(
        tmp_path,
        mounted=mounted,
        caller=(
            "def read_option(key: str) -> None: pass\n"
            "def other(value: str) -> None: pass\n"
            "def consume():\n"
            f'    read_option("{selected}")\n'
            "    other(\n"
            '        "not selected"\n'
            "    )\n"
        ),
        rules=[_argument()],
    )
    assert rows[0].status == expected
    assert rows[0].evaluation_proven


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


def test_known_catalog_argument_failure_survives_an_unknown_argument(tmp_path):
    result, _ = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey\n"
            "def read_option(key: str) -> None: pass\n"
            "def consume(key):\n"
            '    read_option("unknown")\n'
            "    read_option(key)\n"
        ),
        rules=[_argument()],
    )

    row = rule_assessments(
        result.observation,
        undecided_by_rule=unknown_positions_by_rule(result.observation),
    )[0]
    assert row.status == "FAIL"
    assert row.count == 1 and row.undecided > 0 and not row.evaluation_proven
    assert any(
        item.kind == "catalog_limit" for item in result.observation.records("unknowns") or ()
    )


@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize("mutation", ["delete", "move"])
def test_saved_catalog_argument_failure_result_cannot_be_removed_or_moved(
    tmp_path, mutation, columnar
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import encode_canonical_model, observation_payload

    rules = [_argument()] if mutation == "delete" else [_argument(), _argument()]
    result, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey\n"
            "def read_option(key: str) -> None: pass\n"
            'def consume():\n    read_option("unknown")\n'
        ),
        rules=rules,
    )
    assert rows[0].status == "FAIL" and rows[0].evaluation_proven
    raw = copy.deepcopy(observation_payload(result.observation))
    violation = next(item for item in raw["violations"] if item.get("rule_ids") == ["CATALOG-0"])
    if mutation == "delete":
        raw["violations"].remove(violation)
    else:
        violation["rule_ids"] = ["CATALOG-1"]

    saved = tmp_path / "mutated-catalog-failure.json"
    saved.write_text(json.dumps(encode_canonical_model(raw) if columnar else raw))
    replay = run_saved_report(saved)
    replayed = next(row for row in replay.rule_assessments if row.id.endswith("CATALOG-0"))

    assert replayed.status != "PASS" or not replayed.evaluation_proven


def test_overlay_values_are_bound_to_their_declaring_owner(tmp_path):
    rule = _argument()
    rule["overlays"] = ["sample.catalog.ExtraKey"]
    _, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey\n"
            "def read_option(key: str) -> None: pass\n"
            "def consume(key):\n"
            "    read_option('new')\n"
        ),
        rules=[rule],
    )
    assert rows[0].status == "PASS"


def test_source_constant_entries_can_serve_as_an_owner_bound_catalog(tmp_path):
    rule = _argument()
    rule["catalog"] = "sample.catalog.ConstantKey"
    _, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey\n"
            "def read_option(key: str) -> None: pass\n"
            "def consume(key):\n"
            "    read_option('api_token')\n"
        ),
        rules=[rule],
    )
    assert rows[0].status == "PASS"


def test_imported_operation_keeps_canonical_binding_for_enum_argument(tmp_path):
    rule = _argument()
    rule["target"] = "sample.catalog.read_option"
    result, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey, read_option as reader\n"
            "def consume(key):\n"
            "    reader(OptionKey.PAGE_SIZE)\n"
        ),
        rules=[rule],
    )
    assert rows[0].status == "PASS" and rows[0].evaluation_proven
    [call] = [
        record
        for record in result.observation.records("calls")
        if record.data.get("source_scope") == "sample.consumer.consume"
    ]
    assert call.data.get("call_binding") is not None


def test_ordinary_class_attribute_does_not_gain_enum_escape_exception(tmp_path):
    rule = _argument()
    rule["catalog"] = "sample.catalog.ConstantKey"
    rule["target"] = "sample.catalog.read_option"
    result, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import ConstantKey, read_option as reader\n"
            "def consume(key):\n"
            "    reader(ConstantKey.API_TOKEN)\n"
        ),
        rules=[rule],
    )
    [call] = [
        record
        for record in result.observation.records("calls")
        if record.data.get("source_scope") == "sample.consumer.consume"
    ]
    assert rows[0].status == "UNKNOWN"
    assert call.data.get("call_binding") is None


def test_mutated_enum_value_does_not_gain_enum_escape_exception(tmp_path):
    rule = _argument()
    rule["target"] = "sample.catalog.read_option"
    result, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey, read_option as reader\n"
            "def consume(key):\n"
            "    reader(OptionKey.PAGE_SIZE)\n"
        ),
        rules=[rule],
        catalog_suffix="OptionKey.PAGE_SIZE = 'changed'\n",
    )
    [call] = result.observation.records("calls")
    assert rows[0].status == "UNKNOWN"
    assert call.data.get("call_binding") is None


@pytest.mark.parametrize("mounted", [False, True])
def test_enum_member_passed_to_mutating_helper_keeps_catalog_argument_unknown(tmp_path, mounted):
    rule = _argument()
    rule["target"] = "sample.catalog.read_option"
    _, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey, read_option\n"
            "from .mutator import mutate\n"
            "def consume():\n"
            "    mutate(OptionKey.PAGE_SIZE)\n"
            "    read_option(OptionKey.PAGE_SIZE)\n"
        ),
        rules=[rule],
        extra_files={
            "sample/mutator.py": ("def mutate(member):\n    member._value_ = 'changed'\n")
        },
        mounted=mounted,
    )

    assert rows[0].status == "UNKNOWN"
    assert not rows[0].evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
def test_selected_catalog_target_cannot_mutate_enum_member_proof(tmp_path, mounted):
    _, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey\n"
            "def read_option(member):\n"
            "    member._value_ = 'changed'\n"
            "def consume():\n"
            "    read_option(OptionKey.PAGE_SIZE)\n"
            "    read_option(OptionKey.PAGE_SIZE)\n"
        ),
        rules=[{**_argument(), "parameter": "member"}],
        mounted=mounted,
    )

    assert rows[0].status == "UNKNOWN"
    assert not rows[0].evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
def test_selected_catalog_target_cannot_delete_enum_member_proof(tmp_path, mounted):
    _, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey\n"
            "def read_option(member):\n"
            "    del member._value_\n"
            "def consume():\n"
            "    read_option(OptionKey.PAGE_SIZE)\n"
            "    read_option(OptionKey.PAGE_SIZE)\n"
        ),
        rules=[{**_argument(), "parameter": "member"}],
        mounted=mounted,
    )

    assert rows[0].status == "UNKNOWN"
    assert not rows[0].evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
def test_unresolved_call_does_not_escape_enum_member_mutation_check(tmp_path, mounted):
    rule = _argument()
    rule["target"] = "sample.catalog.read_option"
    _, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey, read_option\n"
            "def consume():\n"
            "    opaque(OptionKey.PAGE_SIZE)\n"
            "    read_option(OptionKey.PAGE_SIZE)\n"
        ),
        rules=[rule],
        mounted=mounted,
    )

    assert rows[0].status == "UNKNOWN"
    assert not rows[0].evaluation_proven


@pytest.mark.parametrize(
    "caller",
    [
        (
            "from .catalog import OptionKey, read_option as reader\n"
            "def consume(OptionKey):\n"
            "    reader(OptionKey.PAGE_SIZE)\n"
        ),
        (
            "from .catalog import OptionKey, ConstantKey, read_option as reader\n"
            "OptionKey = ConstantKey\n"
            "def consume():\n"
            "    reader(OptionKey.PAGE_SIZE)\n"
        ),
        (
            "from .catalog import OptionKey, read_option as reader\n"
            "def consume():\n"
            "    reader(OptionKey.nested.PAGE_SIZE)\n"
        ),
    ],
    ids=["local-shadow", "reassigned-import", "nested-attribute"],
)
def test_noncanonical_enum_expressions_do_not_gain_escape_exception(tmp_path, caller):
    rule = _argument()
    rule["target"] = "sample.catalog.read_option"
    result, rows = _run(tmp_path, caller=caller, rules=[rule])
    [call] = result.observation.records("calls")
    assert rows[0].status == "UNKNOWN"
    assert call.data.get("call_binding") is None


def test_enum_with_custom_new_does_not_gain_enum_escape_exception(tmp_path):
    rule = _argument()
    rule["catalog"] = "sample.catalog.CustomKey"
    rule["target"] = "sample.catalog.read_option"
    result, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import CustomKey, read_option as reader\n"
            "def consume():\n"
            "    reader(CustomKey.PAGE_SIZE)\n"
        ),
        rules=[rule],
        catalog_suffix=(
            "class CustomKey(StrEnum):\n"
            "    PAGE_SIZE = 'page_size'\n"
            "    def __new__(cls, value):\n"
            "        return object.__new__(cls)\n"
        ),
    )
    [call] = [
        record
        for record in result.observation.records("calls")
        if record.data.get("source_scope") == "sample.consumer.consume"
    ]
    assert rows[0].status == "UNKNOWN"
    assert call.data.get("call_binding") is None


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


def test_incomplete_reference_context_cannot_prove_catalog_entry_unused(tmp_path):
    caller = (
        "from .catalog import OptionKey\n"
        "def consume():\n"
        f"    print(OptionKey.PAGE_SIZE, '{'x' * 17_000}')\n"
    )

    _, rows = _run(tmp_path, caller=caller, rules=[_use()])

    assert rows[0].status == "UNKNOWN"


def test_known_catalog_read_passes_with_an_unrelated_unknown_reference_context(tmp_path):
    caller = (
        "from .catalog import OptionKey\n"
        "def consume():\n"
        "    print(OptionKey.PAGE_SIZE)\n"
        f"    print(OptionKey.RETIRED, '{'x' * 17_000}')\n"
    )

    _, rows = _run(
        tmp_path,
        caller=caller,
        rules=[_use(member="PAGE_SIZE")],
    )

    assert rows[0].status == "PASS"


@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize("mounted", [False, True])
def test_catalog_use_positive_saved_receipt_replays(tmp_path, columnar, mounted):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import encode_canonical_model, observation_payload

    result, rows = _run(
        tmp_path,
        mounted=mounted,
        caller=(
            "def read_option(key: str) -> None: pass\n"
            "def consume():\n"
            '    read_option("page_size")\n'
        ),
        rules=[_read_option_use()],
    )
    assert rows[0].status == "PASS" and rows[0].evaluation_proven

    assert result.observation is not None
    payload = observation_payload(result.observation)
    owner = next(
        item
        for item in result.observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.catalog.OptionKey"
    )
    target = next(
        item
        for item in result.observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.consumer.read_option"
    )
    selected_call = next(
        item
        for item in result.observation.records("calls") or ()
        if item.data.get("expression") == "read_option"
        and item.data.get("source_scope") == "sample.consumer.consume"
    )
    receipt = next(
        item
        for item in result.observation.records("scope_observations") or ()
        if item.kind == "rule_evaluation"
        and len(item.rule_ids) == 1
        and item.rule_ids[0].endswith("CATALOG-0")
    )
    assert owner.id in receipt.fact_ids
    assert target.id in receipt.fact_ids
    assert selected_call.id in receipt.fact_ids
    saved = tmp_path / "catalog-use-positive.json"
    saved.write_text(json.dumps(encode_canonical_model(payload) if columnar else payload))
    replay = run_saved_report(saved)
    replayed = next(row for row in replay.rule_assessments if row.id.endswith("CATALOG-0"))

    assert replayed.status == "PASS" and replayed.evaluation_proven


@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize("mutation", ["omit-owner", "transplant-scope"])
def test_mounted_catalog_use_receipt_binds_foreign_owner_and_exact_source(
    tmp_path, columnar, mutation
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import encode_canonical_model, observation_payload

    rule = _read_option_use()
    rule["source"] = "sample.consumer.consume"
    rule["source_match"] = "exact"
    result, rows = _run(
        tmp_path,
        mounted=True,
        caller=(
            "def read_option(key: str) -> None: pass\n"
            "def consume():\n"
            '    read_option("page_size")\n'
            "def outside():\n"
            '    read_option("page_size")\n'
        ),
        rules=[rule],
    )
    assert rows[0].status == "PASS" and rows[0].evaluation_proven
    payload = copy.deepcopy(observation_payload(result.observation))
    owner = next(
        item
        for item in payload["symbols"]
        if item["data"].get("qualified_name") == "sample.catalog.OptionKey"
    )
    call_by_scope = {
        item["data"]["source_scope"]: item
        for item in payload["calls"]
        if item["data"].get("expression") == "read_option"
    }
    selected_call = call_by_scope["sample.consumer.consume"]
    outside_call = call_by_scope["sample.consumer.outside"]
    receipt = next(
        item
        for item in payload["scope_observations"]
        if item["kind"] == "rule_evaluation"
        and item.get("rule_ids")
        and item["rule_ids"][0].endswith("CATALOG-0")
    )
    assert owner["id"] in receipt["fact_ids"]
    assert selected_call["id"] in receipt["fact_ids"]
    assert outside_call["id"] not in receipt["fact_ids"]
    if mutation == "omit-owner":
        receipt["fact_ids"].remove(owner["id"])
    else:
        receipt["fact_ids"].remove(selected_call["id"])
        receipt["fact_ids"].append(outside_call["id"])

    saved = tmp_path / "transplanted-catalog-use.json"
    saved.write_text(json.dumps(encode_canonical_model(payload) if columnar else payload))
    replay = run_saved_report(saved)
    replayed = next(row for row in replay.rule_assessments if row.id.endswith("CATALOG-0"))

    assert replayed.status != "PASS" or not replayed.evaluation_proven


def test_incomplete_context_keeps_a_known_missing_use_failure_in_another_scope(tmp_path):
    caller = (
        "from .catalog import OptionKey\n"
        "def consume():\n"
        "    print(OptionKey.PAGE_SIZE)\n"
        f"    print(OptionKey.RETIRED, '{'x' * 17_000}')\n"
        "def unused():\n"
        "    pass\n"
    )
    _, rows = _run(
        tmp_path,
        caller=caller,
        rules=[
            _use(source="sample.consumer.consume"),
            _use(source="sample.consumer.unused"),
        ],
    )

    statuses = {row.id.rsplit(":", 1)[-1]: row.status for row in rows}
    assert statuses == {"CATALOG-0": "PASS", "CATALOG-1": "FAIL"}


def test_ambiguous_catalog_import_cannot_prove_missing_use(tmp_path):
    _, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey\n"
            "from .other import OptionKey\n"
            "def consume(): print(OptionKey.PAGE_SIZE)\n"
        ),
        rules=[_use()],
        extra_files={"sample/other.py": "class OptionKey: PAGE_SIZE = 'page_size'\n"},
    )

    assert rows[0].status == "UNKNOWN"
    assert not rows[0].evaluation_proven


def test_ambiguous_import_outside_selected_source_does_not_poison_catalog_use(tmp_path):
    _, rows = _run(
        tmp_path,
        caller=("from .catalog import OptionKey\ndef consume(): print(OptionKey.PAGE_SIZE)\n"),
        rules=[_use(source="sample.consumer.consume")],
        extra_files={
            "sample/other.py": "class OptionKey: PAGE_SIZE = 'page_size'\n",
            "sample/unrelated.py": (
                "from .catalog import OptionKey\nfrom .other import OptionKey\n"
            ),
        },
    )

    assert rows[0].status == "PASS" and rows[0].evaluation_proven


@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    "mutation",
    ["binding", "catalog", "reference", "source", "contract", "format", "missing", "scope"],
)
def test_saved_catalog_receipt_rejects_changed_bound_inventory(tmp_path, mutation, columnar):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import encode_canonical_model, observation_payload

    result, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey\n"
            "def read_option(key: str) -> None: pass\n"
            "def consume(key):\n"
            "    read_option(OptionKey.PAGE_SIZE)\n"
            "    read_option(OptionKey.PAGE_SIZE)\n"
        ),
        rules=[_argument()],
    )
    assert rows[0].status == "PASS" and rows[0].evaluation_proven
    raw = copy.deepcopy(observation_payload(result.observation))
    if mutation == "binding":
        raw["calls"][0]["data"]["call_binding"] = None
        raw["calls"][0]["data"]["call_arguments"] = None
    elif mutation == "catalog":
        owner = next(
            record
            for record in raw["symbols"]
            if record["data"].get("qualified_name") == "sample.catalog.OptionKey"
        )
        owner["data"]["attribute_declarations"][0]["literal_value"] = "changed"
    elif mutation == "reference":
        reference = next(
            record
            for record in raw["references"]
            if record["data"].get("expression") == "OptionKey.PAGE_SIZE"
        )
        reference["data"]["expression"] = "OptionKey.RETIRED"
    elif mutation == "source":
        raw["source"]["source_digest"] = "0" * 64
    elif mutation == "contract":
        raw["contract"]["digest"] = "0" * 64
    elif mutation == "format":
        raw["schema_version"] = "2.8.0"
    else:
        receipt = next(
            record
            for record in raw["scope_observations"]
            if record["kind"] == "rule_evaluation" and record.get("rule_ids") == ["CATALOG-0"]
        )
        if mutation == "missing":
            receipt["data"].pop("call_scope_proof")
        else:
            receipt["data"]["call_scope_proof"]["selected_files"][0] = "outside.py"
    saved = tmp_path / "stale-catalog.json"
    saved.write_text(json.dumps(encode_canonical_model(raw) if columnar else raw))

    replay = run_saved_report(saved)

    assert not replay.rule_assessments or (
        replay.rule_assessments[0].status != "PASS"
        or not replay.rule_assessments[0].evaluation_proven
    )


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize("missing", ["catalog", "overlay"])
def test_missing_catalog_inventory_cannot_prove_literal_nonmembership(
    tmp_path, mounted, columnar, missing
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import encode_canonical_model, observation_payload

    rule = _argument()
    if missing == "catalog":
        rule["catalog"] = "sample.catalog.MissingKey"
    else:
        rule["overlays"] = ["sample.catalog.MissingKey"]
    result, rows = _run(
        tmp_path,
        mounted=mounted,
        caller=(
            "def read_option(key: str) -> None: pass\n"
            "def consume():\n    read_option('not_a_catalog_entry')\n"
        ),
        rules=[rule],
    )

    assert rows[0].status == "UNKNOWN" and not rows[0].evaluation_proven
    assert not [
        row
        for row in result.observation.records("violations") or ()
        if row.kind == "catalog_argument"
    ]
    payload = observation_payload(result.observation)
    saved = tmp_path / "incomplete-catalog.json"
    saved.write_bytes(json.dumps(encode_canonical_model(payload) if columnar else payload).encode())
    replay = run_saved_report(saved)
    [replayed] = replay.rule_assessments
    assert replayed.status.value == "UNKNOWN" and not replayed.evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_local_enum_owner_alias_mutation_keeps_catalog_argument_unknown(
    tmp_path, mounted, columnar
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import encode_canonical_model, observation_payload

    result, rows = _run(
        tmp_path,
        mounted=mounted,
        caller=(
            "from .catalog import OptionKey\n"
            "def read_option(key: str) -> None: pass\n"
            "def consume():\n    read_option(OptionKey.PAGE_SIZE)\n"
        ),
        rules=[_argument()],
        extra_files={
            "sample/mutator.py": (
                "from .catalog import OptionKey as Keys\n"
                "Alias = Keys\n"
                "Alias.PAGE_SIZE._value_ = 'changed'\n"
            )
        },
    )

    assert rows[0].status == "UNKNOWN" and not rows[0].evaluation_proven
    assert not [
        row
        for row in result.observation.records("violations") or ()
        if row.kind == "catalog_argument"
    ]
    payload = observation_payload(result.observation)
    saved = tmp_path / "mutated-catalog-owner.json"
    saved.write_bytes(json.dumps(encode_canonical_model(payload) if columnar else payload).encode())
    replay = run_saved_report(saved)
    [replayed] = replay.rule_assessments
    assert replayed.status.value == "UNKNOWN" and not replayed.evaluation_proven


# The reference collector reads the prefix of a chain it does not resolve (#731).
@pytest.mark.parametrize("read", ["OptionKey.RETIRED.value", "OptionKey.RETIRED.__dict__"])
def test_member_read_under_an_unresolved_attribute_counts_as_catalog_use(tmp_path, read):
    _, rows = _run(
        tmp_path,
        caller=f"from .catalog import OptionKey\ndef consume():\n    return {read}\n",
        rules=[_use(member="RETIRED")],
    )
    assert (rows[0].status, rows[0].evaluation_proven) == ("PASS", True)


def test_prefix_read_on_a_continuation_line_keeps_catalog_use_absence_unknown(tmp_path):
    # Cost of #731: the one-line excerpt of `"k": ExtraKey.NEW.value,` gives no context.
    _, rows = _run(
        tmp_path,
        caller="from .catalog import OptionKey, ExtraKey\n"
        "def consume():\n"
        "    print(OptionKey.PAGE_SIZE)\n"
        "    return {\n"
        '        "k": ExtraKey.NEW.value,\n'
        "    }\n",
        rules=[_use(member="RETIRED")],
    )
    assert (rows[0].status, rows[0].evaluation_proven) == ("UNKNOWN", False)


# A class read is not a member read, also when its alias has the name of a member.
@pytest.mark.parametrize(
    "files",
    [
        {"sample/consumer.py": "from .catalog import OptionKey as RETIRED\n"},
        {
            "sample/api.py": "from .catalog import OptionKey\n",
            "sample/consumer.py": "from .api import OptionKey as RETIRED\n",
        },
    ],
    ids=["direct-alias", "reexport-alias"],
)
def test_owner_alias_named_like_a_member_is_no_catalog_use(tmp_path, files):
    caller = files.pop("sample/consumer.py") + "def consume():\n    return RETIRED\n"
    _, rows = _run(tmp_path, caller=caller, rules=[_use(member="RETIRED")], extra_files=files)
    assert (rows[0].status, rows[0].evaluation_proven) == ("FAIL", True)


# A member read through a module that imports the enum is a member read (#731).
@pytest.mark.parametrize("read", ["OptionKey.RETIRED", "OptionKey.RETIRED.value"])
def test_member_read_through_a_reexport_counts_as_catalog_use(tmp_path, read):
    _, rows = _run(
        tmp_path,
        caller=f"from .api import OptionKey\ndef consume():\n    return {read}\n",
        rules=[_use(member="RETIRED")],
        extra_files={"sample/api.py": "from .catalog import OptionKey\n"},
    )
    assert (rows[0].status, rows[0].evaluation_proven) == ("PASS", True)
