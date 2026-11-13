# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

import pytest
from test_exact_module_ownership import _component, _observe_tree, _rule

from archkeel.ir.decisions import rule_assessments


@pytest.mark.parametrize(
    "helper", ["def public_helper(): _effect()", "@staticmethod\ndef _helper(): _effect()"]
)
def test_ineligible_resolved_local_helper_is_unknown_under_guard(tmp_path, helper):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
            )
        ],
    }
    name = "public_helper" if helper.startswith("def public") else "_helper"
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": (
                f"def _effect(): pass\n{helper}\ndef generate(seeded: bool):\n"
                f"    if seeded:\n        {name}()\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "UNKNOWN"
    assert not assessment.evaluation_proven
