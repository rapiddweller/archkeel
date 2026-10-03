# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Reject malformed inherited-member proof at the process boundary."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_source_trust_boundary import _payload

from archkeel.ir.facts_codec import ProtocolError, decode_response

SCHEMA = json.loads((Path(__file__).parents[1] / "schema/source-facts.schema.json").read_bytes())


def _schema_errors(payload):
    return list(Draft202012Validator(SCHEMA).iter_errors(payload))


@pytest.mark.parametrize(
    "key",
    [
        "source_binding_unique",
        "source_member_binding_static",
        "origin_member_binding_static",
        "origin_binding_unique",
        "class_header_static",
        "class_body_control_flow",
        "signature_decorators_proven",
        "source_final_method_binding",
        "overloaded",
        "overload_signature",
    ],
)
@pytest.mark.parametrize("value", [None, 0, 1, "true", [], {}])
def test_malformed_proof_flags(key, value):
    payload = _payload()
    payload["facts"]["sections"][0]["records"][0]["data"][key] = value
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())
    assert _schema_errors(payload)


@pytest.mark.parametrize("value", [None, "x", [""], [1], [None], [False], {}])
def test_malformed_candidates(value):
    payload = _payload()
    payload["facts"]["sections"][0]["records"][0]["data"]["reexport_candidates"] = value
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())
    assert _schema_errors(payload)


@pytest.mark.parametrize("value", [[], ["module.Class"]])
def test_candidate_arrays(value):
    payload = _payload()
    payload["facts"]["sections"][0]["records"][0]["data"]["reexport_candidates"] = value
    facts = decode_response(json.dumps(payload).encode()).facts
    assert facts.sections[0].records[0].data.get("reexport_candidates") == tuple(value)
    assert not _schema_errors(payload)


@pytest.mark.parametrize(
    "missing",
    [
        "source_binding_unique",
        "source_member_binding_static",
        "class_header_static",
        "signature_decorators_proven",
    ],
)
@pytest.mark.parametrize("imported_base", [False, True], ids=["local-base", "imported-base"])
def test_missing_symbol_proof_is_unknown(tmp_path, missing, imported_base):
    from test_boundary_types_non_init_facades import _write_app

    from archkeel.analyzer.python.collect import collect
    from archkeel.check.observation import assemble_observation
    from archkeel.check.ratchets import unknown_positions
    from archkeel.ir.facts_codec import encode_response
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    _write_app(
        tmp_path,
        public=["sample.app.api:Child"],
        api=(
            "from .impl import Base\nclass Child(Base): pass\n"
            if imported_base
            else "class Base:\n    def convert(self) -> str: ...\nclass Child(Base): pass\n"
        ),
        implementation="class Base:\n    def convert(self) -> str: ...\n" if imported_base else "",
        init="",
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    complete = assemble_observation(
        facts,
        contract_root=tmp_path,
        contract_path=tmp_path / "contract.json",
        roots=("sample",),
        namespace="sample",
    )[0]
    assert unknown_positions(complete) == 0
    payload = json.loads(encode_response(CollectionResponse(facts)))
    for section in payload["facts"]["sections"]:
        for record in section["records"]:
            record["data"].pop(missing, None)
    facts = decode_response(json.dumps(payload).encode()).facts
    observation = assemble_observation(
        facts,
        contract_root=tmp_path,
        contract_path=tmp_path / "contract.json",
        roots=("sample",),
        namespace="sample",
    )[0]
    assert unknown_positions(observation) > 0
