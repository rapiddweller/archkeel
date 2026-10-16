# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Single local literal bindings are syntax evidence, not general value inference."""

import pytest
from test_analyzer import _observe_one_rule

from archkeel.ir.trace import trace_valid_violations

_RULE = {
    "kind": "forbidden_construct",
    "source": "sample.core",
    "constructs": ["string_literal_compare"],
}


@pytest.mark.parametrize(
    ("statement", "expression", "form"),
    [
        ('flag = "--json"', "flag in value", "membership"),
        ('flag = "--json"', "flag not in value", "membership"),
        ('flag = "--json"; ready = True', "flag in value", "membership"),
        ('flag = b"--json"', "flag in value", "membership"),
        ('flag = "--json"', "value == flag", "compare"),
        ('flag = "--json"', "flag != value", "compare"),
        ('flag: str = "--json"', "flag in value", "membership"),
        ('flag = ""', "flag in value", "membership"),
        ('other = flag = "--json"', "flag in value", "membership"),
    ],
)
def test_single_local_literal_produces_trace_valid_failure(tmp_path, statement, expression, form):
    source = f"def parse(value):\n    {statement}\n    return {expression}\n"
    result = _observe_one_rule(tmp_path, _RULE, {"core.py": source})
    assert result.diagnostics == () and result.observation is not None
    comparisons = [
        row.data.get("form")
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
    ]
    assert comparisons == [form]
    assert [(row.kind, row.rule_ids) for row in trace_valid_violations(result.observation)] == [
        ("forbidden_construct", ("RULE",))
    ]


@pytest.mark.parametrize(
    "source",
    [
        'def parse(value, flag="--json"):\n    return flag in value\n',
        'def parse(value):\n    flag = "--json"\n    flag = value\n    return flag in value\n',
        'def parse(value, ready):\n    if ready:\n        flag = "--json"\n    return flag in value\n',
        'def parse(value):\n    return flag in value\n    flag = "--json"\n',
        'def outer(value):\n    flag = "--json"\n    def parse():\n        return flag in value\n',
        'def parse(value):\n    global flag\n    flag = "--json"\n    return flag in value\n',
        'def outer(value):\n    flag = "--json"\n    def parse():\n        nonlocal flag\n        return flag in value\n',
        'def parse(value):\n    if (flag := "--json"):\n        return flag in value\n',
        'def parse(value):\n    flag = "--json"\n    del flag\n    return flag in value\n',
        'def parse(value):\n    flag, other = ("--json", "--yaml")\n    return flag in value\n',
    ],
)
def test_ambiguous_or_other_scope_values_do_not_gain_literal_evidence(tmp_path, source):
    result = _observe_one_rule(tmp_path, _RULE, {"core.py": source})
    assert result.diagnostics == () and result.observation is not None
    assert not [
        row
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
    ]
    assert trace_valid_violations(result.observation) == ()
