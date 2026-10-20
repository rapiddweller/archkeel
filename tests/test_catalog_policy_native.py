"""Catalog arguments and required source reads use admitted enum declarations."""

import copy
import json
from pathlib import Path

import pytest

from archkeel.cli.observe import observe
from archkeel.ir.decisions import rule_assessments


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


def _run(tmp_path: Path, *, caller: str, rules, catalog_suffix: str = ""):
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


def _use(source="sample.consumer"):
    return {
        "kind": "catalog_use",
        "source": source,
        "catalog": "sample.catalog.OptionKey",
        "member": "PAGE_SIZE",
    }


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
        (
            "from .catalog import OptionKey\ndef consume():\n    print(OptionKey.PAGE_SIZE)\n",
            "PASS",
        ),
        (
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
        (
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


@pytest.mark.parametrize("mutation", ["binding", "catalog", "scope"])
def test_saved_catalog_receipt_rejects_changed_bound_inventory(tmp_path, mutation):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import observation_payload

    result, rows = _run(
        tmp_path,
        caller=(
            "from .catalog import OptionKey\n"
            "def read_option(key: str) -> None: pass\n"
            "def consume(key):\n"
            "    read_option(OptionKey.PAGE_SIZE)\n"
            "    print(OptionKey.PAGE_SIZE)\n"
        ),
        rules=[_argument(), _use()],
    )
    assert all(row.status == "PASS" and row.evaluation_proven for row in rows)
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
    else:
        receipt = next(
            record
            for record in raw["scope_observations"]
            if record["kind"] == "rule_evaluation" and record.get("rule_ids") == ["CATALOG-0"]
        )
        receipt["data"]["call_scope_proof"]["selected_files"][0] = "outside.py"
    saved = tmp_path / "stale-catalog.json"
    saved.write_text(json.dumps(raw))

    replay = run_saved_report(saved)

    argument, usage = replay.rule_assessments
    assert argument.status == "UNKNOWN" and not argument.evaluation_proven
    if mutation == "scope":
        assert usage.status == "PASS" and usage.evaluation_proven
    else:
        assert usage.status == "UNKNOWN" and not usage.evaluation_proven
