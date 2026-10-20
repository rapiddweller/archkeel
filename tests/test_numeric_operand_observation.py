# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bounded modulo operands retain source identity and exact alias derivations."""

import json
from dataclasses import replace

import pytest
from test_analyzer import _component, _observe, _parsed_module

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


@pytest.mark.parametrize(
    "source,assignment_line",
    [
        (
            "def choose(job_nonce): return job_nonce % WIDTH\nWIDTH = 4\n",
            2,
        ),
        (
            "def unrelated(job_nonce):\n    WIDTH = 4\n    return job_nonce % WIDTH\n"
            "def choose(job_nonce):\n    return job_nonce % WIDTH\n",
            2,
        ),
        (
            "WIDTH = 4\nWIDTH = 8\ndef choose(job_nonce): return job_nonce % WIDTH\n",
            1,
        ),
    ],
)
def test_numeric_alias_claim_must_be_a_preceding_unique_binding_in_its_scope(
    tmp_path, source, assignment_line
):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
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
    payload = json.loads(encode_response(CollectionResponse(facts)))
    sections = payload["facts"]["sections"]
    operation = next(
        record
        for section in sections
        for record in section["records"]
        if record["kind"] == "numeric_operand" and record["data"]["owner"] == "sample.core.choose"
    )
    if "def unrelated" in source:
        unrelated = next(
            record
            for section in sections
            for record in section["records"]
            if record["kind"] == "numeric_operand"
            and record["data"]["owner"] == "sample.core.unrelated"
            and record["data"]["proof"] == "known"
        )
        borrowed_origin = unrelated["data"]["derivation"][0]
    else:
        evidence = next(
            row
            for row in payload["facts"]["evidence"]
            if row["line"] == assignment_line and "WIDTH =" in row["excerpt"]
        )
        borrowed_origin = {
            "name": "WIDTH",
            "value": 4,
            "expression": "4",
            "evidence_id": evidence["id"],
            "line": evidence["line"],
            "column": evidence["column"],
            "end_line": evidence["end_line"],
            "end_column": evidence["column"] + len("WIDTH = 4"),
        }
    operation["data"]["proof"] = "known"
    operation["data"]["value"] = 4
    operation["data"]["derivation"] = [borrowed_origin]
    operation["evidence_ids"].extend(
        [borrowed_origin["evidence_id"]]
        + ([borrowed_origin["scope_evidence_id"]] if "scope_evidence_id" in borrowed_origin else [])
    )

    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


@pytest.mark.parametrize(
    "source",
    [
        "WIDTH = 4\nchoose = lambda job_nonce, WIDTH: job_nonce % WIDTH\n",
        "WIDTH = 4\nvalues = [job_nonce % WIDTH for WIDTH in (1,)]\n",
        "WIDTH = 4\nclass Holder:\n    WIDTH = 8\n"
        "    choose = lambda job_nonce, WIDTH: job_nonce % WIDTH\n",
        "WIDTH = 4\nclass Holder:\n    WIDTH = 8\n"
        "    values = [job_nonce % WIDTH for WIDTH in (1,)]\n",
    ],
    ids=[
        "module-lambda-parameter",
        "module-comprehension-target",
        "class-lambda-parameter",
        "class-comprehension-target",
    ],
)
def test_anonymous_class_scope_binders_reject_forged_module_alias(tmp_path, source):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
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
    payload = json.loads(encode_response(CollectionResponse(facts)))
    operation = next(
        row
        for section in payload["facts"]["sections"]
        for row in section["records"]
        if row["kind"] == "numeric_operand"
    )
    assert operation["data"]["proof"] == "unknown"
    width = next(
        row
        for row in payload["facts"]["evidence"]
        if row["line"] == 1 and row["excerpt"] == "WIDTH = 4"
    )
    operation["data"]["proof"] = "known"
    operation["data"]["value"] = 4
    operation["data"]["derivation"] = [
        {
            "name": "WIDTH",
            "value": 4,
            "expression": "4",
            "evidence_id": width["id"],
            "line": 1,
            "column": 0,
            "end_line": 1,
            "end_column": 9,
        }
    ]
    operation["evidence_ids"].append(width["id"])

    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


def test_numeric_alias_in_a_nested_ancestor_scope_keeps_a_valid_witness(tmp_path):
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
        "def outer():\n    WIDTH = 4\n    def inner(job_nonce):\n        return job_nonce % WIDTH\n"
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
        record
        for section in response.facts.sections
        for record in section.records
        if record.kind == "numeric_operand"
    )
    assert operation.data.get("proof") == "known"
    assert operation.data.get("value") == 4


