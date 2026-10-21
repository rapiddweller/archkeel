# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

import pytest

from archkeel.ir.facts import GuardedEffectEvidence, RecordData, guarded_effect


def _fact(**changes):
    values = {
        "condition": {"kind": "parameter", "owner": "pkg.generate", "name": "seeded"},
        "condition_value": True,
        "condition_evidence_ids": ["ev-condition"],
        "path_evidence_ids": ["ev-branch"],
        "effect_binding_evidence_ids": ["ev-call-binding"],
        "complete": True,
        "unknown_reason": None,
        "helper_bindings": [],
    }
    values.update(changes)
    values["condition"] = RecordData(tuple(values["condition"].items()))
    return RecordData(
        tuple(
            (name, tuple(value) if isinstance(value, list) else value)
            for name, value in values.items()
        )
    )


def test_guarded_effect_fact_decodes_typed_declaration_and_path():
    result = guarded_effect(_fact())

    assert isinstance(result, GuardedEffectEvidence)
    assert result.condition.kind.value == "parameter"
    assert result.condition.owner == "pkg.generate"
    assert result.condition_value is True
    assert result.path_evidence_ids == ("ev-branch",)


def test_incomplete_guarded_effect_requires_an_unknown_reason():
    with pytest.raises(ValueError, match="unknown_reason"):
        guarded_effect(_fact(complete=False))


def test_guarded_effect_fact_rejects_unknown_fields():
    with pytest.raises(ValueError, match="fields"):
        guarded_effect(_fact(extra=True))


def test_guarded_effect_decodes_bound_helper_actual_token():
    helper = RecordData(
        (
            ("target", "pkg._helper"),
            ("call_id", "CALL-1"),
            (
                "arguments",
                (
                    RecordData(
                        (
                            ("argument_index", 0),
                            ("token_kind", "condition"),
                            ("token_value", None),
                            (
                                "condition",
                                RecordData(
                                    (
                                        ("kind", "parameter"),
                                        ("owner", "pkg.run"),
                                        ("name", "seeded"),
                                    )
                                ),
                            ),
                            ("evidence_ids", ("ev-actual",)),
                        )
                    ),
                ),
            ),
            ("evidence_ids", ("ev-helper",)),
        )
    )

    proof = guarded_effect(_fact(helper_bindings=[helper]))

    assert proof.helper_bindings[0].target == "pkg._helper"
    assert proof.helper_bindings[0].arguments[0].argument_index == 0
    assert proof.helper_bindings[0].arguments[0].condition.name == "seeded"
