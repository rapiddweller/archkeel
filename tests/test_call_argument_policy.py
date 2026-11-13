# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Call argument rules bind written actuals to canonical formal parameters."""

import json
from pathlib import Path

import pytest
from test_exact_module_ownership import _component

from archkeel.cli.observe import observe
from archkeel.ir.codec import observation_payload
from archkeel.ir.decisions import rule_assessments

_PROVENANCE = ["docs/architecture/sample.md"]


def _selector_rule():
    return {
        "id": "SELECT-PAGE",
        "kind": "forbidden_construct",
        "source": "sample",
        "constructs": ["string_literal_compare"],
        "selector": {"receiver": "sample.storage.Storage", "member": "page", "role": "call"},
        "rationale": "Selector facts are only collected for a declared selector rule.",
        "provenance": _PROVENANCE,
        "decided_by": "architect",
    }


def _contract(
    *, source="sample.caller", target="sample.storage.page", parameter="query", selector=False
):
    return {
        "schema_version": "3.11.0" if selector else "3.10.0",
        "components": [
            {
                "id": "COMP-SAMPLE",
                "label": "sample",
                "role": "component",
                "packages": ["sample"],
                "responsibilities": ["Own the synthetic sample."],
                "forbidden_responsibilities": [],
                "provenance": _PROVENANCE,
            }
        ],
        "rules": [
            {
                "id": "FORBID-QUERY-LITERAL",
                "kind": "forbidden_call_argument",
                "source": source,
                "target": target,
                "parameter": parameter,
                "rationale": "Query text must come from the selected typed argument.",
                "provenance": _PROVENANCE,
                "decided_by": "architect",
            },
            *([_selector_rule()] if selector else []),
        ],
    }


def _observe(
    tmp_path: Path,
    caller: str,
    *,
    storage: str | None = None,
    mounted: bool = False,
    source: str = "sample.caller",
    target: str = "sample.storage.page",
    parameter: str = "query",
    selector: bool = False,
):
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "docs/architecture/sample.md": "Synthetic decision.\n",
        "contract.json": json.dumps(
            _contract(source=source, target=target, parameter=parameter, selector=selector)
        ),
        "sample/__init__.py": "",
        "sample/storage.py": storage
        or ("class QuerySpec: pass\ndef page(query: QuerySpec, label: str = '') -> None: pass\n"),
        "sample/caller.py": caller,
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    contract = _contract(source=source, target=target, parameter=parameter, selector=selector)
    if mounted:
        (tmp_path / "inside.json").write_text(json.dumps(contract))
        contract = {
            "schema_version": "3.11.0" if selector else "3.10.0",
            "components": [_component("sample", ["sample"], inside="inside.json")],
            "rules": [],
        }
        (tmp_path / "contract.json").write_text(json.dumps(contract))
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
    [row] = [
        item
        for item in rule_assessments(result.observation, undecided_by_rule={})
        if item.kind == "forbidden_call_argument"
    ]
    return result, row


@pytest.mark.parametrize(
    ("actuals", "expected"),
    [
        ('"SELECT 1"', "FAIL"),
        ('query="SELECT 1"', "FAIL"),
        ('spec, label="SELECT 1"', "PASS"),
        ('query=spec, label="heading"', "PASS"),
    ],
)
def test_policy_selects_only_the_bound_query_parameter(tmp_path, actuals, expected):
    _, row = _observe(
        tmp_path,
        f"from .storage import page\ndef consume(spec):\n    page({actuals})\n",
    )

    assert row.kind == "forbidden_call_argument"
    assert row.status == expected and row.evaluation_proven


@pytest.mark.parametrize(
    "formal,actual",
    [
        ("*args", "'same', value, 'same'"),
        ("**kwargs", "first='same', allowed=value, second='same'"),
    ],
)
@pytest.mark.parametrize("mounted", [False, True])
def test_variadic_literals_share_one_violation_with_all_evidence_and_saved_replay(
    tmp_path, formal, actual, mounted
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes

    result, row = _observe(
        tmp_path,
        f"from .storage import page\ndef consume(value):\n    page({actual})\n",
        storage=f"def page({formal}): pass\n",
        parameter=formal,
        mounted=mounted,
    )
    assert row.status == "FAIL" and row.evaluation_proven
    [violation] = result.observation.records("violations")
    assert len(violation.evidence_ids) == 2
    for name, payload in (
        ("ordinary", json.dumps(observation_payload(result.observation)).encode()),
        ("columnar", canonical_report_bytes(result.observation)),
    ):
        saved = tmp_path / f"{name}.json"
        saved.write_bytes(payload)
        [replayed] = run_saved_report(saved).rule_assessments
        assert replayed.status == "FAIL" and replayed.evaluation_proven


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        ('""', "FAIL"),
        ('"SELECT " "1"', "FAIL"),
        ('f"SELECT 1"', "PASS"),
        ('"SELECT " + "1"', "PASS"),
        ('(value := "SELECT 1")', "PASS"),
    ],
)
def test_only_written_string_constants_are_claimed_as_literals(tmp_path, actual, expected):
    _, row = _observe(
        tmp_path,
        f"from .storage import page\ndef consume(spec):\n    page({actual})\n",
    )

    assert row.status == expected and row.evaluation_proven


