import json

import pytest

from archkeel.analyzer.python.collect import collect
from archkeel.ir.facts_codec import CollectionResponse, decode_response, encode_response
from archkeel.ir.protocol import (
    CollectionRequest,
    ProtocolVersion,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)


def _payload(tmp_path, source: str) -> dict:
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "core.py").write_text(source)
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
            ProtocolVersion.V4,
        )
    )
    return json.loads(encode_response(CollectionResponse(facts, ProtocolVersion.V4)))


def _call(payload: dict, expression: str) -> dict:
    calls = next(
        section["records"]
        for section in payload["facts"]["sections"]
        if section["name"] == "calls"
    )
    return next(row for row in calls if row["data"].get("expression") == expression)


def test_source_facts_reject_guard_truth_retargeted_from_path_evidence(tmp_path):
    payload = _payload(
        tmp_path,
        "def _effect(): pass\ndef generate(seeded: bool):\n    if seeded:\n        _effect()\n",
    )
    _call(payload, "_effect")["data"]["guarded_effect"][0]["condition_value"] = False

    with pytest.raises(
        ValueError, match="guarded-effect condition value disagrees with its source path"
    ):
        decode_response(json.dumps(payload).encode())
