# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
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


@pytest.mark.parametrize("mutation", ["literal", "value", "end_column"])
def test_numeric_alias_claims_must_match_their_source_witnesses(tmp_path, mutation):
    from dataclasses import replace

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

    (tmp_path / "sample").mkdir()
    source = (
        "def choose(job_nonce): return job_nonce % 4\n"
        if mutation == "literal"
        else "WIDTH = 4\ndef choose(job_nonce): return job_nonce % WIDTH\n"
    )
    (tmp_path / "sample/core.py").write_text(source)
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
    if mutation == "literal":
        operation["data"]["value"] = 2**32
    elif mutation == "value":
        operation["data"]["value"] = 2**32
        operation["data"]["derivation"][0]["value"] = 2**32
    else:
        operation["data"]["derivation"][0]["end_column"] += 100

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
    with pytest.raises(ValueError):
        validate_source_facts(malformed)
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


def test_same_line_indented_and_semicolon_aliases_validate(tmp_path):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import decode_response, encode_response
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "WIDTH = 4; OTHER = 8\n"
        "def choose(job_nonce):\n"
        "    first = job_nonce % WIDTH; second = job_nonce % OTHER\n"
        "    return first, second\n"
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    response = decode_response(encode_response(CollectionResponse(facts)))
    operations = [
        row
        for section in response.facts.sections
        for row in section.records
        if row.kind == "numeric_operand"
    ]
    assert [row.data.get("value") for row in operations] == [4, 8]


def test_repeated_alias_origin_is_valid_when_expression_reuses_name(tmp_path):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import decode_response, encode_response
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "WIDTH = 2\ndef choose(job_nonce): return job_nonce % (WIDTH ** WIDTH)\n"
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    response = decode_response(encode_response(CollectionResponse(facts)))
    operation = next(
        row
        for section in response.facts.sections
        for row in section.records
        if row.kind == "numeric_operand"
    )
    assert operation.data.get("value") == 4


@pytest.mark.parametrize("form", ["binary", "augmented"])
def test_numeric_operation_subject_must_match_left_terminal_name(tmp_path, form):
    from dataclasses import replace

    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
    from archkeel.ir.facts_validation import validate_source_facts
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    source = (
        "def choose(job_nonce): return job_nonce % 4\n"
        if form == "binary"
        else "def choose(job_nonce):\n    job_nonce %= 4\n"
    )
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(source)
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    payload = json.loads(encode_response(CollectionResponse(facts)))
    raw = next(
        record
        for section in payload["facts"]["sections"]
        for record in section["records"]
        if record["kind"] == "numeric_operand"
    )
    raw["data"]["subject"] = "some_other_name"
    from archkeel.ir.facts_codec import parse_record

    malformed = replace(
        facts,
        sections=tuple(
            replace(
                section,
                records=tuple(
                    parse_record(raw) if record.id == raw["id"] else record
                    for record in section.records
                ),
            )
            for section in facts.sections
        ),
    )
    with pytest.raises(ValueError, match="numeric operand"):
        validate_source_facts(malformed)
    with pytest.raises(ProtocolError, match="numeric operand"):
        decode_response(json.dumps(payload).encode())


@pytest.mark.parametrize(
    "source",
    [
        "WIDTH = (\n    4\n)\ndef choose(job_nonce): return job_nonce % WIDTH\n",
        "def choose(job_nonce):\n    return job_nonce % (\n        4\n    )\n",
    ],
)
def test_multiline_numeric_witnesses_remain_unknown(tmp_path, source):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import decode_response, encode_response
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(source)
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    response = decode_response(encode_response(CollectionResponse(facts)))
    operations = [
        row
        for section in response.facts.sections
        for row in section.records
        if row.kind == "numeric_operand"
    ]
    assert len(operations) == 1
    assert operations[0].data.get("proof") == "unknown"
    assert operations[0].data.get("value") is None
    assert operations[0].data.get("derivation") == ()


@pytest.mark.parametrize(("keyword", "body"), [("if", "return True"), ("while", "break")])
def test_single_line_control_condition_numeric_witness_replays(tmp_path, keyword, body):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import decode_response, encode_response
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        f"def choose(nonce_λ):\n    {keyword} (nonce_λ % 4): # checked branch\n"
        f"        {body}\n    return False\n"
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    response = decode_response(encode_response(CollectionResponse(facts)))
    operation = next(
        row
        for section in response.facts.sections
        for row in section.records
        if row.kind == "numeric_operand"
    )
    assert operation.data.get("proof") == "known"
    assert operation.data.get("value") == 4
    assert operation.data.get("subject") == "nonce_λ"


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


def test_elif_modulo_header_retains_known_operand_and_original_span():
    source = """\
def choose(job_nonce, enabled):
    if enabled:
        return 0
    elif job_nonce % 4:  # numeric branch
        return 1
    return 0
"""
    module = _parsed_module(source, "sample.mod", rel_path="sample.py")
    operation = next(
        row for row in collect_constructs([module], {}) if row["kind"] == "numeric_operand"
    )

    assert operation["data"]["proof"] == "known"
    assert operation["data"]["value"] == 4
    assert operation["data"]["line"] == 4
    assert operation["data"]["column"] == 9
    assert operation["data"]["end_column"] == 22


def test_nested_elif_modulo_header_keeps_exact_source_columns():
    source = """\
def choose(job_nonce, enabled, nested):
    if enabled:
        if nested:
            return 0
        elif(job_nonce % 4):  # nested numeric branch
            return 1
    return 0
"""
    module = _parsed_module(source, "sample.mod", rel_path="sample.py")
    operation = next(
        row for row in collect_constructs([module], {}) if row["kind"] == "numeric_operand"
    )

    assert operation["data"]["proof"] == "known"
    assert operation["data"]["value"] == 4
    assert operation["data"]["line"] == 5
    assert operation["data"]["column"] == 13
    assert operation["data"]["end_column"] == 26


@pytest.mark.parametrize(
    "source",
    [
        "def choose(job_nonce):\n    for item in job_nonce % 4:\n        return item\n",
        "def choose(job_nonce):\n    with job_nonce % 4 as item:\n        return item\n",
        "def choose(job_nonce, value=job_nonce % 4):\n    return value\n",
        "class Choose(job_nonce % 4):\n    pass\n",
    ],
)
def test_single_line_header_modulo_evidence_replays_with_original_span(source):
    module = _parsed_module(source, "sample.mod", rel_path="sample.py")
    operation = next(
        row for row in collect_constructs([module], {}) if row["kind"] == "numeric_operand"
    )

    assert operation["data"]["proof"] == "known"
    assert operation["data"]["value"] == 4


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
