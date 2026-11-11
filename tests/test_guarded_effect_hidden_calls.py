# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#758, #759: an effect in a class body or as a bare decorator never gives a proven PASS."""

from __future__ import annotations

import textwrap

import pytest
from test_guarded_effect_proofs import FAIL, UNKNOWN, _verdict

from archkeel.ir.decisions import RuleAssessmentStatus

SOURCE = """
    import os

    def _effect(value=None):
        return value

    def generate(seeded: bool):
        if seeded:
{body}
"""
HIDDEN = {
    # #758: the call is in a class body, so it has no guard facts of the function.
    "class_body_branch": "class Local:\n    if os.environ.get('X'):\n        _effect()",
    "class_body_conditional_expression": "class Local:\n    v = _effect() if True else None",
    "class_body_alias": "class Local:\n    f = _effect\n    f()",
    "class_body_plain_call": "class Local:\n    _effect()",
    # #759: a decorator application `@d def g` is `g = d(g)`, with no call node.
    "bare_function_decorator": "@_effect\ndef local():\n    return 1",
    "bare_class_decorator": "@_effect\nclass Local:\n    pass",
}


@pytest.mark.parametrize("name", HIDDEN)
def test_an_effect_that_has_no_guard_facts_never_gives_a_proven_pass(tmp_path, name):
    body = textwrap.indent(HIDDEN[name], " " * 12)
    files = {"sample/core.py": SOURCE.format(body=body)}
    verdict = _verdict(tmp_path, files, target="sample.core._effect")
    assert verdict[0] is not RuleAssessmentStatus.PASS
    assert verdict in {FAIL, UNKNOWN}
