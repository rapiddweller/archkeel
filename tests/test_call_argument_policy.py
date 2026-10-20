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


def _contract(*, source="sample.caller", target="sample.storage.page"):
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
                "parameter": "query",
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
):
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "docs/architecture/sample.md": "Synthetic decision.\n",
        "contract.json": json.dumps(_contract(source=source, target=target)),
        "sample/__init__.py": "",
        "sample/storage.py": storage
        or ("class QuerySpec: pass\ndef page(query: QuerySpec, label: str = '') -> None: pass\n"),
        "sample/caller.py": caller,
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    contract = _contract(source=source, target=target)
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
    assert raw["schema_version"] == "2.5.0"
    assert parse_observation(raw).schema_version == "2.5.0"

    old = json.loads(json.dumps(raw))
    old["schema_version"] = "2.1.0"
    with pytest.raises(ValueError, match="call_arguments require"):
        parse_observation(old)

    incomplete = json.loads(json.dumps(raw))
    incomplete["calls"][0]["data"].pop("call_arguments")
    with pytest.raises(ValueError, match="explicit call_arguments"):
        parse_observation(incomplete)

    from test_result_schema import _validator

    validator = _validator("command-result-9.0.schema.json")
    current_schema = validator.evolve(schema={"$ref": "urn:archkeel:architecture-ir:decoded:2.5.0"})
    historical_schema = validator.evolve(
        schema={"$ref": "urn:archkeel:architecture-ir:decoded:2.1.0"}
    )
    assert current_schema.is_valid(raw)
    assert not historical_schema.is_valid(raw)


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
