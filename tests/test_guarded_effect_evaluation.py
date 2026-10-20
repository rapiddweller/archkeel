import copy
import json
from pathlib import Path

import pytest

from archkeel.check.evaluation.guarded_effects import guarded_effect_results
from archkeel.ir.codec import parse_contract
from archkeel.ir.facts import EvidenceClass
from archkeel.ir.facts_codec import classified

ROOT = Path(__file__).parents[1]


def _contract():
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_text())
    raw["schema_version"] = "3.13.0"
    raw["rules"] = [
        {
            "id": "NO-RANDOM-WHEN-SEEDED",
            "kind": "forbidden_effect_under_condition",
            "source": "sample.core",
            "target": "secrets.token_hex",
            "condition": {"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
            "rationale": "Seeded execution must not consume nondeterministic bytes.",
            "provenance": ["docs/policy.md"],
            "decided_by": "architect",
        }
    ]
    return parse_contract(raw)


def _record(item_id, kind, data, *, evidence_ids=()):
    return classified(
        item_id=item_id,
        evidence_class=EvidenceClass.FACT,
        area="calls",
        kind=kind,
        title=item_id,
        subjects=["sample.core.generate"],
        evidence_ids=list(evidence_ids),
        data=data,
    )


def _effect(value=True, *, complete=True):
    return {
        "condition": {"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
        "condition_value": value,
        "condition_evidence_ids": ["ev-condition"],
        "path_evidence_ids": ["ev-branch"],
        "effect_binding_evidence_ids": ["ev-binding"],
        "complete": complete,
        "unknown_reason": None if complete else "unsupported_path_or_mutation",
        "helper_bindings": [],
    }


def _inputs(value=True, *, complete=True):
    modules = [_record("module", "module", {"qualified_name": "sample.core"})]
    symbols = [
        _record(
            "function",
            "function",
            {
                "qualified_name": "sample.core.generate",
                "module": "sample.core",
                "parameters": [{"name": "seeded", "annotation": "bool"}],
            },
        )
    ]
    calls = [
        _record(
            "call",
            "resolved_call",
            {
                "source_scope": "sample.core.generate",
                "source_module": "sample.core",
                "call_binding": {
                    "origin": "direct",
                    "target": "secrets.token_hex",
                    "evidence_ids": ["ev-binding"],
                },
                "guarded_effect": [_effect(value, complete=complete)],
            },
        )
    ]
    return modules, symbols, calls


@pytest.mark.parametrize(
    "value,complete,expected",
    [(True, True, "FAIL"), (False, True, "PASS"), (None, True, "FAIL")],
)
def test_guarded_effect_policy_evaluates_only_true_condition_paths(value, complete, expected):
    modules, symbols, calls = _inputs(value, complete=complete)
    violations, limits, receipts = guarded_effect_results(
        _contract(),
        scope="root",
        calls=calls,
        modules=modules,
        symbols=symbols,
        complete=True,
        bindings_measured=True,
    )

    assert ("FAIL" if violations else "PASS") == expected
    assert not limits
    assert len(receipts) == 1


def test_guarded_effect_keeps_incomplete_path_unknown():
    modules, symbols, calls = _inputs(None, complete=False)
    violations, limits, _ = guarded_effect_results(
        _contract(),
        scope="root",
        calls=calls,
        modules=modules,
        symbols=symbols,
        complete=True,
        bindings_measured=True,
    )

    assert not violations
    assert len(limits) == 1
    assert limits[0]["evidence_class"] == "UNKNOWN"


def test_proven_failure_survives_a_sibling_unknown_path():
    modules, symbols, calls = _inputs(True)
    calls.append(
        _record(
            "unknown-call",
            "partially_resolved_call",
            {
                "source_scope": "sample.core.generate",
                "source_module": "sample.core",
                "call_binding": None,
                "guarded_effect": [_effect(None, complete=False)],
            },
        )
    )

    violations, limits, receipts = guarded_effect_results(
        _contract(),
        scope="root",
        calls=calls,
        modules=modules,
        symbols=symbols,
        complete=True,
        bindings_measured=True,
    )

    assert len(violations) == 1
    assert len(limits) == 1
    assert not receipts


def test_effect_without_a_path_inventory_is_unknown():
    modules, symbols, calls = _inputs(True)
    calls[0]["data"].pop("guarded_effect")

    violations, limits, receipts = guarded_effect_results(
        _contract(),
        scope="root",
        calls=calls,
        modules=modules,
        symbols=symbols,
        complete=True,
        bindings_measured=True,
    )

    assert not violations
    assert len(limits) == 1
    assert not receipts


def _helper_inputs(value=True):
    modules = [_record("module", "module", {"qualified_name": "sample.core"})]
    symbols = [
        _record(
            "caller-symbol",
            "function",
            {
                "qualified_name": "sample.core.generate",
                "module": "sample.core",
                "parameters": [{"name": "seeded", "annotation": "bool"}],
            },
        ),
        _record(
            "helper-symbol",
            "function",
            {
                "qualified_name": "sample.core._helper",
                "module": "sample.core",
                "parameters": [
                    {
                        "name": "flag",
                        "annotation": "bool",
                        "kind": "positional",
                        "default": None,
                        "default_known": True,
                    }
                ],
                "receiver_parameter": None,
                "visibility_detail": {"kind": "private"},
                "source_binding_unique": True,
                "source_binding_static": True,
                "decorators": [],
            },
        ),
    ]
    actual = {
        "argument_index": 0,
        "token_kind": "condition",
        "token_value": None,
        "condition": {"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
        "evidence_ids": ["ev-actual"],
    }
    outer = _effect(value)
    outer["effect_binding_evidence_ids"] = ["ev-helper-binding"]
    outer["helper_bindings"] = [
        {
            "target": "sample.core._helper",
            "call_id": "helper-call",
            "arguments": [actual],
            "evidence_ids": ["ev-helper-binding", "ev-actual"],
        }
    ]
    calls = [
        _record(
            "helper-call",
            "resolved_call",
            {
                "source_scope": "sample.core.generate",
                "source_module": "sample.core",
                "call_binding": {
                    "origin": "direct",
                    "target": "sample.core._helper",
                    "evidence_ids": ["ev-helper-binding"],
                },
                "call_arguments": [
                    {
                        "kind": "positional",
                        "keyword": None,
                        "value_kind": "other",
                        "value": None,
                        "evidence_ids": ["ev-actual"],
                    }
                ],
                "guarded_effect": [outer],
            },
        ),
        _record(
            "effect-call",
            "resolved_call",
            {
                "source_scope": "sample.core._helper",
                "source_module": "sample.core",
                "call_binding": {
                    "origin": "direct",
                    "target": "secrets.token_hex",
                    "evidence_ids": ["ev-effect-binding"],
                },
                "guarded_effect": [
                    {
                        "condition": {
                            "kind": "parameter",
                            "owner": "sample.core._helper",
                            "name": "flag",
                        },
                        "condition_value": True,
                        "condition_evidence_ids": ["ev-flag"],
                        "path_evidence_ids": ["ev-helper-branch"],
                        "effect_binding_evidence_ids": ["ev-effect-binding"],
                        "complete": True,
                        "unknown_reason": None,
                        "helper_bindings": [],
                    }
                ],
            },
        ),
    ]
    return modules, symbols, calls


def test_private_helper_binding_substitutes_the_callers_boolean_path():
    modules, symbols, calls = _helper_inputs(True)

    violations, limits, receipts = guarded_effect_results(
        _contract(),
        scope="root",
        calls=calls,
        modules=modules,
        symbols=symbols,
        complete=True,
        bindings_measured=True,
    )

    assert len(violations) == 1
    assert not limits
    assert len(receipts) == 1
    assert set(violations[0]["fact_ids"]) == {"helper-call", "helper-symbol", "effect-call"}


def test_helper_call_sites_keep_their_opposite_condition_paths():
    modules, symbols, calls = _helper_inputs(True)
    false_call = copy.deepcopy(calls[0])
    false_call["id"] = "helper-call-false"
    false_call["data"]["guarded_effect"][0]["condition_value"] = False
    false_call["data"]["guarded_effect"][0]["helper_bindings"][0]["call_id"] = "helper-call-false"
    calls.append(false_call)

    violations, limits, receipts = guarded_effect_results(
        _contract(),
        scope="root",
        calls=calls,
        modules=modules,
        symbols=symbols,
        complete=True,
        bindings_measured=True,
    )

    assert len(violations) == 1
    assert not limits
    assert len(receipts) == 1


def test_unbound_helper_actual_remains_unknown():
    modules, symbols, calls = _helper_inputs(True)
    calls[0]["data"]["call_arguments"][0]["kind"] = "starred_positional"

    violations, limits, receipts = guarded_effect_results(
        _contract(),
        scope="root",
        calls=calls,
        modules=modules,
        symbols=symbols,
        complete=True,
        bindings_measured=True,
    )

    assert not violations
    assert len(limits) == 1
    assert not receipts
