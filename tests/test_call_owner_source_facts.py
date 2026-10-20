# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-facts call proofs stay tied to the exact written receiver and import."""

import json
from pathlib import Path

import pytest

from archkeel.analyzer.python.collect import collect, provider_sources
from archkeel.ir.facts_codec import (
    CollectionResponse,
    ProtocolError,
    RecordData,
    decode_response,
    encode_response,
)
from archkeel.ir.protocol import (
    CollectionRequest,
    ProtocolVersion,
    PythonCollectionPhase,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)


def _payload(
    tmp_path: Path,
    caller: str,
    *,
    other: str = "",
    native: bool = False,
    extra: dict[str, str] | None = None,
) -> dict:
    files = {
        "sample/__init__.py": "",
        "sample/caller.py": caller,
        "sample/storage.py": "class Store:\n    def page(self): pass\n",
        "sample/other.py": other,
    }
    files.update(extra or {})
    for relative, source in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    snapshot = SnapshotInput(str(tmp_path), "a" * 40, False)
    scope = SourceScope(("sample",), "sample")
    request = CollectionRequest(snapshot, scope, PythonSettings(), ProtocolVersion.V4)
    sources = ()
    if native:
        survey_request = CollectionRequest(
            snapshot,
            scope,
            PythonSettings(phase=PythonCollectionPhase.PROVIDERS),
            ProtocolVersion.V4,
        )
        survey = collect(survey_request)
        sources = provider_sources(survey_request, survey)
        request = CollectionRequest(
            snapshot, scope, PythonSettings(provider_sources=sources), ProtocolVersion.V4
        )
    facts = collect(request)
    response = CollectionResponse(facts, ProtocolVersion.V4)
    return json.loads(encode_response(response))


def _records(payload: dict, name: str) -> list[dict]:
    return next(item["records"] for item in payload["facts"]["sections"] if item["name"] == name)


def test_stored_receiver_field_and_call_expression_cannot_be_retargeted(tmp_path):
    payload = _payload(
        tmp_path,
        "from .storage import Store\nclass Holder:\n"
        "    def __init__(self, client: Store): self.client = client\n"
        "    def run(self): self.client.page()\n",
    )
    decode_response(json.dumps(payload).encode())
    initializer = next(
        item
        for item in _records(payload, "symbols")
        if item["data"].get("qualified_name") == "sample.caller.Holder.__init__"
    )
    call = next(
        item
        for item in _records(payload, "calls")
        if item["data"]["expression"] == "self.client.page"
    )
    initializer["data"]["stored_field_writes"][0]["field"] = "other"
    call["data"]["expression"] = "self.other.page"
    call["data"]["call_binding"]["proof"]["field"] = "other"
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


def test_stored_receiver_rhs_must_match_its_typed_parameter(tmp_path):
    payload = _payload(
        tmp_path,
        "from .storage import Store\nfrom .other import Other\nclass Holder:\n"
        "    def __init__(self, client: Store, other: Other): self.client = client\n"
        "    def run(self): self.client.page()\n",
        other="class Other:\n    def page(self): pass\n",
    )
    initializer = next(
        item
        for item in _records(payload, "symbols")
        if item["data"].get("qualified_name") == "sample.caller.Holder.__init__"
    )
    other = next(
        item
        for item in _records(payload, "symbols")
        if item["data"].get("qualified_name") == "sample.other.Other"
    )
    method = next(
        item
        for item in _records(payload, "symbols")
        if item["data"].get("qualified_name") == "sample.other.Other.page"
    )
    call = next(
        item
        for item in _records(payload, "calls")
        if item["data"]["expression"] == "self.client.page"
    )
    initializer["data"]["stored_field_writes"][0]["parameter"] = "other"
    initializer["data"]["stored_field_writes"][0]["annotation_target"] = "sample.other.Other"
    binding = call["data"]["call_binding"]
    binding["target"] = "sample.other.Other.page"
    binding["proof"]["parameter"] = "other"
    binding["proof"]["target"] = "sample.other.Other"
    binding["evidence_ids"] = sorted(
        set(binding["evidence_ids"] + other["evidence_ids"] + method["evidence_ids"])
    )
    call["data"]["targets"] = [binding["target"]]
    call["data"]["target_evidence_ids"] = method["evidence_ids"]
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