@pytest.mark.parametrize(
    ("source", "expected_count"),
    [
        (
            "WIDTH = 4\n"
            "def outer(job_nonce):\n"
            "    def middle():\n"
            "        def inner(): return job_nonce % WIDTH\n"
            "        return inner()\n"
            "    return middle()\n",
            1,
        ),
        (
            "WIDTH = 4\n"
            "class Holder:\n"
            "    WIDTH = 8\n"
            "    def choose(self, job_nonce): return job_nonce % WIDTH\n",
            1,
        ),
        (
            "WIDTH = 4\n"
            "def outer(job_nonce):\n"
            "    def inner(): return job_nonce % WIDTH\n"
            "    def inner(): return job_nonce % WIDTH\n"
            "    return inner()\n",
            2,
        ),
    ],
)
def test_numeric_module_alias_scope_chain_round_trips_native_facts(
    tmp_path, source, expected_count
):
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
        record
        for section in response.facts.sections
        for record in section.records
        if record.kind == "numeric_operand"
    ]
    assert len(operations) == expected_count
    assert [record.data.get("proof") for record in operations] == ["known"] * expected_count
    assert [record.data.get("value") for record in operations] == [4] * expected_count


@pytest.mark.parametrize(
    ("source", "expected_owner", "expected_value"),
    [
        (
            "WIDTH = 4\ndef choose(value=job_nonce % WIDTH): return value\n",
            "sample.core",
            4,
        ),
        (
            "WIDTH = 4\n@decorate(job_nonce % WIDTH)\ndef choose(): return None\n",
            "sample.core",
            4,
        ),
        (
            "WIDTH = 4\n@decorate(job_nonce % WIDTH)\nclass Holder: pass\n",
            "sample.core",
            4,
        ),
        (
            "def outer(job_nonce):\n"
            "    WIDTH = 8\n"
            "    @decorate(job_nonce % WIDTH)\n"
            "    def inner(): return None\n",
            "sample.core.outer",
            8,
        ),
        (
            "def outer(job_nonce):\n"
            "    WIDTH = 8\n"
            "    def inner(value=job_nonce % WIDTH): return value\n"
            "    return inner()\n",
            "sample.core.outer",
            8,
        ),
        (
            "def outer(job_nonce):\n    WIDTH = 8\n    class Inner(job_nonce % WIDTH): pass\n",
            "sample.core.outer",
            8,
        ),
        (
            "class Holder:\n"
            "    WIDTH = 16\n"
            "    def choose(self, value=job_nonce % WIDTH): return value\n",
            "sample.core.Holder",
            16,
        ),
    ],
)
def test_numeric_definition_headers_use_their_enclosing_lexical_scope(
    tmp_path, source, expected_owner, expected_value
):
    from archkeel.analyzer.python.collect import collect
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes
    from archkeel.ir.codec_observation import observation_payload
    from archkeel.ir.decisions import rule_assessments, unknown_positions_by_rule
    from archkeel.ir.facts_validation import validate_source_facts
    from archkeel.ir.protocol import (
        CollectionRequest,
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
    validate_source_facts(facts)
    operations = [
        record
        for section in facts.sections
        for record in section.records
        if record.kind == "numeric_operand"
    ]
    assert len(operations) == 1
    assert operations[0].data.get("proof") == "known"
    assert operations[0].data.get("value") == expected_value
    assert operations[0].data.get("owner") == expected_owner

    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "3.8.0",
                "components": [_component("core")],
                "rules": [
                    {
                        "id": "WIDTH",
                        "kind": "bounded_numeric_operand",
                        "rationale": "Probe lexical ownership in evaluated headers.",
                        "provenance": ["docs/architecture/sample.md"],
                        "decided_by": "architect",
                        "source": "sample.core",
                        "form": "both",
                        "terminal_suffix": "nonce",
                        "minimum_value": 4,
                    }
                ],
            }
        )
    )
    observed = _observe(tmp_path)
    assert observed.observation is not None and not observed.diagnostics
    assessments = rule_assessments(
        observed.observation,
        undecided_by_rule=unknown_positions_by_rule(observed.observation),
    )
    assert len(assessments) == 1 and assessments[0].status.value == "PASS"
    for columnar in (False, True):
        saved = tmp_path / "saved.json"
        saved.write_bytes(
            canonical_report_bytes(observed.observation)
            if columnar
            else json.dumps(observation_payload(observed.observation)).encode()
        )
        assert run_saved_report(saved).rule_assessments == assessments


