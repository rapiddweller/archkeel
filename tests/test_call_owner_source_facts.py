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


@pytest.mark.parametrize(
    "caller,extra",
    [
        (
            "from .storage import Storage\ndef run(): Storage().page('x')\n",
            {},
        ),
        (
            "from .storage import Storage\ndef run():\n"
            "    store = Storage()\n    store.page('x')\n",
            {},
        ),
    ],
    ids=["inline", "assigned"],
)
def test_constructed_receiver_keeps_identity_without_owner_escape(tmp_path, caller, extra):
    payload = _payload(
        tmp_path,
        caller,
        extra={
            **extra,
            "sample/storage.py": "class Storage:\n    def page(self, query): pass\n",
        },
    )
    facts = decode_response(json.dumps(payload).encode()).facts
    storage = next(
        record
        for section in facts.sections
        for record in section.records
        if record.data.get("qualified_name") == "sample.storage.Storage"
    )
    call = next(
        record
        for section in facts.sections
        for record in section.records
        if record.kind.endswith("_call")
        and record.data.get("expression")
        in {
            "Storage().page",
            "store.page",
        }
    )
    binding = call.data.get("call_binding")
    assert storage.data.get("source_member_owner_static") is True
    assert isinstance(binding, RecordData)
    assert binding.get("origin") == "constructed_receiver"
    assert binding.get("target") == "sample.storage.Storage.page"


def test_constructed_receiver_does_not_assume_inherited_default_constructor(tmp_path):
    payload = _payload(
        tmp_path,
        "from .storage import Storage\ndef run(): Storage().page('x')\n",
        extra={
            "sample/storage.py": (
                "class Base:\n    def page(self, query): pass\nclass Storage(Base): pass\n"
            )
        },
    )
    facts = decode_response(json.dumps(payload).encode()).facts
    classes = {
        record.data.get("qualified_name"): record
        for section in facts.sections
        for record in section.records
        if record.kind == "class"
    }
    call = next(
        record
        for section in facts.sections
        for record in section.records
        if record.kind.endswith("_call") and record.data.get("expression") == "Storage().page"
    )
    binding = call.data.get("call_binding")
    assert classes["sample.storage.Storage"].data.get("source_member_owner_static") is True
    assert classes["sample.storage.Base"].data.get("source_member_owner_static") is True
    assert classes["sample.storage.Storage"].data.get("default_instance_result") is False
    assert binding is None


@pytest.mark.parametrize("field_value", [False, None])
def test_constructed_receiver_reader_requires_owner_identity_proof(tmp_path, field_value):
    payload = _payload(
        tmp_path,
        "from .storage import Storage\ndef run(): Storage().page('x')\n",
        extra={"sample/storage.py": "class Storage:\n    def page(self, query): pass\n"},
    )
    storage = next(
        item
        for item in _records(payload, "symbols")
        if item["data"].get("qualified_name") == "sample.storage.Storage"
    )
    if field_value is None:
        storage["data"].pop("source_member_owner_static", None)
    else:
        storage["data"]["source_member_owner_static"] = field_value
    with pytest.raises(ProtocolError, match="constructed receiver"):
        decode_response(json.dumps(payload).encode())


