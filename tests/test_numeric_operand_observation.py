"""Bounded modulo operands retain source identity and exact alias derivations."""

import json
from dataclasses import replace

import pytest
from test_analyzer import _parsed_module

from archkeel.analyzer.python.constructs import collect_constructs


@pytest.mark.parametrize("link", ["operation", "alias"])
def test_dangling_numeric_evidence_is_a_protocol_error(tmp_path, link):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import (
        ProtocolError,
        decode_response,
        encode_response,
        parse_record,
    )
    from archkeel.ir.facts_validation import validate_source_facts
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    operand = "WIDTH" if link == "alias" else "4"
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        f"WIDTH = 4\ndef choose(job_nonce): return job_nonce % {operand}\n"
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    payload = json.loads(encode_response(CollectionResponse(facts)))
    operation = next(
        record
        for section in payload["facts"]["sections"]
        for record in section["records"]
        if record["kind"] == "numeric_operand"
    )
    if link == "operation":
        operation["evidence_ids"] = ["absent-evidence"]
    else:
        operation["data"]["derivation"][0]["evidence_id"] = "absent-evidence"
        operation["evidence_ids"].append("absent-evidence")
    malformed = replace(
        facts,
        sections=tuple(
            replace(
                section,
                records=tuple(
                    parse_record(operation) if record.id == operation["id"] else record
                    for record in section.records
                ),
            )
            for section in facts.sections
        ),
    )
    with pytest.raises(ValueError, match="evidence"):
        validate_source_facts(malformed)
    with pytest.raises(ProtocolError, match="evidence"):
        decode_response(json.dumps(payload).encode())


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