def test_numeric_module_alias_cannot_drop_an_enclosing_shadow_scope(tmp_path):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/core.py").write_text(
        "WIDTH = 4\n"
        "def safe(job_nonce): return job_nonce % WIDTH\n"
        "def outer(job_nonce):\n"
        "    WIDTH = 8\n"
        "    def choose(): return job_nonce % WIDTH\n"
        "    return choose()\n"
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    payload = json.loads(encode_response(CollectionResponse(facts)))
    sections = payload["facts"]["sections"]
    records = [record for section in sections for record in section["records"]]
    safe = next(
        record
        for record in records
        if record["kind"] == "numeric_operand" and record["data"]["owner"] == "sample.core.safe"
    )
    target = next(
        record
        for record in records
        if record["kind"] == "numeric_operand"
        and record["data"]["owner"] == "sample.core.outer.choose"
    )
    target["data"]["proof"] = "known"
    target["data"]["value"] = 4
    target["data"]["derivation"] = safe["data"]["derivation"]
    target["data"]["binding_scopes"] = [
        scope
        for scope in target["data"]["binding_scopes"]
        if scope["scope_owner"] != "sample.core.outer"
    ]
    original_target = next(
        record
        for section in facts.sections
        for record in section.records
        if record.kind == "numeric_operand"
        and record.data.get("owner") == "sample.core.outer.choose"
    )
    outer_scope_id = next(
        scope.get("scope_evidence_id")
        for scope in original_target.data.get("binding_scopes")
        if scope.get("scope_owner") == "sample.core.outer"
    )
    target["evidence_ids"] = sorted(
        {
            *target["evidence_ids"],
            *(item["evidence_id"] for item in safe["data"]["derivation"]),
            outer_scope_id,
        }
    )
    inner_symbol = next(
        record
        for section in payload["facts"]["sections"]
        if section["name"] == "symbols"
        for record in section["records"]
        if record["data"].get("qualified_name") == "sample.core.outer.choose"
    )
    inner_symbol["data"]["parent"] = None
    inner_symbol["data"]["lexical_parent_id"] = None

    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


@pytest.mark.parametrize(
    ("source", "forged_line", "binding_lines"),
    [
        (
            "def choose(job_nonce):\n"
            "    SAFE = 9\n"
            "    keep = job_nonce % SAFE\n"
            "    forged = job_nonce % WIDTH\n"
            "    WIDTH = 4\n",
            4,
            (5,),
        ),
        (
            "def choose(job_nonce):\n"
            "    SAFE = 9\n"
            "    keep = job_nonce % SAFE\n"
            "    forged = job_nonce % WIDTH\n"
            "    WIDTH = 4\n"
            "    WIDTH = 8\n",
            4,
            (5, 6),
        ),
        (
            "def choose(job_nonce):\n"
            "    SAFE = 9\n"
            "    keep = job_nonce % SAFE\n"
            "    WIDTH = 4\n"
            "    def WIDTH(): return 5\n"
            "    forged = job_nonce % WIDTH\n",
            6,
            (4,),
        ),
        (
            "def choose(job_nonce):\n"
            "    SAFE = 9\n"
            "    keep = job_nonce % SAFE\n"
            "    WIDTH = 4\n"
            "    [(WIDTH := 5) for _ in (0,)]\n"
            "    forged = job_nonce % WIDTH\n",
            6,
            (4,),
        ),
        (
            "def choose(job_nonce):\n"
            "    SAFE = 9\n"
            "    keep = job_nonce % SAFE\n"
            "    WIDTH = 4\n"
            "    def sibling(*args: (WIDTH := 5)): return args\n"
            "    forged = job_nonce % WIDTH\n",
            6,
            (4,),
        ),
        (
            "def choose(job_nonce):\n"
            "    SAFE = 9\n"
            "    keep = job_nonce % SAFE\n"
            "    WIDTH = 4\n"
            "    def sibling(**kwargs: (WIDTH := 5)): return kwargs\n"
            "    forged = job_nonce % WIDTH\n",
            6,
            (4,),
        ),
    ],
)
def test_numeric_local_alias_claim_rejects_late_or_rebound_write(
    tmp_path, source, forged_line, binding_lines
):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts import stable_id
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
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
    payload = json.loads(encode_response(CollectionResponse(facts)))
    sections = payload["facts"]["sections"]
    operations = [
        record
        for section in sections
        for record in section["records"]
        if record["kind"] == "numeric_operand"
    ]
    target = next(record for record in operations if record["data"]["line"] == forged_line)
    trusted = next(
        record
        for record in operations
        if record["data"]["proof"] == "known" and record["data"]["derivation"][0]["name"] == "SAFE"
    )
    trusted_origin = trusted["data"]["derivation"][0]
    evidence = payload["facts"]["evidence"]
    source_lines = source.splitlines()
    assignments = [
        next(
            (row for row in evidence if row["line"] == line and "WIDTH =" in row["excerpt"]),
            None,
        )
        for line in binding_lines
    ]
    first = assignments[0]
    if first is None:
        line = binding_lines[0]
        first = {
            "id": stable_id("EVD", "sample/core.py", line, line, 4),
            "file": "sample/core.py",
            "line": line,
            "end_line": line,
            "column": 4,
            "excerpt": source_lines[line - 1],
        }
        evidence.append(first)
    target["data"]["proof"] = "known"
    target["data"]["value"] = 4
    target["data"]["derivation"] = [
        {
            "name": "WIDTH",
            "value": 4,
            "expression": "4",
            "evidence_id": first["id"],
            "line": first["line"],
            "column": first["column"],
            "end_line": first["end_line"],
            "end_column": first["column"] + len("WIDTH = 4"),
            "scope_evidence_id": trusted_origin["scope_evidence_id"],
            "scope_owner": trusted_origin["scope_owner"],
            "scope_symbol_id": trusted_origin["scope_symbol_id"],
        }
    ]
    target["evidence_ids"].extend([first["id"], trusted_origin["scope_evidence_id"]])
    target["evidence_ids"] = sorted(set(target["evidence_ids"]))
    assert (
        stable_id("SYM", "sample.core.choose", "sample/core.py", 1, 0)
        == (trusted_origin["scope_symbol_id"])
    )

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