@pytest.mark.parametrize(
    "files,caller",
    [
        (
            {
                "sample/storage.py": (
                    "class Storage:\n    def page(self, query): pass\n"
                    "def replacement(self, query): pass\nStorage.page = replacement\n"
                )
            },
            "from .storage import Storage\ndef run(): Storage().page('x')\n",
        ),
        (
            {
                "sample/storage.py": (
                    "class Storage:\n    def page(self, query): pass\n"
                    "def replacement(self, query): pass\n"
                    "def mutate(cls): cls.page = replacement\n"
                    "Alias = Storage\nmutate(Alias)\n"
                )
            },
            "from .storage import Storage\ndef run(): Storage().page('x')\n",
        ),
        (
            {
                "sample/storage.py": "class Storage:\n    def page(self, query): pass\n",
                "sample/api.py": "from .storage import Storage\n",
                "sample/mutator.py": (
                    "from .api import Storage\n"
                    "def replacement(self, query): pass\n"
                    "def mutate(cls): cls.page = replacement\nmutate(Storage)\n"
                ),
            },
            "from .api import Storage\ndef run(): Storage().page('x')\n",
        ),
        (
            {"sample/storage.py": "class Storage:\n    def page(self, query): pass\n"},
            "from .storage import Storage\n"
            "def replacement(self, query): pass\n"
            "def run():\n    store = Storage()\n"
            "    store.page = replacement\n    store.page('x')\n",
        ),
        (
            {"sample/storage.py": "class Storage:\n    def page(self, query): pass\n"},
            "from .storage import Storage\n"
            "def replacement(self, query): pass\n"
            "def mutate(instance): instance.page = replacement\n"
            "def run():\n    store = Storage()\n    mutate(store)\n    store.page('x')\n",
        ),
    ],
    ids=[
        "direct-class-mutation",
        "local-alias",
        "reexport-mutation",
        "instance-mutation",
        "instance-forwarding",
    ],
)
def test_constructed_receiver_loses_identity_after_member_escape(tmp_path, files, caller):
    extra = {**files, "sample/caller.py": caller}
    payload = _payload(tmp_path, caller, extra=extra)
    facts = decode_response(json.dumps(payload).encode()).facts
    storage = next(
        record
        for section in facts.sections
        for record in section.records
        if record.data.get("qualified_name") == "sample.storage.Storage"
    )
    call = next(
        record
        for section in facts.sections
        for record in section.records
        if record.kind.endswith("_call")
        and record.data.get("expression") in {"Storage().page", "store.page"}
    )
    assert storage.data.get("source_member_owner_static") is False
    assert call.data.get("call_binding") is None
def test_native_selector_annotation_uses_proven_reexport_origin(tmp_path):
    payload = _payload(
        tmp_path,
        "from .pkg import Store as Selected\ndef run(store: Selected): store.page()\n",
        native=True,
        extra={
            "sample/pkg/__init__.py": "from .types import Store\n",
            "sample/pkg/types.py": "class Store:\n    def page(self): pass\n",
        },
    )
    facts = decode_response(json.dumps(payload).encode()).facts
    selectors = [
        record
        for section in facts.sections
        if section.name.value == "constructs"
        for record in section.records
        if record.kind == "construct_selector"
    ]
    [selector] = selectors
    binding = selector.data.get("receiver_binding")
    assert binding is not None
    assert binding.get("origin") == "declared_receiver"
    assert binding.get("target") == "sample.pkg.types.Store"


def test_selector_proof_index_is_shared_across_multiple_source_modules(tmp_path, monkeypatch):
    payload = _payload(
        tmp_path,
        "from .storage import Store as Selected\ndef run(value: Selected): value.page()\n",
        native=True,
        extra={
            "sample/caller_two.py": "from .other_types import OtherStore as Selected\n"
            "def run(value: Selected): value.page()\n",
            "sample/other_types.py": "class OtherStore:\n    def page(self): pass\n",
        },
    )
    from archkeel.ir import facts_validation

    original = facts_validation._source_proof_index
    calls = 0

    def count_builds(files, records, selector_imports):
        nonlocal calls
        calls += 1
        return original(files, records, selector_imports)

    monkeypatch.setattr(facts_validation, "_source_proof_index", count_builds)
    facts = decode_response(json.dumps(payload).encode()).facts
    selectors = [
        record
        for section in facts.sections
        if section.name.value == "constructs"
        for record in section.records
        if record.kind == "construct_selector"
    ]
    bindings = {
        record.data.get("owner"): record.data.get("receiver_binding").get("target")
        for record in selectors
        if record.data.get("receiver_binding") is not None
    }
    assert calls == 1
    assert bindings == {
        "sample.caller.run": "sample.storage.Store",
        "sample.caller_two.run": "sample.other_types.OtherStore",
    }


def test_ambiguous_reexport_annotation_does_not_prove_selector_receiver(tmp_path):
    payload = _payload(
        tmp_path,
        "from .pkg import Store\nfrom .other import Store\ndef run(store: Store): store.page()\n",
        native=True,
        extra={
            "sample/pkg/__init__.py": "from .types import Store\n",
            "sample/pkg/types.py": "class Store:\n    def page(self): pass\n",
            "sample/other.py": "class Store:\n    def page(self): pass\n",
        },
    )
    facts = decode_response(json.dumps(payload).encode()).facts
    selectors = [
        record
        for section in facts.sections
        if section.name.value == "constructs"
        for record in section.records
        if record.kind == "construct_selector"
    ]
    assert all(
        record.data.get("receiver_binding") is None
        or record.data.get("receiver_binding").get("target") != "sample.pkg.types.Store"
        for record in selectors
    )


