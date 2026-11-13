# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The own dependency policy rejects string dispatch in real source."""

from test_dependency_api_target import _dependency_contract

from archkeel.ir.decisions import rule_assessments

GUARD = "DEPENDENCY-TYPED-CONTROL"


def _guard(model):
    return next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == GUARD)


def test_the_native_guard_comes_from_the_own_contract_without_exemptions():
    rule = next(row for row in _dependency_contract()["rules"] if row["id"] == GUARD)
    assert rule["source"] == "archkeel.ir.dependency"
    assert rule["constructs"] == ["string_literal_compare"]
    assert not rule.get("allowed_sources") and not rule.get("exact_sources")
