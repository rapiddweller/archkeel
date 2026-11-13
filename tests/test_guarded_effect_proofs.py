# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#619: a helper in another module and a rebound guard name must not give a false proof."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from test_exact_module_ownership import _component, _observe_tree, _rule

from archkeel.check.report import run_saved_report
from archkeel.ir.codec import encode_canonical_model, observation_payload
from archkeel.ir.decisions import RuleAssessmentStatus, rule_assessments

PARAMETER = {"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"}
MEMBER = {"kind": "member", "owner": "sample.core.Generator", "name": "seeded"}
FAIL = (RuleAssessmentStatus.FAIL, True)
PASS = (RuleAssessmentStatus.PASS, True)
UNKNOWN = (RuleAssessmentStatus.UNKNOWN, False)
FAIL_WITH_UNKNOWN_SIBLING = (RuleAssessmentStatus.FAIL, False)


def _verdict(
    tmp_path: Path,
    files: dict[str, str],
    *,
    target: str,
    source: str = "sample.core",
    condition: dict[str, str] = PARAMETER,
    mounted: str | None = None,
) -> tuple[RuleAssessmentStatus, bool]:
    """Collect, decode and evaluate the files, then replay the saved report: both must agree."""
    rule = _rule(
        "forbidden_effect_under_condition", source=source, target=target, condition=condition
    )
    contract: dict[str, object] = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [rule],
    }
    if mounted is not None:
        # The rule lives in a mounted contract, so the evaluator only sees the mounted modules.
        contract = {
            "schema_version": "3.13.0",
            "components": [_component("all", [mounted], inside="inside.json")],
            "rules": [],
        }
        inside = {
            "schema_version": "3.13.0",
            "components": [_component("inside", [mounted])],
            "rules": [rule],
        }
        files = {**files, "inside.json": json.dumps(inside)}
    result = _observe_tree(
        tmp_path,
        {"sample/__init__.py": "", **{k: textwrap.dedent(v) for k, v in files.items()}},
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [row] = rule_assessments(result.observation, undecided_by_rule={})
    saved = tmp_path / "report.json"
    saved.write_text(json.dumps(encode_canonical_model(observation_payload(result.observation))))
    [replayed] = run_saved_report(saved).rule_assessments
    assert (replayed.status, replayed.evaluation_proven) == (row.status, row.evaluation_proven)
    return row.status, row.evaluation_proven


# --- item a: the helper walk uses every call, not only the calls of the selected source ---

EFFECT_UNDER_FLAG = "def _helper(flag: bool):\n    if flag:\n        _effect()\n"
HELPERS = {
    "public_helper_has_no_binding": (
        "def helper(flag: bool):\n    if flag:\n        _effect()\n",
        "helper(seeded)",
        UNKNOWN,
    ),
    "effect_under_flag": (EFFECT_UNDER_FLAG, "_helper(seeded)", FAIL),
    "effect_under_negated_flag": (
        "def _helper(flag: bool):\n    if not flag:\n        _effect()\n",
        "_helper(seeded)",
        PASS,
    ),
    "unconditional_effect_false_actual": (
        "def _helper(flag: bool):\n    _effect()\n",
        "_helper(False)",
        FAIL,
    ),
    "keyword_actual": (EFFECT_UNDER_FLAG, "_helper(flag=seeded)", FAIL),
    "no_call_in_helper": ("def _helper(flag: bool):\n    return flag\n", "_helper(seeded)", PASS),
    "other_call_only": ("def _helper(flag: bool):\n    print(flag)\n", "_helper(seeded)", UNKNOWN),
    "unbound_actual_without_effect_proof": (EFFECT_UNDER_FLAG, "_helper(seeded or other)", UNKNOWN),
    "false_actual_by_negation": (EFFECT_UNDER_FLAG, "_helper(not seeded)", PASS),
}
GENERATE = "def generate(seeded: bool, other=False):\n    if seeded:\n        {call}\n"


# --- item d: any rebinding of the guarded name makes the guard unknown ---

REBINDINGS = {
    # Forms that rebind the parameter without an ast.Store target.
    "del": ("del seeded", UNKNOWN),
    "del_parenthesized": ("del (seeded)", UNKNOWN),
    "del_with_other_name": ("del seeded, other", UNKNOWN),
    "del_tuple_target": ("del (other, seeded)", UNKNOWN),
    "del_list_target": ("del [seeded]", UNKNOWN),
    "import": ("import seeded", UNKNOWN),
    "import_dotted": ("import seeded.sub", UNKNOWN),
    "import_as": ("import os as seeded", UNKNOWN),
    "from_import": ("from os import seeded", UNKNOWN),
    "from_import_as": ("from os import path as seeded", UNKNOWN),
    "def": ("def seeded():\n    pass", UNKNOWN),
    "async_def": ("async def seeded():\n    pass", UNKNOWN),
    "class": ("class seeded:\n    pass", UNKNOWN),
    "walrus_in_default": ("def inner(a=(seeded := False)):\n    pass", UNKNOWN),
    # Forms that already worked: the control group.
    "assign": ("seeded = False", UNKNOWN),
    "augmented_assign": ("seeded &= other", UNKNOWN),
    "tuple_assign": ("seeded, other = other, seeded", UNKNOWN),
    "walrus": ("(seeded := False)", UNKNOWN),
    "for_target": ("for seeded in (1,):\n    pass", UNKNOWN),
    "with_target": ("with open('f') as seeded:\n    pass", UNKNOWN),
    "except_as": ("try:\n    pass\nexcept ValueError as seeded:\n    pass", UNKNOWN),
    # Forms that keep the guard: the boundary group.
    "no_op": ("pass", FAIL),
    # The other path keeps the guard: the violation stays, a sibling path is unknown.
    "del_in_one_path_of_nested_if": ("if other:\n    del seeded", FAIL_WITH_UNKNOWN_SIBLING),
    "del_other_name": ("del other", FAIL),
    "del_attribute_of_guard": ("del seeded.attr", FAIL),
    "del_item_of_guard": ("del seeded[0]", FAIL),
    "import_other_name": ("import os", FAIL),
    "def_other_name": ("def inner():\n    pass", FAIL),
    "class_other_name": ("class Inner:\n    pass", FAIL),
    "del_in_nested_def_body": ("def inner():\n    seeded = 1\n    del seeded", FAIL),
}


NONLOCAL_CLEARS_THE_GUARD = """
    def _effect():
        return None

    def generate(seeded: bool, other=False):
        def clear():
            nonlocal {names}
            seeded = False
        if seeded:
            clear()
            _effect()
"""


@pytest.mark.parametrize("names", ["seeded", "other, seeded", "seeded, other"])
def test_a_nested_function_that_rebinds_the_parameter_makes_the_guard_unknown(tmp_path, names):
    files = {"sample/core.py": NONLOCAL_CLEARS_THE_GUARD.format(names=names)}
    status, _ = _verdict(tmp_path, files, target="sample.core._effect")
    assert status is RuleAssessmentStatus.UNKNOWN


MEMBER_REBINDINGS = {
    "del_attribute": ("del self.seeded", UNKNOWN),
    "del_attribute_in_tuple": ("del (self.other, self.seeded)", UNKNOWN),
    "rebind_receiver": ("self = other", UNKNOWN),
    "del_receiver": ("del self", UNKNOWN),
    "import_as_receiver": ("import os as self", UNKNOWN),
    "assign_attribute": ("self.seeded = False", UNKNOWN),
    "del_other_attribute": ("del self.other", FAIL),
}


# A class body runs when the class statement runs, so it can change the guard like any statement.
CLASS_BODY_REBINDINGS = {
    "opaque_call": "self.reset()",
    "assign_attribute": "self.seeded = False",
    "plain_class_attribute": "limit = 1",
}


# A definition header runs when the statement runs, before the body: a call there can change the
# guard. A decorated definition or a metaclass keyword already gives UNKNOWN end to end for another
# reason, so those forms (and the bare decorator and the `metaclass=` keyword, which are calls
# without a call node) are checked on the walker in test_guard_path_classes.py. An annotation runs
# at definition time only before Python 3.14 and without the `__future__` import; a deferred
# annotation gives a false UNKNOWN, never a false proof.
HEADERS = {
    "default": ("def local(a=self.reset()):\n    return a", UNKNOWN),
    "keyword_default": ("def local(*, a=self.reset()):\n    return a", UNKNOWN),
    "async_default": ("async def local(a=self.reset()):\n    return a", UNKNOWN),
    "lambda_default": ("local = lambda a=self.reset(): a", UNKNOWN),
    "class_base": ("class Local(make(self.reset())):\n    pass", UNKNOWN),
    "two_calls_in_header": ("def local(a=self.reset(), b=other()):\n    return a", UNKNOWN),
    "annotation": ("def local(a: self.reset()):\n    return a", UNKNOWN),
    "return_annotation": ("def local() -> self.reset():\n    return 1", UNKNOWN),
    "vararg_annotation": ("def local(*a: self.reset()):\n    return a", UNKNOWN),
    "kwarg_annotation": ("def local(**a: self.reset()):\n    return a", UNKNOWN),
    "harmless_annotation": ("def local(a: int) -> int:\n    return a", FAIL),
    "harmless_default": ("def local(a=1):\n    return a", FAIL),
    "harmless_class_fields": ("class Local:\n    limit = 1\n    names = ('a', 'b')", FAIL),
    "class_hook_base": ("class Local(Base):\n    pass", UNKNOWN),
    "class_hook_metaclass": ("class Local(metaclass=Meta):\n    pass", UNKNOWN),
    "class_hook_set_name": ("class Local:\n    field = shared", UNKNOWN),
}


# Accepted cost: a class-local store of the guard name does not change the guard in Python, but
# the walker cannot tell it from a store in the enclosing scope, so the verdict is UNKNOWN.


# After the body, a class statement runs hooks that have no call node in the source:
# __init_subclass__ of a base, a metaclass __new__ or __init__, and __set_name__ of a body value.
# Such a hook can set the member, so a value from before or inside the class is not safe.


# The evaluator already gives UNKNOWN for a class body that holds a guard branch, so only the
# `global` form shows a wrong value end to end; the forms with a later binding keep a mutation
# reason on every path and stay UNKNOWN. The walker tests in test_guard_path_classes.py cover
# the branch values inside the body.
# A class body has its own name scope. A name that the body declares `global` or binds anywhere is
# not the guard, so a branch on it in the body must not set the guard value after the class.
PARAMETER_SCOPING = """
    def _effect():
        return None

    def generate(seeded: bool, other=None):
        if {outer}:
            class Local:
{body}
            _effect()
"""
CLASS_SCOPING = {
    # The read in the branch is the module global, not the parameter: a wrong PASS (false value).
    "global_read": ("other", "global seeded\nif seeded:\n    raise ValueError", UNKNOWN),
    # A later store makes the name class-local, so the earlier read is not the parameter either.
    "store_after_read": ("seeded", "if seeded:\n    other = 1\nseeded = other", UNKNOWN),
    "for_after_read": (
        "seeded",
        "if seeded:\n    other = 1\nfor seeded in range(3):\n    pass",
        UNKNOWN,
    ),
    "import_after_read": ("seeded", "if seeded:\n    other = 1\nimport os as seeded", UNKNOWN),
    "def_after_read": ("seeded", "if seeded:\n    other = 1\ndef seeded():\n    pass", UNKNOWN),
    "nonlocal_read": ("seeded", "nonlocal seeded\nif seeded:\n    other = 1", UNKNOWN),
    "plain_fields": ("seeded", "limit = 1", FAIL),
}


MEMBER_SCOPING = {
    "rebound_after_read": ("other", "if self.seeded:\n    limit = 1\nself = other", UNKNOWN),
    "global_receiver": (
        "other",
        "global self\nif self.seeded:\n    raise ValueError",
        UNKNOWN,
    ),
}
