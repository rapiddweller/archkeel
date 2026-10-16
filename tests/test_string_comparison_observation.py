# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Native comparison observations cover protocol literals without inferring runtime values."""

import pytest
from test_analyzer import _observe_one_rule, _parsed_module

from archkeel.analyzer.python.constructs import collect_constructs
from archkeel.ir.trace import trace_valid_violations

RULE = {
    "kind": "forbidden_construct",
    "source": "sample.core",
    "constructs": ["string_literal_compare"],
}

ENUM = 'from enum import Enum as ProtocolEnum\nclass Token(ProtocolEnum):\n    IMPORT = "import"\n'


@pytest.mark.parametrize(
    ("source", "form"),
    [
        ('def parse(value):\n    return value == "import"\n', "compare"),
        (
            'from typing import Final\nIMPORT: Final[str] = "import"\n'
            "def parse(value):\n    return value == IMPORT\n",
            "compare",
        ),
        (
            'TOKENS = ("import", "export")\ndef parse(value):\n    return value in TOKENS\n',
            "membership",
        ),
        (
            'TOKENS = {"import", "export"}\ndef parse(value):\n    return value in TOKENS\n',
            "membership",
        ),
        (
            'TOKENS = ["import", "export"]\ndef parse(value):\n    return value in TOKENS\n',
            "membership",
        ),
        ('def parse(value):\n    return value == b"import"\n', "compare"),
        ('def parse(value):\n    return value in (b"import", b"export")\n', "membership"),
        (
            'def parse(value):\n    match value:\n        case b"import":\n'
            "            return True\n        case _:\n            return False\n",
            "match",
        ),
        (ENUM + "def parse(value):\n    return value == Token.IMPORT.value\n", "compare"),
        (
            ENUM + "def parse(value):\n    return value in (Token.IMPORT.value,)\n",
            "membership",
        ),
        (
            ENUM + "def parse(value):\n    match value:\n        case Token.IMPORT.value:\n"
            "            return True\n        case _:\n            return False\n",
            "match",
        ),
        ('if __name__ == "__main__":\n    pass\n', "compare"),
    ],
    ids=[
        "literal",
        "final",
        "named-tuple",
        "named-set",
        "named-list",
        "bytes-equality",
        "bytes-membership",
        "bytes-match",
        "enum-value",
        "enum-value-membership",
        "enum-value-match",
        "entry-protocol",
    ],
)
def test_native_protocol_literal_comparison_has_trace_valid_failure(tmp_path, source, form):
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert result.diagnostics == () and result.observation is not None
    comparisons = [
        row
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
    ]
    assert [row.data.get("form") for row in comparisons] == [form]
    violations = trace_valid_violations(result.observation)
    assert [(row.kind, row.rule_ids) for row in violations] == [("forbidden_construct", ("RULE",))]


@pytest.mark.parametrize(
    "source",
    [
        ENUM + "def parse(value):\n    return value is Token.IMPORT\n",
        "def parse(module: str, expected: str):\n    return module == expected\n",
        'TOKEN = "import"\ndef parse(value, TOKEN):\n    return value == TOKEN\n',
        'TOKEN = "import"\ndef parse(value):\n    TOKEN = value\n    return value == TOKEN\n',
        'TOKENS = ("import",)\ndef parse(value, TOKENS):\n    return value in TOKENS\n',
        'TOKENS = ("import",)\nTOKENS = read_tokens()\n'
        "def parse(value):\n    return value in TOKENS\n",
        'TOKENS = {"import"}\nTOKENS.add(read_token())\n'
        "def parse(value):\n    return value in TOKENS\n",
        'TOKENS = ["import"]\nother = TOKENS\nother.append(read_token())\n'
        "def parse(value):\n    return value in TOKENS\n",
        ENUM + "def parse(value, Token):\n    return value == Token.IMPORT.value\n",
        'class Other:\n    value = "import"\n'
        "def parse(value, Other):\n    return value == Other.value\n",
        'def parse(value):\n    match value:\n        case {"kind": _}:\n'
        "            return True\n        case _:\n            return False\n",
    ],
    ids=[
        "enum-identity",
        "name-data",
        "shadowed-scalar",
        "local-scalar",
        "shadowed-collection",
        "reassigned-collection",
        "mutated-set",
        "escaped-list",
        "shadowed-enum",
        "shadowed-class",
        "mapping-structure",
    ],
)
def test_native_controls_do_not_infer_literal_runtime_values(tmp_path, source):
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert result.diagnostics == () and result.observation is not None
    assert not [
        row
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
    ]
    assert trace_valid_violations(result.observation) == ()


def test_cross_module_imported_runtime_values_remain_an_explicit_limit(tmp_path):
    result = _observe_one_rule(
        tmp_path,
        RULE,
        {
            "core.py": "from sample.cli import TOKEN\n"
            "def parse(value):\n    return value == TOKEN\n",
            "cli.py": 'TOKEN = "import"\n',
        },
    )
    assert result.diagnostics == () and result.observation is not None
    assert not [
        row
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
    ]


def test_record_ids_are_distinct_and_collection_order_does_not_change_evidence():
    source = 'TOKENS = ("import",)\nvalue in TOKENS\nvalue == b"import"\n'
    parsed = _parsed_module(source)
    first = collect_constructs([parsed], {})
    second = collect_constructs([parsed], {})
    records = [row for row in first if row["kind"] == "string_literal_compare"]
    assert sorted(row["data"]["form"] for row in records) == ["compare", "membership"]
    assert len({row["id"] for row in records}) == 2
    assert first == second


@pytest.mark.parametrize(
    ("prefix", "base"),
    [
        ("class Enum:\n    pass\n", "Enum"),
        ("from enum import Enum as ProtocolEnum\nProtocolEnum = other_base\n", "ProtocolEnum"),
    ],
    ids=["unrelated-base", "rebound-import"],
)
def test_enum_value_requires_a_direct_stdlib_enum_base_import(tmp_path, prefix, base):
    source = (
        prefix + f'class Token({base}):\n    IMPORT = "import"\n'
        "def parse(value):\n    return value == Token.IMPORT.value\n"
    )
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert result.diagnostics == () and result.observation is not None
    assert not [
        row
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
    ]
