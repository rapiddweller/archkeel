"""Bounded modulo operands retain source identity and exact alias derivations."""

import pytest
from test_analyzer import _parsed_module

from archkeel.analyzer.python.constructs import collect_constructs


def test_modulo_operations_have_distinct_full_spans_and_constant_proofs():
    source = """SMALL = 16
WIDE = 2**64
def choose(job_nonce, dynamic):
    small = job_nonce % SMALL
    wide = job_nonce % WIDE
    unknown = job_nonce % dynamic
    job_nonce %= 16
    return small, wide, unknown
"""
    module = _parsed_module(source, "sample.mod", rel_path="sample.py")
    records = collect_constructs([module], {})
    operations = sorted(
        (row for row in records if row["kind"] == "numeric_operand"),
        key=lambda row: (row["data"]["line"], row["data"]["column"]),
    )

    assert len(operations) == 4
    assert [row["data"]["form"] for row in operations] == [
        "binary",
        "binary",
        "binary",
        "augmented",
    ]
    assert len({row["id"] for row in operations}) == 4
    assert all("end_line" in row["data"] and "end_column" in row["data"] for row in operations)
    assert [(row["data"]["proof"], row["data"].get("value")) for row in operations] == [
        ("known", 16),
        ("known", 18446744073709551616),
        ("unknown", None),
        ("known", 16),
    ]
    derivation = operations[0]["data"]["derivation"]
    assert len(derivation) == 1
    assert derivation[0]["name"] == "SMALL"
    assert derivation[0]["value"] == 16
    assert derivation[0]["evidence_id"] in operations[0]["evidence_ids"]
    assert derivation[0]["line"] == 1


@pytest.mark.parametrize(
    "source",
    [
        "SMALL = 16\nif flag:\n    SMALL = 8\ndef f(x): return x % SMALL\n",
        "SMALL = 16\ndel SMALL\ndef f(x): return x % SMALL\n",
        "SMALL = 16\nSMALL += 1\ndef f(x): return x % SMALL\n",
        "SMALL = 16\nimport os as SMALL\ndef f(x): return x % SMALL\n",
        "SMALL = 16\ndef rebind():\n    global SMALL\n    SMALL = 8\ndef f(x): return x % SMALL\n",
        "SMALL = 16\ndef f(x):\n    (SMALL := 8)\n    return x % SMALL\n",
    ],
)
def test_module_alias_proof_rejects_every_rebinding_form(source):
    module = _parsed_module(source, "sample.mod", rel_path="sample.py")
    records = collect_constructs([module], {})
    operation = next(row for row in records if row["kind"] == "numeric_operand")
    assert operation["data"]["proof"] == "unknown"
    assert operation["data"]["derivation"] == []


def test_local_alias_shadowing_and_oversized_direct_integer_are_unknown():
    source = (
        """\
def f(x):
    small = 16
    if flag:
        small = 8
    return x % small
def g(x):
    return x % 0x"""
        + "1"
        + "0" * 1100
        + "\n"
    )
    module = _parsed_module(source, "sample.mod", rel_path="sample.py")
    records = collect_constructs([module], {})
    operations = sorted(
        (row for row in records if row["kind"] == "numeric_operand"),
        key=lambda row: row["data"]["column"],
    )
    assert [row["data"]["proof"] for row in operations] == ["unknown", "unknown"]


def test_power_bounds_return_unknown_without_unbounded_integer_work():
    module = _parsed_module(
        "def f(x): return x % 2**257, x % 2**4096, x % 3**256\n",
        "sample.mod",
        rel_path="sample.py",
    )
    records = collect_constructs([module], {})
    operations = sorted(
        (row for row in records if row["kind"] == "numeric_operand"),
        key=lambda row: row["data"]["column"],
    )
    assert [row["data"]["proof"] for row in operations] == ["unknown", "unknown", "known"]
