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
from archkeel.ir.codec_observation import parse_observation
from archkeel.ir.decisions import rule_assessments

_PROVENANCE = ["docs/architecture/sample.md"]


def _contract(*, source="sample.caller", target="sample.storage.page", parameter="query"):
    return {
        "schema_version": "3.10.0",
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
            }
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
):
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "docs/architecture/sample.md": "Synthetic decision.\n",
        "contract.json": json.dumps(_contract(source=source, target=target, parameter=parameter)),
        "sample/__init__.py": "",
        "sample/storage.py": storage
        or ("class QuerySpec: pass\ndef page(query: QuerySpec, label: str = '') -> None: pass\n"),
        "sample/caller.py": caller,
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    contract = _contract(source=source, target=target, parameter=parameter)
    if mounted:
        (tmp_path / "inside.json").write_text(json.dumps(contract))
        contract = {
            "schema_version": "3.10.0",
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
    [row] = rule_assessments(result.observation, undecided_by_rule={})
    return result, row


def test_written_positional_string_literal_fails_for_selected_formal(tmp_path):
    result, row = _observe(
        tmp_path,
        'from .storage import page\ndef consume(spec):\n    page("SELECT 1")\n',
    )

    assert row.kind == "forbidden_call_argument"
    assert row.status == "FAIL" and row.evaluation_proven
    [violation] = result.observation.records("violations")
    assert violation.rule_ids == (row.id,)
    assert violation.evidence_ids and violation.fact_ids


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


@pytest.mark.parametrize("formal", ["*args", "**kwargs"])
@pytest.mark.parametrize("displayed", [False, True])
@pytest.mark.parametrize("value,expected", [("'literal'", "FAIL"), ("value", "PASS"), ("", "PASS")])
@pytest.mark.parametrize("mounted", [False, True])
def test_variadic_selectors_bind_displayed_and_plain_names(
    tmp_path, formal, displayed, value, expected, mounted
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes

    actual = f"item={value}" if formal == "**kwargs" and value else value
    result, row = _observe(
        tmp_path,
        f"from .storage import page\ndef consume(value):\n    page({actual})\n",
        storage=f"def page({formal}): pass\n",
        parameter=formal if displayed else formal.lstrip("*"),
        mounted=mounted,
    )
    assert row.status == expected and row.evaluation_proven
    model = result.observation
    for name, payload in (
        ("ordinary", json.dumps(observation_payload(model)).encode()),
        ("columnar", canonical_report_bytes(model)),
    ):
        saved = tmp_path / f"{name}.json"
        saved.write_bytes(payload)
        [replayed] = run_saved_report(saved).rule_assessments
        assert replayed.status == expected and replayed.evaluation_proven


@pytest.mark.parametrize(
    "formal,parameter,actual",
    [
        ("*args", "**args", "'literal'"),
        ("*args", "***args", "'literal'"),
        ("*args", "****args", "'literal'"),
        ("**kwargs", "*kwargs", "item='literal'"),
        ("**kwargs", "***kwargs", "item='literal'"),
    ],
)
@pytest.mark.parametrize("mounted", [False, True])
def test_absent_variadic_selector_does_not_certify_a_normalized_violation(
    tmp_path, formal, parameter, actual, mounted
):
    _, row = _observe(
        tmp_path,
        f"from .storage import page\ndef consume():\n    page({actual})\n",
        storage=f"def page({formal}): pass\n",
        parameter=parameter,
        mounted=mounted,
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven


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


def test_known_violation_survives_a_separate_unbindable_call(tmp_path):
    result, row = _observe(
        tmp_path,
        "from .storage import page\n"
        "def consume(spec, queries):\n"
        '    page("SELECT 1")\n'
        "    page(*queries)\n",
    )

    assert row.status == "FAIL"
    [violation] = result.observation.records("violations")
    assert violation.kind == "forbidden_call_argument"


def test_unbound_calls_keep_null_argument_facts_and_do_not_erase_known_failures(tmp_path):
    result, row = _observe(
        tmp_path,
        "from .storage import page\n"
        "def consume(spec):\n"
        '    page("SELECT 1")\n'
        '    unknown("SELECT 2")\n',
    )

    assert row.status == "FAIL"
    calls = observation_payload(result.observation)["calls"]
    direct = next(call for call in calls if call["data"]["expression"] == "page")
    unbound = next(call for call in calls if call["data"]["expression"] == "unknown")
    assert direct["data"]["call_arguments"]
    assert unbound["data"]["call_binding"] is None
    assert unbound["data"]["call_arguments"] is None


@pytest.mark.parametrize("mounted", [False, True])
def test_call_argument_rule_runs_at_root_and_inside_mount(tmp_path, mounted):
    result, row = _observe(
        tmp_path,
        "from .storage import page\ndef consume(spec):\n    page('SELECT 1')\n",
        mounted=mounted,
    )

    assert row.status == "FAIL" and row.evaluation_proven
    [violation] = result.observation.records("violations")
    assert violation.rule_ids == (row.id,)


def test_saved_receipt_does_not_certify_changed_actual_or_removed_violation(tmp_path):
    from archkeel.check.report import run_saved_report

    result, row = _observe(
        tmp_path,
        "from .storage import page\ndef consume(spec):\n    page('SELECT 1')\n",
    )
    assert row.status == "FAIL"
    raw = observation_payload(result.observation)
    argument = raw["calls"][0]["data"]["call_arguments"][0]
    assert argument["value"] == "SELECT 1"
    argument["value_kind"] = "other"
    argument["value"] = None
    raw["violations"] = []
    saved = tmp_path / "tampered.json"
    saved.write_text(json.dumps(raw))

    replay = run_saved_report(saved)

    [assessment] = replay.rule_assessments
    assert assessment.status == "UNKNOWN" and not assessment.evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize("change", ["relocate", "delete", "change"])
def test_saved_argument_receipt_binds_result_section_and_contents(
    tmp_path, mounted, columnar, change
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes

    result, row = _observe(
        tmp_path,
        "from .storage import page\ndef consume():\n    page('SELECT 1')\n",
        mounted=mounted,
    )
    assert row.status == "FAIL" and row.evaluation_proven
    payload = observation_payload(result.observation)
    [violation] = payload["violations"]
    if change == "relocate":
        payload["violations"].clear()
        payload["scope_observations"].append(violation)
    elif change == "delete":
        payload["violations"].clear()
    else:
        violation["title"] = "changed finding"
    saved = tmp_path / "tampered.json"
    saved.write_bytes(canonical_report_bytes(payload) if columnar else json.dumps(payload).encode())

    [replayed] = run_saved_report(saved).rule_assessments

    assert replayed.status != "PASS" and not replayed.evaluation_proven


def test_source_facts_reject_a_forged_string_literal_value(tmp_path):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import (
        CollectionResponse,
        ProtocolError,
        decode_response,
        encode_response,
    )
    from archkeel.ir.protocol import CollectionRequest, PythonSettings, SnapshotInput, SourceScope

    _observe(tmp_path, "from .storage import page\ndef run():\n    page('safe')\n")
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    payload = json.loads(encode_response(CollectionResponse(facts)))
    calls = next(
        section["records"] for section in payload["facts"]["sections"] if section["name"] == "calls"
    )
    call = next(record for record in calls if record["data"]["expression"] == "page")
    assert call["data"]["call_arguments"][0]["value"] == "safe"
    call["data"]["call_arguments"][0]["value"] = "forged"

    with pytest.raises(ProtocolError, match="argument.*source|source.*argument"):
        decode_response(json.dumps(payload).encode())


def test_unbounded_multiline_call_keeps_identity_and_unknown_argument_inventory(tmp_path):
    from test_result_schema import _validator

    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import result_payload
    from archkeel.ir.model import SCHEMA_VERSION

    result, row = _observe(
        tmp_path,
        "from .storage import page\ndef consume(spec):\n    page(\n        'SELECT 1'\n    )\n",
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    raw = observation_payload(result.observation)
    call = next(item for item in raw["calls"] if item["data"]["expression"] == "page")
    assert call["data"]["call_binding"] is not None
    assert call["data"]["call_arguments"] is None
    validator = _validator("command-result-9.0.schema.json")
    for profile in ("decoded", "python-decoded"):
        schema = validator.evolve(
            schema={"$ref": f"urn:archkeel:architecture-ir:{profile}:{SCHEMA_VERSION}"}
        )
        assert not list(schema.iter_errors(raw))
    saved = tmp_path / "multiline-observation.json"
    saved.write_text(json.dumps(raw))
    replay = run_saved_report(saved)
    assert replay.rule_assessments[0].status == "UNKNOWN"
    assert not list(validator.iter_errors(result_payload(replay)))

    from test_result_schema import _validator

    validator = _validator("command-result-9.0.schema.json")
    historical = json.loads(json.dumps(raw))
    historical["schema_version"] = "2.8.0"
    for profile in ("decoded", "python-decoded"):
        schema = validator.evolve(schema={"$ref": f"urn:archkeel:architecture-ir:{profile}:2.8.0"})
        assert schema.is_valid(historical)


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


def test_source_facts_reject_reordered_actual_evidence(tmp_path):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import (
        CollectionResponse,
        ProtocolError,
        decode_response,
        encode_response,
    )
    from archkeel.ir.protocol import CollectionRequest, PythonSettings, SnapshotInput, SourceScope

    _observe(tmp_path, "from .storage import page\ndef run():\n    page('safe', 'heading')\n")
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    payload = json.loads(encode_response(CollectionResponse(facts)))
    calls = next(
        section["records"] for section in payload["facts"]["sections"] if section["name"] == "calls"
    )
    call = next(record for record in calls if record["data"]["expression"] == "page")
    call["data"]["call_arguments"].reverse()

    with pytest.raises(ProtocolError, match="argument.*source|source.*argument"):
        decode_response(json.dumps(payload).encode())


@pytest.mark.parametrize("mutation", ["selector", "signature"])
def test_saved_receipt_does_not_certify_changed_formal_or_signature(tmp_path, mutation):
    from archkeel.check.report import run_saved_report

    result, row = _observe(
        tmp_path,
        "from .storage import page\ndef consume(spec):\n    page(spec)\n",
    )
    assert row.status == "PASS"
    raw = observation_payload(result.observation)
    if mutation == "selector":
        rule = next(
            item for item in raw["declarations"] if item["kind"] == "forbidden_call_argument"
        )
        rule["data"]["parameter"] = "label"
    else:
        target = next(
            item
            for item in raw["symbols"]
            if item["data"]["qualified_name"] == "sample.storage.page"
        )
        target["data"]["parameters"][0]["name"] = "value"
    saved = tmp_path / "changed-contract-proof.json"
    saved.write_text(json.dumps(raw))

    replay = run_saved_report(saved)

    [assessment] = replay.rule_assessments
    assert assessment.status == "UNKNOWN" and not assessment.evaluation_proven


def test_positional_only_keyword_is_bound_to_kwargs_not_selected_formal(tmp_path):
    _, row = _observe(
        tmp_path,
        "from .storage import page\ndef consume(spec):\n    page(query='literal')\n",
        storage="def page(query='default', /, **options): pass\n",
    )

    assert row.status == "PASS" and row.evaluation_proven


def test_call_argument_evidence_requires_the_new_observation_version(tmp_path):
    result, _ = _observe(
        tmp_path,
        "from .storage import page\ndef consume(spec):\n    page(spec)\n",
    )
    raw = observation_payload(result.observation)
    assert raw["schema_version"] == "2.9.0"
    assert parse_observation(raw).schema_version == "2.9.0"

    old = json.loads(json.dumps(raw))
    old["schema_version"] = "2.4.0"
    old["declarations"] = [
        item for item in old["declarations"] if item["kind"] != "source_ownership"
    ]
    old_references = old["references"]
    old["references"] = []
    for item in old_references:
        if item["kind"] != "source_role":
            item["data"].pop("reference_context", None)
            old["references"].append(item)
    with pytest.raises(ValueError, match="call_arguments require"):
        parse_observation(old)

    incomplete = json.loads(json.dumps(raw))
    incomplete["calls"][0]["data"].pop("call_arguments")
    with pytest.raises(ValueError, match="explicit call_arguments"):
        parse_observation(incomplete)

    historical = json.loads(json.dumps(raw))
    historical["schema_version"] = "2.5.0"
    historical["references"] = [
        item for item in historical["references"] if item["kind"] != "source_role"
    ]
    for item in historical["references"]:
        item["data"].pop("reference_context", None)
    for symbol in historical["symbols"]:
        for attribute in symbol["data"].get("attribute_declarations", []):
            attribute.pop("literal_value", None)
    assert parse_observation(historical).schema_version == "2.5.0"
    stale_catalog_fact = json.loads(json.dumps(historical))
    stale_catalog_fact["symbols"][0]["data"].setdefault("attribute_declarations", []).append(
        {"name": "PAGE_SIZE", "literal_value": "page_size"}
    )
    with pytest.raises(ValueError, match="catalog literal values require"):
        parse_observation(stale_catalog_fact)

    from test_result_schema import _validator

    validator = _validator("command-result-9.0.schema.json")
    current_schema = validator.evolve(schema={"$ref": "urn:archkeel:architecture-ir:decoded:2.9.0"})
    historical_schema = validator.evolve(
        schema={"$ref": "urn:archkeel:architecture-ir:decoded:2.1.0"}
    )
    assert current_schema.is_valid(raw)
    assert not historical_schema.is_valid(raw)


def test_bound_call_with_no_written_actuals_keeps_an_empty_tuple(tmp_path):
    result, row = _observe(
        tmp_path,
        "from .storage import page\ndef consume(spec):\n    page()\n",
        storage="def page(query: str = 'default') -> None: pass\n",
    )

    assert row.status == "PASS" and row.evaluation_proven
    raw = observation_payload(result.observation)
    [call] = [item for item in raw["calls"] if item["data"]["expression"] == "page"]
    assert call["data"]["call_binding"] is not None
    assert call["data"]["call_arguments"] == []


@pytest.mark.parametrize("columnar", [False, True])
def test_unbound_call_has_null_arguments_and_cannot_certify_policy(tmp_path, columnar):
    from test_result_schema import _validator

    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import encode_canonical_model

    result, row = _observe(
        tmp_path,
        'def consume(spec):\n    unknown("literal")\n',
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    raw = observation_payload(result.observation)
    [call] = [item for item in raw["calls"] if item["data"]["expression"] == "unknown"]
    assert call["data"]["call_binding"] is None
    assert call["data"]["call_arguments"] is None

    validator = _validator("command-result-9.0.schema.json")
    current_schema = validator.evolve(schema={"$ref": "urn:archkeel:architecture-ir:decoded:2.9.0"})
    assert current_schema.is_valid(raw)

    inconsistent = json.loads(json.dumps(raw))
    inconsistent_call = next(
        item for item in inconsistent["calls"] if item["data"]["expression"] == "unknown"
    )
    inconsistent_call["data"]["call_arguments"] = []
    assert not current_schema.is_valid(inconsistent)
    with pytest.raises(ValueError, match="canonical call binding"):
        parse_observation(inconsistent)

    saved = tmp_path / ("unbound-columnar.json" if columnar else "unbound.json")
    saved_payload = encode_canonical_model(raw) if columnar else raw
    saved.write_text(json.dumps(saved_payload))
    replay = run_saved_report(saved)
    [assessment] = replay.rule_assessments
    assert assessment.status == "UNKNOWN" and not assessment.evaluation_proven

    from archkeel.ir.codec import decode_canonical_model

    decoded = parse_observation(decode_canonical_model(saved_payload))
    [decoded_call] = [
        item for item in decoded.records("calls") if item.data.get("expression") == "unknown"
    ]
    assert decoded_call.data.get("call_arguments") is None


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


def test_alias_uses_canonical_target_and_other_same_named_method_is_disjoint(tmp_path):
    _, alias_row = _observe(
        tmp_path,
        "from .storage import page as fetch\ndef consume(spec):\n fetch('x')\n",
    )
    _, other_row = _observe(
        tmp_path,
        "class Other:\n"
        "    def page(self, query): pass\n"
        "def consume(other: Other):\n    other.page('x')\n",
    )

    assert alias_row.status == "FAIL" and alias_row.evaluation_proven
    assert other_row.status == "PASS" and other_row.evaluation_proven


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


def test_constructed_receiver_does_not_prove_a_mutated_method(tmp_path):
    _, row = _observe(
        tmp_path,
        "from .storage import Storage\ndef consume():\n    Storage().page('literal')\n",
        storage=(
            "class Storage:\n    def page(self, query): pass\n"
            "def replacement(self, query): pass\n"
            "def mutate(cls):\n    cls.page = replacement\n"
            "mutate(Storage)\n"
        ),
        target="sample.storage.Storage.page",
    )

    assert row.status.value == "UNKNOWN"
    assert not row.evaluation_proven