@pytest.mark.parametrize(
    "caller,expected",
    [
        (
            "from .pkg import Vault as Selected\nclass Holder:\n"
            "    def __init__(self, client: Selected): self.client = client\n"
            "    def run(self): self.client.page()\n",
            "sample.pkg.types.Vault",
        ),
        (
            "from .pkg import Vault\nfrom .other import Vault\nclass Holder:\n"
            "    def __init__(self, client: Vault): self.client = client\n"
            "    def run(self): self.client.page()\n",
            None,
        ),
    ],
)
def test_stored_annotation_origin_uses_unique_reexport_binding(tmp_path, caller, expected):
    payload = _payload(
        tmp_path,
        caller,
        extra={
            "sample/pkg/__init__.py": "from .types import Vault\n",
            "sample/pkg/types.py": "class Vault:\n    def page(self): pass\n",
            "sample/other.py": "class Vault:\n    def page(self): pass\n",
        },
    )
    facts = decode_response(json.dumps(payload).encode()).facts
    call = next(
        record
        for section in facts.sections
        if section.name.value == "calls"
        for record in section.records
        if record.data.get("expression") == "self.client.page"
    )
    binding = call.data.get("call_binding")
    if expected is None:
        assert binding is None
    else:
        assert isinstance(binding, RecordData)
        assert binding.get("origin") == "stored_receiver"
        assert binding.get("target") == f"{expected}.page"
        assert binding.get("proof").get("target") == expected
    from archkeel.ir.facts_validation import _annotation_class_origin

    symbols = next(section for section in facts.sections if section.name.value == "symbols")
    initializer = next(
        record
        for record in symbols.records
        if record.data.get("qualified_name") == "sample.caller.Holder.__init__"
    )
    parameters = initializer.data.get("parameters")
    assert isinstance(parameters, tuple)
    parameter = next(
        item for item in parameters if isinstance(item, RecordData) and item.get("name") == "client"
    )
    declarations: dict[str, list] = {}
    for section in facts.sections:
        if section.name.value != "symbols":
            continue
        for record in section.records:
            name = record.data.get("qualified_name")
            if record.kind in {"class", "function", "method"} and isinstance(name, str):
                declarations.setdefault(name, []).append(record)
    assert _annotation_class_origin(initializer, parameter, facts, declarations) == expected


def test_constructed_receiver_cannot_use_another_real_allocation(tmp_path):
    payload = _payload(
        tmp_path,
        "from .storage import Store\nfrom .other import Other\ndef run():\n"
        "    store = Store()\n    other = Other()\n    store.page()\n",
        other="class Other:\n    def page(self): pass\n",
    )
    decode_response(json.dumps(payload).encode())
    symbols = _records(payload, "symbols")
    calls = _records(payload, "calls")
    call = next(item for item in calls if item["data"]["expression"] == "store.page")
    constructor = next(item for item in calls if item["data"]["expression"] == "Other")
    other = next(
        item for item in symbols if item["data"].get("qualified_name") == "sample.other.Other"
    )
    method = next(
        item for item in symbols if item["data"].get("qualified_name") == "sample.other.Other.page"
    )
    binding = call["data"]["call_binding"]
    proof = binding["proof"]
    call["data"]["targets"] = ["sample.other.Other.page"]
    binding["target"] = "sample.other.Other.page"
    proof["target"] = "sample.other.Other"
    proof["constructor_evidence_id"] = constructor["evidence_ids"][0]
    proof["assignment_name"] = "other"
    proof["assignment_evidence_id"] = constructor["data"]["result_bindings"][0]["evidence_ids"][0]
    binding["evidence_ids"] = sorted(
        set(
            binding["evidence_ids"]
            + constructor["evidence_ids"]
            + constructor["data"]["result_bindings"][0]["evidence_ids"]
            + other["evidence_ids"]
            + method["evidence_ids"]
        )
    )
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


def test_native_binding_cannot_use_another_imports_witness(tmp_path):
    payload = _payload(
        tmp_path,
        "import random\nfrom secrets import token_hex\ndef run(): random.random()\n",
        native=True,
    )
    decode_response(json.dumps(payload).encode())
    calls, imports = _records(payload, "calls"), _records(payload, "imports")
    call = next(item for item in calls if item["data"]["expression"] == "random.random")
    imported = next(item for item in imports if item["data"].get("symbol") == "token_hex")
    provider = next(
        item
        for item in payload["facts"]["provider_bindings"]
        if item["qualified_name"] == "secrets.token_hex"
    )
    binding = call["data"]["call_binding"]
    binding["target"] = "secrets.token_hex"
    binding["evidence_ids"] = sorted(
        set(binding["evidence_ids"] + imported["evidence_ids"] + [provider["evidence_id"]])
    )
    binding["proof"]["target"] = "secrets.token_hex"
    binding["proof"]["provider_evidence_id"] = provider["evidence_id"]
    call["data"]["targets"] = ["secrets.token_hex"]
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


@pytest.mark.parametrize(
    "caller,first,second,other,native",
    [
        (
            "from .storage import Store\nfrom .other import Other\n"
            "class Holder:\n def __init__(self, client: Store, alt: Other):\n"
            "  self.client=client\n  self.alt=alt\n"
            " def run(self):\n  self.client.page()\n  self.alt.page()\n",
            "self.client.page",
            "self.alt.page",
            "class Other:\n def page(self): pass\n",
            False,
        ),
        (
            "from .storage import Store\nfrom .other import Other\ndef run():\n"
            " store=Store()\n other=Other()\n store.page()\n other.page()\n",
            "store.page",
            "other.page",
            "class Other:\n def page(self): pass\n",
            False,
        ),
        (
            "import random\nfrom secrets import token_hex\ndef run():\n"
            " random.random()\n token_hex(8)\n",
            "random.random",
            "token_hex",
            "",
            True,
        ),
    ],
)
def test_call_identity_cannot_be_grafted_from_a_real_sibling_site(
    tmp_path, caller, first, second, other, native
):
    payload = _payload(
        tmp_path,
        caller,
        other=other,
        native=native,
    )
    calls = _records(payload, "calls")
    original = next(item for item in calls if item["data"]["expression"] == first)
    witness = next(item for item in calls if item["data"]["expression"] == second)
    original["data"]["expression"] = witness["data"]["expression"]
    original["evidence_ids"] = witness["evidence_ids"]
    for key in ("call_binding", "targets", "target_evidence_ids"):
        original["data"][key] = witness["data"][key]
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())
