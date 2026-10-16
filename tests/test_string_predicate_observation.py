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
        (
            ENUM + "def parse(value):\n    return value.startswith(Token.IMPORT.value)\n",
            "startswith",
        ),
    ],
)
def test_written_string_predicate_is_a_trace_valid_failure(tmp_path, source, form):
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert not result.diagnostics and result.observation is not None
    records = [
        row
        for row in result.observation.records("constructs")
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
        "def parse(value):\n    return value.startswith(compute_prefix())\n",
    ],
)
def test_predicate_observation_does_not_infer_runtime_or_unrelated_calls(tmp_path, source):
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert not result.diagnostics and result.observation is not None
    assert not result.observation.records("constructs")
    assert not trace_valid_violations(result.observation)


@pytest.mark.parametrize(
    ("source", "form"),
    [
        (
            ENUM + 'def parse(value):\n    return value.startswith(("x", Token.IMPORT))\n',
            "startswith",
        ),
        (
            'PREFIXES = ("import", "export")\n'
            'def parse(value):\n    return value.startswith(PREFIXES)\n',
            "startswith",
        ),
        (
            'PREFIXES = (b"import", b"export")\n'
            'def parse(value):\n    return value.endswith(PREFIXES)\n',
            "endswith",
        ),
        ('def parse(value, stop):\n    return value.startswith("import", 1, stop)\n', "startswith"),
    ],
)
def test_literal_prefix_vocabulary_cannot_hide_inside_a_tuple_or_range_call(tmp_path, source, form):
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert not result.diagnostics and result.observation is not None
    constructs = [
        row
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
    ]
    assert [row.data.get("form") for row in constructs] == [form]
    assert [(row.kind, row.rule_ids) for row in trace_valid_violations(result.observation)] == [
        ("forbidden_construct", ("RULE",))
    ]


@pytest.mark.parametrize(
    "source",
    [
        ENUM + "def parse(value):\n    return value.startswith((Token.IMPORT,))\n",
        'PREFIXES = ("import",)\n'
        'def parse(value, PREFIXES):\n    return value.startswith(PREFIXES)\n',
        'PREFIXES = ("import",)\nPREFIXES = read_prefixes()\n'
        'def parse(value):\n    return value.startswith(PREFIXES)\n',
        'PREFIXES = ("import",)\nother = PREFIXES\n'
        'def parse(value):\n    return value.startswith(PREFIXES)\n',
        'PREFIXES = ["import"]\ndef parse(value):\n    return value.startswith(PREFIXES)\n',
        'PREFIXES = {"import"}\ndef parse(value):\n    return value.startswith(PREFIXES)\n',
        'PREFIXES = tuple("import")\ndef parse(value):\n    return value.startswith(PREFIXES)\n',
        "PREFIXES = (compute_prefix(),)\n"
        "def parse(value):\n    return value.startswith(PREFIXES)\n",
        'PREFIXES = (("import",),)\ndef parse(value):\n    return value.startswith(PREFIXES)\n',
        'def parse(value):\n    return value.startswith(["import"])\n',
        'def parse(value):\n    return value.startswith({"import"})\n',
        "def parse(value):\n    return value.startswith(())\n",
        'def parse(value, prefix):\n    return value.startswith(prefix, "import")\n',
        'def parse(value, prefix):\n    return value.endswith(prefix, 0, "import")\n',
        'def parse(value):\n    return value.startswith(prefix="import")\n',
    ],
)
def test_unproven_collections_and_non_prefix_arguments_are_not_vocabulary(tmp_path, source):
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert not result.diagnostics and result.observation is not None
    assert not result.observation.records("constructs")
    assert not trace_valid_violations(result.observation)


def test_prefix_evidence_keeps_the_exact_written_call_and_native_span(tmp_path):
    source = 'def parse(value):\n    return value.startswith("import", 1)\n'
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert not result.diagnostics and result.observation is not None
    assert len(result.observation.records("constructs")) == 1
    [construct] = result.observation.records("constructs")
    evidence = {row.id: row for row in result.observation.evidence}
    [site] = [evidence[identity] for identity in construct.evidence_ids]
    assert (site.file, site.line, site.end_line, site.column, site.excerpt) == (
        "sample/core.py",
        2,
        2,
        11,
        '    return value.startswith("import", 1)',
    )
    assert construct.data.get("owner") == "sample.core.parse"
    assert construct.data.get("form") == "startswith"
    assert [(row.kind, row.rule_ids) for row in trace_valid_violations(result.observation)] == [
        ("forbidden_construct", ("RULE",))
    ]


def test_named_tuple_can_be_shared_by_membership_and_first_predicate_argument(tmp_path):
    source = (
        'PREFIXES = ("import", "export")\n'
        "def parse(value):\n"
        "    return value in PREFIXES or value.startswith(PREFIXES)\n"
    )
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert not result.diagnostics and result.observation is not None
    assert sorted(row.data.get("form") for row in result.observation.records("constructs")) == [
        "membership",
        "startswith",
    ]
    assert len(trace_valid_violations(result.observation)) == 2