def test_module_expression_alias_uses_unique_source_binding_inventory(tmp_path):
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
        "WIDE = 2**64\ndef choose(job_nonce): return job_nonce % WIDE\n"
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
        record
        for section in response.facts.sections
        for record in section.records
        if record.kind == "numeric_operand"
    )
    assert operation.data.get("proof") == "known"
    assert operation.data.get("value") == 2**64


@pytest.mark.parametrize(
    "source",
    [
        "WIDTH = 4\n"
        "def safe(job_nonce): return job_nonce % WIDTH\n"
        "def choose(WIDTH, job_nonce): return job_nonce % WIDTH\n",
        "WIDTH = 4\n"
        "def safe(job_nonce): return job_nonce % WIDTH\n"
        "def choose(job_nonce):\n"
        "    WIDTH = 8\n"
        "    return job_nonce % WIDTH\n",
    ],
)
def test_module_alias_claim_cannot_cross_a_local_shadow(tmp_path, source):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
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
    payload = json.loads(encode_response(CollectionResponse(facts)))
    sections = payload["facts"]["sections"]
    operations = [
        record
        for section in sections
        for record in section["records"]
        if record["kind"] == "numeric_operand"
    ]
    trusted = next(record for record in operations if record["data"]["owner"] == "sample.core.safe")
    target = next(
        record for record in operations if record["data"]["owner"] == "sample.core.choose"
    )
    target["data"]["proof"] = "known"
    target["data"]["value"] = 4
    target["data"]["derivation"] = [trusted["data"]["derivation"][0]]
    target["evidence_ids"].append(trusted["data"]["derivation"][0]["evidence_id"])
    target["evidence_ids"] = sorted(set(target["evidence_ids"]))

    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


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


def test_class_anonymous_scope_cannot_retarget_module_alias_to_class_binding(tmp_path):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    source = (
        "WIDTH = 4\n"
        "class Holder:\n"
        "    WIDTH = 8\n"
        "    choose = lambda job_nonce: job_nonce % WIDTH\n"
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
    records = [record for section in payload["facts"]["sections"] for record in section["records"]]
    operation = next(record for record in records if record["kind"] == "numeric_operand")
    class_assignment = next(
        evidence
        for evidence in payload["facts"]["evidence"]
        if evidence["line"] == 3 and evidence["excerpt"].strip() == "WIDTH = 8"
    )
    origin = operation["data"]["derivation"][0]
    origin.update(
        evidence_id=class_assignment["id"],
        value=8,
        expression="8",
        line=3,
        column=4,
        end_line=3,
        end_column=13,
    )
    operation["data"]["value"] = 8
    operation["evidence_ids"] = sorted({*operation["evidence_ids"], class_assignment["id"]})

    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


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
