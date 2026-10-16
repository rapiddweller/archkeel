# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Written prefix/suffix grammar decisions use the existing native construct policy."""

import pytest
from test_analyzer import _observe_one_rule
from test_string_comparison_observation import ENUM, RULE

from archkeel.ir.trace import trace_valid_violations


@pytest.mark.parametrize(
    ("source", "form"),
    [
        ('def parse(value):\n    return value.startswith("import")\n', "startswith"),
        ('def parse(value):\n    return value.endswith(".ts")\n', "endswith"),
        ('def parse(value):\n    return value.startswith(b"import")\n', "startswith"),
        ('def parse(value):\n    return value.endswith((".ts", ".tsx"))\n', "endswith"),
        ('TOKEN = "import"\ndef parse(value):\n    return value.startswith(TOKEN)\n', "startswith"),
        (ENUM + "def parse(value):\n    return value.startswith(Token.IMPORT.value)\n", "startswith"),
    ],
)
def test_written_string_predicate_is_a_trace_valid_failure(tmp_path, source, form):
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert not result.diagnostics and result.observation is not None
    records = [
        row for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
    ]
    assert [row.data.get("form") for row in records] == [form]
    assert [(row.kind, row.rule_ids) for row in trace_valid_violations(result.observation)] == [
        ("forbidden_construct", ("RULE",))
    ]


@pytest.mark.parametrize(
    "source",
    [
        ENUM + "def parse(value):\n    return value.startswith(Token.IMPORT)\n",
        "def parse(value, prefix):\n    return value.startswith(prefix)\n",
        'TOKEN = "import"\ndef parse(value, TOKEN):\n    return value.startswith(TOKEN)\n',
        'def parse(value):\n    return value.transform("import")\n',
        'def parse(value):\n    return value.startswith(compute_prefix())\n',
    ],
)
def test_predicate_observation_does_not_infer_runtime_or_unrelated_calls(tmp_path, source):
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert not result.diagnostics and result.observation is not None
    assert not result.observation.records("constructs")
    assert not trace_valid_violations(result.observation)