@pytest.mark.parametrize("actual", ["*queries", "query='x', query=spec"])
def test_spread_or_duplicate_actuals_are_unknown(tmp_path, actual):
    _, row = _observe(
        tmp_path,
        f"from .storage import page\ndef consume(spec, queries):\n    page({actual})\n",
    )

    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize(
    ("callee", "actual", "expected"),
    [
        ("other", "spec", "PASS"),
        ("other", "'selected literal'", "FAIL"),
        ("page", "spec", "UNKNOWN"),
        ("unbound", "spec", "UNKNOWN"),
    ],
)
def test_argument_inventory_is_required_only_for_potentially_selected_calls(
    tmp_path, mounted, callee, actual, expected
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes
    from archkeel.ir.decisions import unknown_positions_by_rule

    result, row = _observe(
        tmp_path,
        "from .storage import page, other\n"
        "def consume(spec):\n"
        f"    page({actual})\n"
        f"    {callee}(\n"
        "        'unbounded literal'\n"
        "    )\n",
        storage="def page(query): pass\ndef other(query): pass\n",
        mounted=mounted,
    )
    [row] = rule_assessments(
        result.observation, undecided_by_rule=unknown_positions_by_rule(result.observation)
    )
    calls = observation_payload(result.observation)["calls"]
    unbounded = next(call for call in calls if call["data"]["call_arguments"] is None)
    binding = unbounded["data"]["call_binding"]
    assert (binding["target"] if binding else None) == (
        None if callee == "unbound" else f"sample.storage.{callee}"
    )
    assert row.status == expected
    assert row.evaluation_proven == (expected != "UNKNOWN")
    for name, payload in (
        ("ordinary", json.dumps(observation_payload(result.observation)).encode()),
        ("columnar", canonical_report_bytes(result.observation)),
    ):
        saved = tmp_path / f"{name}.json"
        saved.write_bytes(payload)
        assert run_saved_report(saved).rule_assessments == (row,)


@pytest.mark.parametrize(
    ("caller", "source", "storage", "target"),
    [
        ("", "sample.caller", None, "sample.storage.page"),
        ("def consume(spec): pass\n", "sample.absent", None, "sample.storage.page"),
        (
            "from .storage import page\ndef consume(spec):\n page('x')\n",
            "sample.caller",
            "@decorate\ndef page(query): pass\n",
            "sample.storage.page",
        ),
        (
            "from .storage import page\ndef consume(spec):\n page('x')\n",
            "sample.caller",
            "def page(query): pass\npage = replacement\n",
            "sample.storage.page",
        ),
        (
            "from .storage import QuerySpec\ndef consume(spec):\n QuerySpec('x')\n",
            "sample.caller",
            "class QuerySpec: pass\n",
            "sample.storage.QuerySpec",
        ),
    ],
)
def test_missing_scope_target_or_signature_is_unknown(tmp_path, caller, source, storage, target):
    _, row = _observe(
        tmp_path,
        caller,
        source=source,
        storage=storage,
        target=target,
    )

    assert row.status == "UNKNOWN" and not row.evaluation_proven


def test_argument_rule_is_admitted_only_by_contract_3_10_schema():
    from test_result_schema import _validator

    validator = _validator("command-result-9.0.schema.json")
    payload = _contract()
    current = validator.evolve(schema={"$ref": "urn:archkeel:architecture-contract:3.10.0"})
    historical = validator.evolve(schema={"$ref": "urn:archkeel:architecture-contract:3.9.0"})
    assert current.is_valid(payload)
    payload["schema_version"] = "3.9.0"
    assert not historical.is_valid(payload)


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    ("receiver_setup", "receiver"),
    [
        ("", "Storage().page"),
        ("store = Storage()\n    ", "store.page"),
    ],
)
@pytest.mark.parametrize(
    ("actual", "expected"),
    [("'literal'", "FAIL"), ("spec", "PASS"), ("*queries", "UNKNOWN")],
)
def test_constructed_receiver_arguments_bind_and_replay(
    tmp_path, mounted, columnar, receiver_setup, receiver, actual, expected
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import encode_canonical_model

    caller = (
        "from .storage import Storage\n"
        "def consume(spec, queries):\n"
        f"    {receiver_setup}{receiver}({actual})\n"
    )
    result, row = _observe(
        tmp_path,
        caller,
        storage="class Storage:\n    def page(self, query): pass\n",
        mounted=mounted,
        target="sample.storage.Storage.page",
    )

    assert row.status.value == expected
    report = observation_payload(result.observation)
    saved = tmp_path / "constructed-receiver.json"
    saved.write_text(json.dumps(encode_canonical_model(report) if columnar else report))
    [replayed] = run_saved_report(saved).rule_assessments
    assert replayed.status.value == expected
    assert replayed.evaluation_proven == (expected != "UNKNOWN")
    if expected != "UNKNOWN":
        assert replayed == row
