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
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "docs/architecture/catalog.md": "Synthetic catalog decision.\n",
        "contract.json": json.dumps(_raw(*rules)),
        "sample/__init__.py": "",
        "sample/catalog.py": config,
        "sample/consumer.py": caller,
        **(extra_files or {}),
    }
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


def _use(source="sample.consumer", member="PAGE_SIZE"):
    return {
        "kind": "catalog_use",
        "source": source,
        "catalog": "sample.catalog.OptionKey",
        "member": member,
    }


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
    assert all(item.held for item in references.values())

    renamed = renamed_contract(contract, {"sample": "renamed"})
    moved = {item.pointer: item.value for item in module_references(renamed)}
    assert moved["/rules/0/source"] == "renamed.consumer"
    assert moved["/rules/0/target"] == "renamed.consumer.read_option"
    assert moved["/rules/0/catalog"] == "renamed.catalog.OptionKey"
    assert moved["/rules/0/overlays/0"] == "renamed.catalog.ExtraKey"


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
def test_catalog_use_positive_saved_receipt_replays(tmp_path, columnar):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import encode_canonical_model, observation_payload

    result, rows = _run(
        tmp_path,
        caller="from .catalog import OptionKey\ndef consume():\n    print(OptionKey.PAGE_SIZE)\n",
        rules=[_use()],
    )
    assert rows[0].status == "PASS" and rows[0].evaluation_proven

    assert result.observation is not None
    payload = observation_payload(result.observation)
    saved = tmp_path / "catalog-use-positive.json"
    saved.write_text(json.dumps(encode_canonical_model(payload) if columnar else payload))
    replay = run_saved_report(saved)
    replayed = next(row for row in replay.rule_assessments if row.id.endswith("CATALOG-0"))

    assert replayed.status == "PASS" and replayed.evaluation_proven


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
            "    print(OptionKey.PAGE_SIZE)\n"
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
