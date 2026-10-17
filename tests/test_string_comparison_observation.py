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
        (
            'TOKENS = ("import", "export")\ndef parse(value):\n    return value not in TOKENS\n',
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
        "named-not-in",
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


@pytest.mark.parametrize("expression", ["value == TOKEN", "TOKEN in value", "TOKEN not in value"])
def test_cross_module_imported_runtime_values_remain_an_explicit_limit(tmp_path, expression):
    result = _observe_one_rule(
        tmp_path,
        RULE,
        {
            "core.py": "from sample.cli import TOKEN\n"
            f"def parse(value):\n    return {expression}\n",
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


@pytest.mark.parametrize(
    "source",
    [
        'TOKENS = alias = ["import"]\nalias.clear()\n'
        "def parse(value):\n    return value in TOKENS\n",
        'holder.tokens = TOKENS = ["import"]\nholder.tokens.clear()\n'
        "def parse(value):\n    return value in TOKENS\n",
        'TOKENS = ("import",)\n'
        "def parse(value, expected):\n    return value in TOKENS == expected\n",
        'TOKENS = ("import",)\ndef parse(value, others):\n    return value in TOKENS in others\n',
    ],
    ids=[
        "chained-name-assignment",
        "chained-attribute-assignment",
        "equality-role",
        "membership-left-role",
    ],
)
def test_native_collection_alias_and_chained_roles_are_unclassified(tmp_path, source):
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert result.diagnostics == () and result.observation is not None
    assert not [
        row
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
    ]
    assert trace_valid_violations(result.observation) == ()


@pytest.mark.parametrize(
    "source",
    [
        'def parse(path):\n    return "node_modules" in path.split("/")\n',
        'def parse(text):\n    return "import" not in text\n',
        'def parse(content):\n    return b"import" in content\n',
        'def parse(content):\n    return b"import" not in content\n',
        'NEEDLE = "import"\ndef parse(values):\n    return NEEDLE in values\n',
        'from typing import Final\nNEEDLE: Final[str] = "import"\n'
        "def parse(values):\n    return NEEDLE not in values\n",
        'NEEDLE = b"import"\ndef parse(values):\n    return NEEDLE in values\n',
        'class Words:\n    IMPORT = "import"\n'
        "def parse(values):\n    return Words.IMPORT in values\n",
        ENUM + "def parse(values):\n    return Token.IMPORT.value in values\n",
    ],
    ids=[
        "parser-literal-needle",
        "not-in-text",
        "bytes-needle",
        "not-in-bytes",
        "module-scalar",
        "final-scalar-not-in",
        "module-bytes",
        "class-scalar",
        "enum-value",
    ],
)
def test_native_literal_membership_needles_have_trace_valid_failures(tmp_path, source):
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert result.diagnostics == () and result.observation is not None
    comparisons = [
        row
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
    ]
    assert [row.data.get("form") for row in comparisons] == ["membership"]
    assert [(row.kind, row.rule_ids) for row in trace_valid_violations(result.observation)] == [
        ("forbidden_construct", ("RULE",))
    ]


@pytest.mark.parametrize(
    "source",
    [
        ENUM + "def parse(values):\n    return Token.IMPORT in values\n",
        "def parse(needle: str, values: tuple[str, ...]):\n    return needle in values\n",
        'NEEDLE = "import"\ndef parse(NEEDLE, values):\n    return NEEDLE in values\n',
        'NEEDLE = "import"\ndef parse(values):\n'
        "    NEEDLE = read_word()\n    return NEEDLE in values\n",
        "NEEDLE = read_word()\ndef parse(values):\n    return NEEDLE in values\n",
    ],
    ids=["enum-needle", "data-needle", "shadowed-scalar-needle", "local-needle", "dynamic-needle"],
)
def test_native_typed_or_unproven_membership_needles_have_no_literal_claim(tmp_path, source):
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert result.diagnostics == () and result.observation is not None
    assert not [
        row
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
    ]
    assert trace_valid_violations(result.observation) == ()


@pytest.mark.parametrize(
    "source",
    [
        "from enum import Enum\n"
        "class Mixin:\n    @property\n    def value(self):\n        return 7\n"
        'class Token(Mixin, Enum):\n    IMPORT = "import"\n',
        "from enum import Enum\nclass Token(Enum):\n"
        "    def __new__(cls, written):\n"
        "        obj = object.__new__(cls)\n        obj._value_ = len(written)\n"
        '        return obj\n    IMPORT = "import"\n',
        "from enum import Enum\nclass Token(Enum):\n"
        "    def __init__(self, written):\n        self._value_ = len(written)\n"
        '    IMPORT = "import"\n',
        "from enum import Enum\nclass Token(Enum):\n"
        "    def __getattribute__(self, name):\n"
        '        return {"value": 7}.get(name, object.__getattribute__(self, name))\n'
        '    IMPORT = "import"\n',
        "from enum import Enum\nclass Token(Enum):\n"
        "    def __setattr__(self, name, value):\n"
        '        object.__setattr__(self, name, {"_value_": 7}.get(name, value))\n'
        '    IMPORT = "import"\n',
        "from enum import Enum, EnumType\nclass ChangingEnumType(EnumType):\n"
        "    def __new__(cls, name, bases, namespace):\n"
        '        dict.__setitem__(namespace, "IMPORT", 7)\n'
        "        return super().__new__(cls, name, bases, namespace)\n"
        'class Token(Enum, metaclass=ChangingEnumType):\n    IMPORT = "import"\n',
        "from enum import Enum\ndef change(cls):\n"
        "    cls.IMPORT._value_ = 7\n    return cls\n"
        '@change\nclass Token(Enum):\n    IMPORT = "import"\n',
        'from enum import IntEnum\nclass Token(IntEnum):\n    IMPORT = "1"\n',
        "from enum import Enum\nclass Token(Enum):\n"
        "    @property\n    def value(self):\n        return 7\n"
        '    IMPORT = "import"\n',
        "from enum import Enum\nclass Token(Enum):\n"
        '    _ignore_ = "IMPORT"\n    IMPORT = "import"\n',
    ],
    ids=[
        "mixin-value",
        "custom-new",
        "custom-init",
        "custom-getattribute",
        "custom-setattr",
        "metaclass-keyword",
        "class-decorator",
        "intenum-conversion",
        "own-value",
        "namespace-ignore",
    ],
)
def test_native_custom_enum_does_not_establish_string_value(tmp_path, source):
    source += "def parse(values):\n    return Token.IMPORT.value in values\n"
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert result.diagnostics == () and result.observation is not None
    assert not [
        row
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
    ]
    assert trace_valid_violations(result.observation) == ()


@pytest.mark.parametrize("base", ["Enum", "StrEnum"])
def test_native_simple_enum_retains_literal_value_evidence(tmp_path, base):
    source = (
        f"from enum import {base}\nclass Token({base}):\n"
        '    """Ordinary literal enum members."""\n    IMPORT = "import"\n'
        '    EXPORT = "export"\n'
        "def parse(values):\n    return Token.IMPORT.value in values\n"
    )
    result = _observe_one_rule(tmp_path, RULE, {"core.py": source})
    assert result.diagnostics == () and result.observation is not None
    assert [
        row.data.get("form")
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
    ] == ["membership"]
    assert [(row.kind, row.rule_ids) for row in trace_valid_violations(result.observation)] == [
        ("forbidden_construct", ("RULE",))
    ]


# Qualified sources select real declarations, not merely their containing module.
@pytest.mark.parametrize(
    ("scope", "source"),
    [
        ("sample.core.parse", "def parse(value):\n    return value is None\n"),
        (
            "sample.core.Box",
            "class Box:\n    def parse(self, value):\n        return value is None\n",
        ),
        (
            "sample.core.Box.parse",
            "class Box:\n    def parse(self, value):\n        return value is None\n",
        ),
    ],
)
def test_qualified_construct_owner_has_receipt_and_real_mutation_fails(tmp_path, scope, source):
    from test_analyzer import _observe

    from archkeel.ir.decisions import rule_assessments

    safe = source + '\ndef outside(value):\n    return value == "outside"\n'
    result = _observe_one_rule(tmp_path, RULE | {"source": scope}, {"core.py": safe})
    assert result.diagnostics == () and result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "PASS" and assessment.evaluation_proven
    receipts = [
        row
        for row in result.observation.records("scope_observations") or ()
        if row.kind == "rule_evaluation" and row.rule_ids == ("RULE",)
    ]
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.subjects and all(
        name == scope or name.startswith(scope + ".") for name in receipt.subjects
    )
    symbols = {row.id: row for row in result.observation.records("symbols") or ()}
    assert receipt.fact_ids and all(identity in symbols for identity in receipt.fact_ids)
    assert set(receipt.subjects) == {
        symbols[identity].data.get("qualified_name") for identity in receipt.fact_ids
    }
    contract = (tmp_path / "contract.json").read_bytes()
    (tmp_path / "sample/core.py").write_text(safe.replace("value is None", 'value == "import"', 1))
    changed = _observe(tmp_path)
    assert changed.diagnostics == () and changed.observation is not None
    findings = trace_valid_violations(changed.observation)
    assert len(findings) == 1 and findings[0].rule_ids == ("RULE",)
    [failed] = rule_assessments(changed.observation, undecided_by_rule={})
    assert failed.status == "FAIL"
    assert (tmp_path / "contract.json").read_bytes() == contract


@pytest.mark.parametrize("scope", ["sample.core.missing", "sample.core.pars", "sample.core.Boxes"])
def test_missing_or_near_sibling_construct_owner_remains_unknown(tmp_path, scope):
    from archkeel.ir.decisions import rule_assessments

    result = _observe_one_rule(
        tmp_path,
        RULE | {"source": scope},
        {
            "core.py": "class Box:\n    pass\ndef parse(value):\n    return value\n",
        },
    )
    assert result.exit_code == 2 and result.observation is not None
    assert any(row.kind == "rule_without_subjects" for row in result.diagnostics)
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "UNKNOWN" and not assessment.evaluation_proven
    assert not any(
        row.kind == "rule_evaluation" and row.rule_ids == ("RULE",)
        for row in result.observation.records("scope_observations") or ()
    )


def test_qualified_construct_owner_does_not_turn_incomplete_scan_into_pass(tmp_path):
    from archkeel.ir.decisions import rule_assessments

    result = _observe_one_rule(
        tmp_path,
        RULE | {"source": "sample.core.parse"},
        {
            "core.py": "def parse(value):\n    return value is None\n",
            "broken.py": "def broken(:\n",
        },
    )
    assert result.exit_code == 2 and result.observation is not None
    assert not any(row.kind == "rule_without_subjects" for row in result.diagnostics)
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "UNKNOWN" and not assessment.evaluation_proven


def test_qualified_construct_receipt_requires_actual_symbol_and_clipped_module_evidence(tmp_path):
    import copy
    import json
    from dataclasses import replace
    from inspect import signature

    from archkeel.check.evaluation.rules import rule_evaluation_facts, rule_subject_failures
    from archkeel.ir.codec import parse_contract
    from archkeel.ir.facts_codec import raw_record
    from archkeel.ir.profiles import PYTHON

    result = _observe_one_rule(tmp_path, RULE, {"core.py": "def parse(value):\n    return value\n"})
    assert result.observation is not None
    modules = tuple(raw_record(row) for row in result.observation.records("modules") or ())
    symbols = tuple(raw_record(row) for row in result.observation.records("symbols") or ())
    contract = parse_contract(json.loads((tmp_path / "contract.json").read_text()))
    contract = replace(contract, rules=(replace(contract.rules[0], source="sample.core.parse"),))
    arguments = dict(
        profile=PYTHON,
        scope="root",
        modules=modules,
        source_modules=None,
        blank_modules=frozenset(),
        receipt_scope_complete=True,
    )
    assert rule_evaluation_facts(contract, **arguments) == []
    assert "symbols" in signature(rule_evaluation_facts).parameters
    [receipt] = rule_evaluation_facts(contract, symbols=symbols, **arguments)
    assert receipt["subjects"] == ["sample.core.parse"]
    assert receipt["fact_ids"]
    assert not rule_subject_failures(
        contract.rules, {"sample.core"}, symbols=symbols, type_shapes={}
    )
    assert (
        rule_evaluation_facts(
            contract,
            symbols=symbols,
            **(arguments | {"source_modules": frozenset({"sample.other"})}),
        )
        == []
    )
    assert rule_subject_failures(
        contract.rules,
        {"sample.core"},
        symbols=symbols,
        source_modules=frozenset({"sample.other"}),
        type_shapes={},
    )
    for field, value in [
        ("kind", "vendor.future"),
        ("kind", "attribute"),
        ("module", "sample.other"),
        ("qualified_name", "sample.other.parse"),
    ]:
        invalid = copy.deepcopy(symbols)
        for symbol in invalid:
            if field == "kind":
                symbol["kind"] = value
            else:
                symbol["data"][field] = value
        assert rule_evaluation_facts(contract, symbols=invalid, **arguments) == []
        assert rule_subject_failures(
            contract.rules,
            {"sample.core"},
            symbols=invalid,
            type_shapes={},
        )

    # RawData is a mutable JSON dict. Its stored fields, as serialized on the wire,
    # must decide ownership even if an accepted dict subclass overrides get().
    class SpoofedOwner(dict):
        def get(self, key, default=None):
            return {
                "module": "sample.core",
                "qualified_name": "sample.core.parse",
            }.get(key, default)

    spoofed = copy.deepcopy(symbols)
    for symbol in spoofed:
        symbol["data"] = SpoofedOwner(
            symbol["data"]
            | {"module": "sample.other", "qualified_name": "sample.other.parse"}
        )
        assert json.loads(json.dumps(symbol["data"]))["module"] == "sample.other"
    assert rule_evaluation_facts(contract, symbols=spoofed, **arguments) == []
    assert rule_subject_failures(
        contract.rules, {"sample.core"}, symbols=spoofed, type_shapes={}
    )


def test_real_report_evaluates_a_qualified_construct_owner(tmp_path):
    from test_inside_rule_coverage import _commit_test_root

    from archkeel.check.ports import ScanConfig
    from archkeel.check.report import run_report
    from archkeel.cli.observe import observe

    _observe_one_rule(
        tmp_path,
        RULE | {"source": "sample.core.parse"},
        {
            "core.py": "def parse(value):\n    return value is None\n",
        },
    )
    _commit_test_root(tmp_path)
    result, packet = run_report(
        tmp_path,
        config=ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        analyzer=observe,
    )
    assert result.exit_code == 0 and result.diagnostics == () and packet is not None
    assert result.rule_assessments and all(row.status == "PASS" for row in result.rule_assessments)


@pytest.mark.parametrize("scope", ["sample.core.a.parse", "sample.foreign.parse"])
def test_inside_qualified_construct_owner_respects_actual_parent_scope(tmp_path, scope):
    import json

    from test_analyzer import _component, _observe
    from test_inside_rule_coverage import _write_inside_case

    from archkeel.ir.decisions import rule_assessments

    _write_inside_case(
        tmp_path,
        rules=[
            RULE
            | {
                "id": "RULE",
                "source": scope,
                "rationale": "Check the actual named owner within this parent.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    )
    (tmp_path / "sample/core/a.py").write_text(
        "def parse(value):\n    return value is None\n"
        'def outside(value):\n    return value == "outside"\n'
    )
    (tmp_path / "sample/foreign.py").write_text("def parse(value):\n    return value\n")
    path = tmp_path / "contract.json"
    outer = json.loads(path.read_text())
    outer["components"].append(_component("foreign"))
    path.write_text(json.dumps(outer))
    result = _observe(tmp_path)
    assert result.observation is not None
    assessment = next(
        row
        for row in rule_assessments(result.observation, undecided_by_rule={})
        if row.id == "core:RULE"
    )
    receipts = [
        row
        for row in result.observation.records("scope_observations") or ()
        if row.kind == "rule_evaluation" and row.rule_ids == ("core:RULE",)
    ]
    if scope == "sample.foreign.parse":
        assert result.exit_code == 2
        assert any(row.kind == "rule_without_subjects" for row in result.diagnostics)
        assert assessment.status == "UNKNOWN" and not assessment.evaluation_proven
        assert receipts == []
    else:
        assert result.diagnostics == () and assessment.status == "PASS"
        assert assessment.evaluation_proven and len(receipts) == 1
        assert receipts[0].subjects == ("sample.core.a.parse",)
        (tmp_path / "sample/core/a.py").write_text(
            'def parse(value):\n    return value == "import"\n'
        )
        changed = _observe(tmp_path)
        assert changed.observation is not None
        assert [
            (row.kind, row.rule_ids) for row in trace_valid_violations(changed.observation)
        ] == [("forbidden_construct", ("core:RULE",))]
