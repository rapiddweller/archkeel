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


@pytest.mark.parametrize("name", HELPERS)
def test_helper_in_another_module_gets_the_verdict_of_a_helper_in_the_source(tmp_path, name):
    helper, call, expected = HELPERS[name]
    same_module = {
        "sample/core.py": f"def _effect():\n    return None\n\n{helper}\n"
        + GENERATE.format(call=call)
    }
    other_module = {
        "sample/util.py": f"def _effect():\n    return None\n\n{helper}\n",
        "sample/core.py": f"from .util import {call.partition('(')[0]}\n\n"
        + GENERATE.format(call=call),
    }
    inside = _verdict(tmp_path / "in", same_module, target="sample.core._effect")
    outside = _verdict(tmp_path / "out", other_module, target="sample.util._effect")
    assert (inside, outside) == (expected, expected)


def test_the_selected_source_does_not_change_the_verdict_for_the_same_helper(tmp_path):
    files = {
        "sample/util.py": "def _effect():\n    return None\n\n" + EFFECT_UNDER_FLAG,
        "sample/core.py": "from .util import _helper\n\n" + GENERATE.format(call="_helper(seeded)"),
    }
    narrow = _verdict(tmp_path / "narrow", files, target="sample.util._effect")
    wide = _verdict(tmp_path / "wide", files, target="sample.util._effect", source="sample")
    assert (narrow, wide) == (FAIL, FAIL)


@pytest.mark.parametrize(
    "mounted,expected",
    [("sample", FAIL), ("sample.core", UNKNOWN)],
    ids=["helper-inside-the-mount", "helper-outside-the-mount"],
)
def test_a_mounted_contract_sees_a_helper_only_inside_its_mount(tmp_path, mounted, expected):
    files = {
        "sample/util.py": "def _effect():\n    return None\n\n" + EFFECT_UNDER_FLAG,
        "sample/core.py": "from .util import _helper\n\n" + GENERATE.format(call="_helper(seeded)"),
    }
    assert _verdict(tmp_path, files, target="sample.util._effect", mounted=mounted) == expected


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


@pytest.mark.parametrize("name", REBINDINGS)
def test_rebinding_the_guarded_parameter_inside_the_branch(tmp_path, name):
    statement, expected = REBINDINGS[name]
    body = textwrap.indent(statement, "        ")
    source = (
        "def _effect():\n    return None\n\n"
        f"def generate(seeded: bool, other=False):\n    if seeded:\n{body}\n        _effect()\n"
    )
    files = {"sample/core.py": source}
    assert _verdict(tmp_path, files, target="sample.core._effect") == expected


def test_a_deleted_parameter_before_the_guard_makes_the_guard_unknown(tmp_path):
    source = (
        "def _effect():\n    return None\n\n"
        "def generate(seeded: bool):\n    del seeded\n    if seeded:\n        _effect()\n"
    )
    assert _verdict(tmp_path, {"sample/core.py": source}, target="sample.core._effect") == UNKNOWN


def test_a_deletion_after_the_effect_does_not_hide_the_proven_failure(tmp_path):
    source = (
        "def _effect():\n    return None\n\n"
        "def generate(seeded: bool):\n    if seeded:\n        _effect()\n        del seeded\n"
    )
    assert _verdict(tmp_path, {"sample/core.py": source}, target="sample.core._effect") == FAIL


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


def test_a_nested_function_that_rebinds_another_name_keeps_the_guard(tmp_path):
    source = """
    def _effect():
        return None

    def generate(seeded: bool, other=False):
        def clear():
            nonlocal other
            other = False
        if seeded:
            _effect()
    """
    assert _verdict(tmp_path, {"sample/core.py": source}, target="sample.core._effect") == FAIL


MEMBER_REBINDINGS = {
    "del_attribute": ("del self.seeded", UNKNOWN),
    "del_attribute_in_tuple": ("del (self.other, self.seeded)", UNKNOWN),
    "rebind_receiver": ("self = other", UNKNOWN),
    "del_receiver": ("del self", UNKNOWN),
    "import_as_receiver": ("import os as self", UNKNOWN),
    "assign_attribute": ("self.seeded = False", UNKNOWN),
    "del_other_attribute": ("del self.other", FAIL),
}


@pytest.mark.parametrize("name", MEMBER_REBINDINGS)
def test_rebinding_the_guarded_member_or_its_receiver_inside_the_branch(tmp_path, name):
    statement, expected = MEMBER_REBINDINGS[name]
    body = textwrap.indent(statement, "            ")
    source = (
        "def _effect():\n    return None\n\n"
        "class Generator:\n"
        "    def __init__(self):\n        self.seeded: bool = False\n\n"
        "    def generate(self, other=None):\n"
        f"        if self.seeded:\n{body}\n            _effect()\n"
    )
    files = {"sample/core.py": source}
    assert _verdict(tmp_path, files, target="sample.core._effect", condition=MEMBER) == expected