def test_native_imported_type_probe_has_import_evidence(tmp_path):
    payload = _payload(
        tmp_path,
        "from .types import Store as Selected\n"
        "def run(value): return isinstance(value, Selected)\n",
        native=True,
        extra={
            "sample/types.py": "class Store: pass\n",
        },
    )
    facts = decode_response(json.dumps(payload).encode()).facts
    selectors = [
        record
        for section in facts.sections
        if section.name.value == "constructs"
        for record in section.records
        if record.kind == "construct_selector"
    ]
    [selector] = selectors
    binding = selector.data.get("receiver_binding")
    assert binding is not None
    assert binding.get("target") == "sample.types.Store"
    assert binding.get("evidence_ids")


def test_native_reexported_type_probe_stays_unknown_without_an_origin_route(tmp_path):
    payload = _payload(
        tmp_path,
        "from .pkg import Store as Selected\ndef run(value): return isinstance(value, Selected)\n",
        native=True,
        extra={
            "sample/pkg/__init__.py": "from .types import Store\n",
            "sample/pkg/types.py": "class Store: pass\n",
        },
    )
    facts = decode_response(json.dumps(payload).encode()).facts
    selectors = [
        record
        for section in facts.sections
        if section.name.value == "constructs"
        for record in section.records
        if record.kind == "construct_selector"
    ]
    [selector] = selectors
    assert selector.data.get("status") == "unknown"
    assert selector.data.get("receiver_type") is None
    assert selector.data.get("receiver_binding") is None


def test_native_multiline_type_probe_stays_unknown_without_operation_excerpt(tmp_path):
    payload = _payload(
        tmp_path,
        "from .storage import Store\n"
        "def run(value):\n"
        "    return isinstance(\n"
        "        value, Store\n"
        "    )\n",
        native=True,
    )
    facts = decode_response(json.dumps(payload).encode()).facts
    selectors = [
        record
        for section in facts.sections
        if section.name.value == "constructs"
        for record in section.records
        if record.kind == "construct_selector"
    ]
    [selector] = selectors
    assert selector.data.get("selector_role") == "type_probe"
    assert selector.data.get("status") == "unknown"
    assert selector.data.get("receiver_type") is None
    assert selector.data.get("receiver_binding") is None


def test_native_nested_function_cannot_reuse_outer_parameter_binding(tmp_path):
    payload = _payload(
        tmp_path,
        "from .storage import Store\n"
        "def outer(store: Store):\n"
        "    def inner(): return store.page()\n",
        native=True,
    )
    facts = decode_response(json.dumps(payload).encode()).facts
    selectors = [
        record
        for section in facts.sections
        if section.name.value == "constructs"
        for record in section.records
        if record.kind == "construct_selector"
    ]
    [selector] = selectors
    assert selector.data.get("owner") == "sample.caller.outer.inner"
    assert selector.data.get("status") == "unknown"
    assert selector.data.get("receiver_type") is None
    assert selector.data.get("receiver_binding") is None


def test_native_module_level_local_constructor_has_a_source_binding(tmp_path):
    payload = _payload(
        tmp_path,
        "class Store: pass\nSELECTED = Store()\n",
        native=True,
    )
    facts = decode_response(json.dumps(payload).encode()).facts
    selectors = [
        record
        for section in facts.sections
        if section.name.value == "constructs"
        for record in section.records
        if record.kind == "construct_selector"
    ]
    [selector] = selectors
    assert selector.data.get("owner") == "sample.caller"
    assert selector.data.get("receiver_type") == "sample.caller.Store"
    assert selector.data.get("receiver_binding") is not None


def test_native_nested_attribute_chain_keeps_exact_declared_receiver(tmp_path):
    payload = _payload(
        tmp_path,
        "class Store:\n    parent: Store\ndef run(store: Store): return store.parent.parent\n",
        native=True,
    )
    facts = decode_response(json.dumps(payload).encode()).facts
    selectors = [
        record
        for section in facts.sections
        if section.name.value == "constructs"
        for record in section.records
        if record.kind == "construct_selector"
    ]
    [selector] = selectors
    assert selector.data.get("selector_role") == "read"
    assert selector.data.get("member") == "parent"
    assert selector.data.get("receiver_type") == "sample.caller.Store"
    assert selector.data.get("receiver_parameter") == "store"


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
