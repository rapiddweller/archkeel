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


def _payload(tmp_path, source: str | dict[str, str]) -> dict:
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("")
    sources = {"sample/core.py": source} if isinstance(source, str) else source
    for path, text in sources.items():
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text)
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


def test_source_facts_reject_helper_actual_retargeted_from_its_source(tmp_path):
    payload = _payload(
        tmp_path,
        "def _effect(): pass\n"
        "def _helper(flag: bool):\n    if flag:\n        _effect()\n"
        "def generate(seeded: bool, other: bool):\n"
        "    if seeded:\n        _helper(seeded)\n",
    )
    helper = _call(payload, "_helper")["data"]["guarded_effect"][0]["helper_bindings"][0]
    helper["arguments"][0]["condition"]["name"] = "other"

    with pytest.raises(
        ValueError, match="guarded-effect helper argument disagrees with its source"
    ):
        decode_response(json.dumps(payload).encode())


def test_source_facts_reject_helper_callee_retargeted_to_a_sibling(tmp_path):
    payload = _payload(
        tmp_path,
        "def _effect(): pass\n"
        "def _helper(flag: bool):\n    if flag:\n        _effect()\n"
        "def _other(flag: bool): pass\n"
        "def generate(seeded: bool):\n    if seeded:\n        _helper(seeded)\n",
    )
    call = _call(payload, "_helper")
    sibling = next(
        row
        for section in payload["facts"]["sections"]
        if section["name"] == "symbols"
        for row in section["records"]
        if row["data"].get("qualified_name") == "sample.core._other"
    )
    binding = call["data"]["call_binding"]
    binding["target"] = "sample.core._other"
    binding["evidence_ids"] = sorted(set(binding["evidence_ids"] + sibling["evidence_ids"]))
    call["data"]["targets"] = ["sample.core._other"]
    for proof in call["data"]["guarded_effect"]:
        proof["effect_binding_evidence_ids"] = binding["evidence_ids"]
        for helper in proof["helper_bindings"]:
            helper["target"] = "sample.core._other"
            helper["evidence_ids"] = sorted(set(helper["evidence_ids"] + sibling["evidence_ids"]))

    with pytest.raises(
        ValueError, match="guarded-effect helper target disagrees with its written callee"
    ):
        decode_response(json.dumps(payload).encode())


def test_source_facts_bind_imported_helper_to_its_written_import(tmp_path):
    payload = _payload(
        tmp_path,
        {
            "sample/core.py": "def _helper(flag: bool):\n    if flag:\n        pass\n",
            "sample/other.py": "def _helper(flag: bool):\n    pass\n",
            "sample/client.py": (
                "from sample.core import _helper as _h\n"
                "def generate(seeded: bool):\n    if seeded:\n        _h(seeded)\n"
            ),
        },
    )
    call = _call(payload, "_h")
    assert call["data"]["call_binding"]["target"] == "sample.core._helper"
    binding = call["data"]["guarded_effect"][0]["helper_bindings"][0]
    assert binding["target"] == "sample.core._helper"


def test_source_facts_reject_imported_helper_retargeted_to_sibling_module(tmp_path):
    payload = _payload(
        tmp_path,
        {
            "sample/core.py": "def _helper(flag: bool):\n    if flag:\n        pass\n",
            "sample/other.py": "def _helper(flag: bool):\n    pass\n",
            "sample/client.py": (
                "from sample.core import _helper as _h\n"
                "def generate(seeded: bool):\n    if seeded:\n        _h(seeded)\n"
            ),
        },
    )
    call = _call(payload, "_h")
    sibling = next(
        row
        for section in payload["facts"]["sections"]
        if section["name"] == "symbols"
        for row in section["records"]
        if row["data"].get("qualified_name") == "sample.other._helper"
    )
    binding = call["data"]["call_binding"]
    binding["target"] = "sample.other._helper"
    binding["evidence_ids"] = sorted(set(binding["evidence_ids"] + sibling["evidence_ids"]))
    call["data"]["targets"] = ["sample.other._helper"]
    for proof in call["data"]["guarded_effect"]:
        proof["effect_binding_evidence_ids"] = binding["evidence_ids"]
        for helper in proof["helper_bindings"]:
            helper["target"] = "sample.other._helper"
            helper["evidence_ids"] = sorted(set(helper["evidence_ids"] + sibling["evidence_ids"]))

    with pytest.raises(
        ValueError, match="guarded-effect helper target disagrees with its written callee"
    ):
        decode_response(json.dumps(payload).encode())
