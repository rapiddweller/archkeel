import pytest
from test_analyzer import _parsed_module
from test_delta import _model, _record
from test_result_schema import _validator

from archkeel.analyzer.python.calls import collect_calls
from archkeel.analyzer.python.resolve import build_symbol_index
from archkeel.ir.codec import parse_observation


def test_collector_attaches_typed_condition_and_path_evidence_to_call():
    module = _parsed_module(
        """def target(seeded: bool):
    if seeded:
        forbidden()
"""
    )
    evidence = {}
    calls = collect_calls([module], build_symbol_index([]), evidence)

    proof = calls[0]["data"].get("guarded_effect")
    assert proof[0]["condition"] == {
        "kind": "parameter",
        "owner": "sample.mod.target",
        "name": "seeded",
    }
    assert proof[0]["condition_value"] is True
    assert proof[0]["condition_evidence_ids"]
    assert proof[0]["path_evidence_ids"]
    assert proof[0]["complete"] is False


def test_unannotated_parameter_does_not_become_a_boolean_condition():
    module = _parsed_module("def target(seeded):\n    if seeded:\n        forbidden()\n")

    calls = collect_calls([module], build_symbol_index([]), {})

    assert calls[0]["data"].get("guarded_effect") is None


def test_collector_binds_boolean_member_to_its_class_declaration():
    module = _parsed_module(
        """class Generator:
    def __init__(self):
        self.seeded: bool = False
    def target(self):
        if self.seeded:
            forbidden()
"""
    )

    calls = collect_calls([module], build_symbol_index([]), {})

    proof = calls[0]["data"].get("guarded_effect")
    assert proof[0]["condition"] == {
        "kind": "member",
        "owner": "sample.mod.Generator",
        "name": "seeded",
    }
    assert proof[0]["condition_value"] is True


def test_guarded_effect_facts_require_observation_2_8():
    raw = _model(git_head="a" * 40)
    raw["schema_version"] = "2.1.0"
    raw["calls"] = [
        _record(
            "effect",
            kind="call",
            data={
                "call_binding": None,
                "guarded_effect": [
                    {
                        "condition": {"kind": "parameter", "owner": "sample.run", "name": "seeded"},
                        "condition_value": True,
                        "condition_evidence_ids": ["e-condition"],
                        "path_evidence_ids": ["e-path"],
                        "effect_binding_evidence_ids": ["e-binding"],
                        "complete": False,
                        "unknown_reason": "missing_binding",
                        "helper_bindings": [],
                    }
                ],
            },
        )
    ]
    with pytest.raises(ValueError, match="observation 2.8.0"):
        parse_observation(raw)

    raw["schema_version"] = "2.8.0"
    raw["calls"][0]["data"]["call_arguments"] = []
    assert len(parse_observation(raw).records("calls")) == 1


def test_python_decoded_2_8_schema_admits_only_typed_guard_proofs():
    raw = _model(git_head="a" * 40)
    raw["schema_version"] = "2.8.0"
    raw["calls"] = [
        _record(
            "effect",
            kind="call",
            data={
                "source_scope": "sample.run",
                "source_module": "sample",
                "expression": "effect()",
                "status": "resolved",
                "targets": ["sample.effect"],
                "candidate_count": 1,
                "candidates_truncated": False,
                "reason": "",
                "target_evidence_ids": [],
                "call_binding": None,
                "call_arguments": [],
                "guarded_effect": [
                    {
                        "condition": {"kind": "parameter", "owner": "sample.run", "name": "seeded"},
                        "condition_value": True,
                        "condition_evidence_ids": ["e-condition"],
                        "path_evidence_ids": ["e-path"],
                        "effect_binding_evidence_ids": ["e-binding"],
                        "complete": False,
                        "unknown_reason": "missing_binding",
                        "helper_bindings": [],
                    }
                ],
            },
        )
    ]
    schema = {"$ref": "urn:archkeel:architecture-ir:python-decoded:2.8.0"}
    assert _validator("command-result-9.0.schema.json").evolve(schema=schema).is_valid(raw)
    malformed = raw.copy()
    malformed["calls"] = [raw["calls"][0].copy()]
    malformed["calls"][0]["data"] = raw["calls"][0]["data"].copy()
    malformed["calls"][0]["data"]["guarded_effect"][0]["extra"] = True
    assert (
        not _validator("command-result-9.0.schema.json").evolve(schema=schema).is_valid(malformed)
    )
