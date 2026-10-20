# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Call ownership follows bound declarations, not matching method names."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_exact_module_ownership import _component, _observe_tree, _rule

from archkeel.ir.decisions import rule_assessments
from archkeel.ir.model import SCHEMA_VERSION

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("allowed,expected", [((), "FAIL"), (("sample.caller",), "PASS")])
def test_saved_call_policy_requires_a_reader_with_the_new_wire_version(tmp_path, allowed, expected):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes

    result, row = _observe(
        tmp_path,
        "from .storage import Storage\ndef run(c: Storage):\n    c.page()\n",
        allowed=allowed,
    )
    assert result.observation.schema_version == SCHEMA_VERSION
    assert row.status == expected and row.evaluation_proven
    saved = tmp_path / "architecture.json"
    saved.write_bytes(canonical_report_bytes(result.observation))
    replay = run_saved_report(saved)
    [replayed] = replay.rule_assessments
    assert replayed == row


def test_saved_observation_21_rejects_extended_call_identity(tmp_path):
    from archkeel.ir.codec import observation_payload, parse_observation

    result, _ = _observe(
        tmp_path,
        "from .storage import Storage\nclass Holder:\n"
        "    def __init__(self, client: Storage): self.client = client\n"
        "    def run(self): self.client.page()\n",
        allowed=(),
    )
    payload = observation_payload(result.observation)
    payload["schema_version"] = "2.3.0"
    with pytest.raises(ValueError, match="extended call bindings require observation schema 2.4.0"):
        parse_observation(payload)


def test_stored_receiver_assessment_survives_saved_report_replay(tmp_path):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes

    result, row = _observe(
        tmp_path,
        "from .storage import Storage\nclass Holder:\n"
        "    def __init__(self, client: Storage): self.client = client\n"
        "    def run(self): self.client.page()\n",
        allowed=(),
    )
    path = tmp_path / "architecture.json"
    path.write_bytes(canonical_report_bytes(result.observation))
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed == row


@pytest.mark.parametrize("mounted", [False, True])
def test_stored_typed_receiver_is_proven_beyond_candidate_resolution(tmp_path, mounted):
    result, row = _observe(
        tmp_path,
        "from .storage import Storage\nclass Holder:\n"
        "    def __init__(self, client: Storage): self.client = client\n"
        "    def run(self): self.client.page()\n",
        allowed=(),
        mounted=mounted,
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "self.client.page"
    )
    assert call.data.get("targets") == ("sample.storage.Storage.page",)
    assert call.data.get("call_binding").get("target") == "sample.storage.Storage.page"
    assert row.status == "FAIL" and row.count == 1


def test_unicode_python_identifier_stored_receiver_is_proven(tmp_path):
    result, row = _observe(
        tmp_path,
        "from .storage import Storage\nclass Holder:\n"
        "    def __init__(self, café: Storage): self.café = café\n"
        "    def run(self): self.café.page()\n",
        allowed=(),
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "self.café.page"
    )
    assert call.data.get("call_binding").get("target") == "sample.storage.Storage.page"
    assert row.status == "FAIL" and row.count == 1


@pytest.mark.parametrize(
    "caller",
    [
        "from .storage import Storage\nclass Holder:\n"
        "    def __init__(self, client: Storage, flag: bool):\n"
        "        if flag: self.client = client\n"
        "    def run(self): self.client.page()\n",
        "from .storage import Storage\nclass Holder:\n"
        "    def __init__(self):\n        client = object(); self.client = client\n"
        "    def run(self): self.client.page()\n",
        "from .storage import Storage\nclass Holder:\n"
        "    def __init__(self, client: Storage): self.client = client\n"
        "    def run(self):\n        self = object(); self.client.page()\n",
    ],
)
def test_stored_receiver_mutations_and_shadowing_stay_unknown(tmp_path, caller):
    result, row = _observe(tmp_path, caller, allowed=())
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "self.client.page"
    )
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN"


def test_mixed_known_violation_and_unknown_receiver_keeps_failure_visible(tmp_path):
    result, row = _observe(
        tmp_path,
        "from .storage import Storage\nclass Holder:\n"
        "    def __init__(self, client: Storage): self.client = client\n"
        "    def run(self): self.client.page()\n"
        "def uncertain(client): client.page()\n",
        allowed=(),
    )
    assert row.status == "FAIL" and row.count == 1 and not row.evaluation_proven
    assert any(item.kind == "call_owner" for item in result.observation.records("violations"))
    assert any(item.kind == "call_owner_limit" for item in result.observation.records("unknowns"))


@pytest.mark.parametrize(
    "caller,expression",
    [
        ("from .storage import Store\ndef run(): Store().page()\n", "Store().page"),
        (
            "from .storage import Store\ndef run():\n    store = Store()\n    store.page()\n",
            "store.page",
        ),
    ],
)
def test_proven_default_construction_binds_method_identity(tmp_path, caller, expression):
    result, row = _observe(
        tmp_path,
        caller,
        target="sample.storage.Store.page",
        allowed=(),
        extra={"sample/storage.py": "class Store:\n    def page(self): pass\n"},
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == expression
    )
    assert call.data.get("call_binding").get("target") == "sample.storage.Store.page"
    assert row.status == "FAIL" and row.count == 1


@pytest.mark.parametrize(
    "caller,provider",
    [
        (
            "from .storage import Store\ndef run():\n    store = Store()\n"
            "    store = unknown_factory()\n    store.page()\n",
            "class Store:\n    def page(self): pass\n",
        ),
        (
            "from .storage import Store\ndef run(): Store().page()\n",
            "class Store:\n    def __new__(cls): return object.__new__(cls)\n"
            "    def page(self): pass\n",
        ),
    ],
)
def test_conflicting_or_custom_allocation_remains_unknown(tmp_path, caller, provider):
    result, row = _observe(
        tmp_path,
        caller,
        target="sample.storage.Store.page",
        allowed=(),
        extra={"sample/storage.py": provider},
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") in {"Store().page", "store.page"}
    )
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize(
    "mutations",
    [
        "self.client = Other()",
        "del self.client",
        "def __getattribute__(self, name): return super().__getattribute__(name)",
    ],
)
def test_changed_or_dynamic_stored_receiver_remains_unknown(tmp_path, mutations):
    init_body = "self.client = client"
    run_body = ""
    if mutations.startswith("del ") or mutations.startswith("self.client ="):
        run_body = f"\n    def mutate(self): {mutations}"
    else:
        init_body += "\n    " + mutations
    result, row = _observe(
        tmp_path,
        "from .storage import Storage\nclass Holder:\n"
        f"    def __init__(self, client: Storage): {init_body}\n"
        "    def run(self): self.client.page()"
        f"{run_body}\n",
        allowed=(),
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "self.client.page"
    )
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize(
    "caller,target,expression",
    [
        ("import random\ndef run(): random.random()\n", "random.random", "random.random"),
        (
            "import random as rng\ndef run(): rng.Random().random()\n",
            "random.Random.random",
            "rng.Random().random",
        ),
        (
            "from datetime import datetime as clock\ndef run(): clock.now()\n",
            "datetime.datetime.now",
            "clock.now",
        ),
        (
            "from secrets import token_hex as token\ndef run(): token()\n",
            "secrets.token_hex",
            "token",
        ),
    ],
)
def test_selected_stdlib_calls_use_import_bound_runtime_identity(
    tmp_path, caller, target, expression
):
    result, row = _observe(tmp_path, caller, target=target, allowed=())
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == expression
    )
    binding = call.data.get("call_binding")
    assert binding is not None and binding.get("target") == target
    assert len(binding.get("evidence_ids")) >= 2
    assert row.status == "FAIL" and row.count == 1


def test_observed_native_target_can_prove_allowed_owner_rule(tmp_path):
    _result, row = _observe(
        tmp_path,
        "import random\ndef run(): random.random()\n",
        target="random.random",
        allowed=("sample.caller.run",),
    )
    assert row.status == "PASS" and row.evaluation_proven


def test_unobserved_native_target_stays_unknown(tmp_path):
    _result, row = _observe(
        tmp_path,
        "def run(): pass\n",
        target="random.random",
        allowed=("sample.caller.run",),
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven


def test_shadowed_stdlib_spelling_does_not_get_native_call_identity(tmp_path):
    result, row = _observe(
        tmp_path,
        "class Other:\n    def random(self): pass\ndef run(random: Other): random.random()\n",
        target="random.random",
        allowed=(),
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "random.random"
    )
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven


def test_native_provider_reassignment_revokes_identity(tmp_path):
    result, row = _observe(
        tmp_path,
        "import random as rng\ndef run():\n    rng = unknown_factory()\n    rng.random()\n",
        target="random.random",
        allowed=(),
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "rng.random"
    )
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven


def test_native_member_mutation_revokes_identity(tmp_path):
    result, row = _observe(
        tmp_path,
        "import random\ndef run():\n    random.random = unknown\n    random.random()\n",
        target="random.random",
        allowed=(),
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "random.random"
    )
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize(
    "caller",
    [
        "from datetime import datetime as clock\n"
        "def run():\n    clock.now = unknown\n    clock.now()\n",
        "import sys\nimport datetime\n"
        "sys.modules['datetime'] = unknown\ndef run(): datetime.datetime.now()\n",
        "import datetime\ndatetime.datetime = unknown\ndef run(): datetime.datetime.now()\n",
        "import sys\nmodules = sys.modules\nimport datetime\n"
        "modules['datetime'] = unknown\ndef run(): datetime.datetime.now()\n",
        "class datetime:\n    class datetime:\n        def now(self): pass\n"
        "def run(): datetime.datetime.now()\n",
    ],
)
def test_datetime_shadow_or_revocation_stays_unknown(tmp_path, caller):
    result, row = _observe(
        tmp_path,
        caller,
        target="datetime.datetime.now",
        allowed=(),
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression").endswith("now")
    )
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven


def test_inherited_stored_receiver_resolves_only_its_unique_base_method(tmp_path):
    result, row = _observe(
        tmp_path,
        "from .storage import Store\nclass Holder:\n"
        "    def __init__(self, client: Store): self.client = client\n"
        "    def run(self): self.client.page()\n",
        target="sample.storage.Base.page",
        allowed=(),
        extra={
            "sample/storage.py": "class Base:\n    def page(self): pass\nclass Store(Base): pass\n"
        },
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "self.client.page"
    )
    assert call.data.get("call_binding").get("target") == "sample.storage.Base.page"
    assert row.status == "FAIL" and row.count == 1


def _observe(
    root,
    caller,
    *,
    source="sample",
    allowed=("sample.storage",),
    exact=(),
    mounted=False,
    target="sample.storage.Storage.page",
    extra=None,
):
    contract = {
        "schema_version": "3.7.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "call_owner",
                source=source,
                target=target,
                allowed_sources=list(allowed),
                exact_sources=list(exact),
            )
        ],
    }
    files = {
        "sample/__init__.py": "",
        "sample/storage.py": "from typing import Protocol\nclass Storage(Protocol):\n"
        "    def page(self) -> None: ...\ndef settle() -> None: pass\n",
        "sample/caller.py": caller,
    }
    files.update(extra or {})
    if mounted:
        import json

        files["inside.json"] = json.dumps(contract)
        contract = {
            "schema_version": "3.7.0",
            "components": [_component("all", ["sample"], inside="inside.json")],
            "rules": [],
        }
    result = _observe_tree(root, files, contract)
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "call_owner"
    ]
    return result, row


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize(
    "caller,allowed,expected",
    [
        (
            "from .storage import Storage\ndef run(client: Storage):\n    client.page()\n",
            ("sample.storage",),
            "FAIL",
        ),
        (
            "from .storage import Storage\ndef run(client: Storage):\n    client.page()\n",
            ("sample.caller.run",),
            "PASS",
        ),
        (
            "class Other:\n    def page(self) -> None: pass\n"
            "def run(client: Other):\n    client.page()\n",
            ("sample.storage",),
            "PASS",
        ),
        ("def run(client):\n    client.page()\n", ("sample.storage",), "UNKNOWN"),
    ],
)
def test_native_receiver_owner(tmp_path, caller, allowed, expected, mounted):
    result, row = _observe(tmp_path, caller, allowed=allowed, mounted=mounted)
    assert row.status == expected, row
    assert row.evaluation_proven is (expected != "UNKNOWN")
    if expected == "FAIL":
        [violation] = result.observation.records("violations")
        assert violation.evidence_ids and violation.fact_ids and violation.rule_ids


@pytest.mark.parametrize(
    "caller",
    [
        "from .storage import Storage\ndef run(client: Storage, other):\n"
        "    client = other\n    client.page()\n",
        "from .storage import Storage\ndef run(client: Storage):\n"
        "    client.page = replacement\n    client.page()\n",
        "class Other:\n    def page(self) -> None: pass\ndef run(client: Other):\n"
        "    client.page = replacement\n    client.page()\n",
        "def run(unknown):\n    unknown()\n",
        "from .storage import Storage\nclass Other:\n    def page(self): pass\n"
        "Other.page = Storage.page\ndef run(client: Other):\n    client.page()\n",
        "from .storage import Storage\nclass Other:\n    def page(self): pass\n"
        "Storage.page = Other.page\ndef run(client: Storage):\n    client.page()\n",
    ],
)
def test_unproven_binding_never_certifies_disjointness(tmp_path, caller):
    _, row = _observe(tmp_path, caller)
    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize(
    "body",
    [
        "from .storage import settle\nsettle()\n",
        "from .storage import settle as alias\nalias()\n",
    ],
)
def test_direct_lexical_calls_use_the_scanned_declaration(tmp_path, body):
    _, row = _observe(tmp_path, body, target="sample.storage.settle")
    assert row.status == "FAIL" and row.evaluation_proven


def test_reexport_candidate_does_not_prove_a_different_target(tmp_path):
    _, row = _observe(
        tmp_path,
        "from .facade import settle\nsettle()\n",
        target="sample.storage.settle",
        extra={"sample/facade.py": "from .storage import settle\n"},
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize(
    "caller,provider",
    [
        (
            "from .helper import harmless\nharmless()\n",
            "from .storage import settle\ndef harmless(): pass\nharmless = settle\n",
        ),
        (
            "from . import helper as Fake\ndef run(client: Fake):\n    client.page()\n",
            "def page(): pass\n",
        ),
    ],
)
def test_unstable_provider_or_nonclass_annotation_cannot_prove_disjointness(
    tmp_path, caller, provider
):
    _, row = _observe(tmp_path, caller, extra={"sample/helper.py": provider})
    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize("mutation", [False, True])
def test_remote_provider_rebinding_preserves_only_the_unmutated_alias(tmp_path, mutation):
    extra = {"sample/helper.py": "def harmless(): pass\n"}
    if mutation:
        extra["sample/patch.py"] = (
            "from . import helper\nfrom .storage import settle\nhelper.harmless = settle\n"
        )
    _, row = _observe(
        tmp_path,
        ("from . import patch\n" if mutation else "")
        + "from .helper import harmless as invoke\ninvoke()\n",
        target="sample.storage.settle",
        extra=extra,
    )
    assert row.status == ("UNKNOWN" if mutation else "PASS")
    assert row.evaluation_proven is (not mutation)


def test_known_violation_remains_fail_beside_an_unknown_call(tmp_path):
    _, row = _observe(
        tmp_path,
        "from .storage import Storage\ndef run(client: Storage, unknown):\n"
        "    client.page()\n    unknown()\n",
    )
    assert row.status == "FAIL" and not row.evaluation_proven


def test_allowed_function_can_contain_unknown_calls(tmp_path):
    _, row = _observe(
        tmp_path, "def run(unknown):\n    unknown()\n", allowed=("sample.caller.run",)
    )
    assert row.status == "PASS" and row.evaluation_proven


@pytest.mark.parametrize(
    "source,caller",
    [
        ("sample.absent", "VALUE = 1\n"),
        ("sample.caller", "def broken(:\n"),
    ],
)
def test_missing_scope_or_parse_failure_is_unknown(tmp_path, source, caller):
    _, row = _observe(tmp_path, caller, source=source)
    assert row.status == "UNKNOWN" and not row.evaluation_proven


def test_exact_function_allowance_does_not_cover_nested_function(tmp_path):
    _, row = _observe(
        tmp_path,
        "from .storage import Storage\ndef run(client: Storage):\n"
        "    def nested(client: Storage):\n        client.page()\n",
        allowed=(),
        exact=("sample.caller.run",),
    )
    assert row.status == "FAIL"


def test_exact_module_allowance_covers_its_own_functions(tmp_path):
    _, row = _observe(
        tmp_path,
        "from .storage import Storage\ndef run(client: Storage):\n    client.page()\n",
        allowed=(),
        exact=("sample.caller",),
    )
    assert row.status == "PASS" and row.evaluation_proven


@pytest.mark.parametrize(
    "caller,target",
    [
        ("VALUE = 1\n", "sample.storage.absent"),
        ("", "sample.storage.Storage.page"),
    ],
)
def test_missing_target_or_empty_source_cannot_certify_absence(tmp_path, caller, target):
    _, row = _observe(tmp_path, caller, source="sample.caller", target=target)
    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize(
    "provider,target,expected",
    [
        ("def settle(): pass\n", "settle", "PASS"),
        ("def settle(): pass\nsettle()\n", "settle", "PASS"),
        ("def settle(): pass\nsettle = other\n", "settle", "UNKNOWN"),
        ("def settle(): pass\ndel settle\n", "settle", "UNKNOWN"),
        ("@decorate\ndef settle(): pass\n", "settle", "UNKNOWN"),
        ("class Storage:\n    def page(self): pass\n", "Storage.page", "PASS"),
        (
            "class Storage:\n    def page(self): pass\n    page = other\n",
            "Storage.page",
            "UNKNOWN",
        ),
        (
            "class Storage:\n    def page(self): pass\n    del page\n",
            "Storage.page",
            "UNKNOWN",
        ),
        (
            "class Storage:\n    def page(self): pass\nStorage.page = other\n",
            "Storage.page",
            "UNKNOWN",
        ),
        (
            "class Storage:\n    def page(self): pass\nStorage = other\n",
            "Storage.page",
            "UNKNOWN",
        ),
        (
            "class Storage:\n    def page(self): pass\ndel Storage\n",
            "Storage.page",
            "UNKNOWN",
        ),
        (
            "class Storage:\n    @decorate\n    def page(self): pass\n",
            "Storage.page",
            "UNKNOWN",
        ),
        (
            "from opaque import Base\nclass Storage(Base):\n    def page(self): pass\n",
            "Storage.page",
            "UNKNOWN",
        ),
        ("class Storage: pass\n", "Storage", "PASS"),
        (
            "from dataclasses import dataclass\n@dataclass\nclass Storage:\n    value: int\n",
            "Storage",
            "PASS",
        ),
        (
            "from typing import TypedDict\nclass Storage(TypedDict):\n    value: int\n",
            "Storage",
            "PASS",
        ),
        ("class Storage: pass\nStorage = other\n", "Storage", "UNKNOWN"),
        ("class Storage: pass\ndel Storage\n", "Storage", "UNKNOWN"),
        ("@decorate\nclass Storage: pass\n", "Storage", "UNKNOWN"),
        ("from opaque import Base\nclass Storage(Base): pass\n", "Storage", "PASS"),
    ],
)
def test_uncalled_target_requires_its_binding_proof(tmp_path, provider, target, expected, mounted):
    result, row = _observe(
        tmp_path,
        "VALUE = 1\n",
        source="sample.caller",
        target=f"sample.storage.{target}",
        extra={"sample/storage.py": provider},
        mounted=mounted,
    )
    assert not [
        call
        for call in result.observation.records("calls") or ()
        if call.data.get("source_module") == "sample.caller"
    ]
    assert row.status == expected, row
    assert row.evaluation_proven is (expected != "UNKNOWN")
    if provider == "def settle(): pass\nsettle()\n":
        [symbol] = [
            item
            for item in result.observation.records("symbols")
            if item.data.get("qualified_name") == "sample.storage.settle"
        ]
        assert symbol.data.get("source_binding_static") is True
        assert symbol.data.get("source_member_binding_static") is False


@pytest.fixture
def owner_facts(tmp_path):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.protocol import (
        CollectionRequest,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    _observe(
        tmp_path, "from .storage import Storage\ndef run(client: Storage):\n    client.page()\n"
    )
    return collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )


@pytest.mark.parametrize("value", [True, False, None, 1, "true", [], {}])
def test_uncalled_function_binding_flag_has_one_boolean_contract(owner_facts, value):
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
    from archkeel.ir.protocol import CollectionResponse

    payload = json.loads(encode_response(CollectionResponse(owner_facts)))
    symbols = next(s["records"] for s in payload["facts"]["sections"] if s["name"] == "symbols")
    declaration = next(s for s in symbols if s["data"]["qualified_name"] == "sample.storage.settle")
    declaration["data"]["source_binding_static"] = value
    schema = json.loads((ROOT / "schema/source-facts.schema.json").read_bytes())
    accepted = type(value) is bool
    assert Draft202012Validator(schema).is_valid(payload) is accepted
    if accepted:
        decode_response(json.dumps(payload).encode())
    else:
        with pytest.raises(ProtocolError):
            decode_response(json.dumps(payload).encode())


def test_call_binding_response_roundtrip_and_schema(owner_facts):
    from archkeel.ir.facts_codec import decode_response, encode_response
    from archkeel.ir.protocol import CollectionResponse

    encoded = encode_response(CollectionResponse(owner_facts))
    assert encode_response(decode_response(encoded)) == encoded
    schema = json.loads((ROOT / "schema/source-facts.schema.json").read_bytes())
    assert not list(Draft202012Validator(schema).iter_errors(json.loads(encoded)))


@pytest.mark.parametrize(
    "caller,target,provider",
    [
        (
            "from .storage import Storage\nclass Holder:\n"
            "    def __init__(self, client: Storage): self.client = client\n"
            "    def run(self): self.client.page()\n",
            "sample.storage.Storage.page",
            "from typing import Protocol\nclass Storage(Protocol):\n"
            "    def page(self) -> None: ...\n",
        ),
        (
            "from .storage import Store\ndef run():\n    store = Store()\n    store.page()\n",
            "sample.storage.Store.page",
            "class Store:\n    def page(self): pass\n",
        ),
        (
            "import random\ndef run():\n    random.random()\n",
            "random.random",
            "class Store:\n    def page(self): pass\n",
        ),
    ],
)
def test_extended_call_proofs_validate_against_published_source_schema(
    tmp_path, caller, target, provider
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

    _observe(
        tmp_path,
        caller,
        target=target,
        allowed=(),
        extra={"sample/storage.py": provider},
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    encoded = encode_response(CollectionResponse(facts))
    assert encode_response(decode_response(encoded)) == encoded
    response = json.loads(encoded)
    schema = json.loads((ROOT / "schema/source-facts.schema.json").read_bytes())
    assert not list(Draft202012Validator(schema).iter_errors(response))


@pytest.mark.parametrize(
    "change",
    ["missing", "origin", "extended-origin", "target", "call-evidence", "dangling", "extra"],
)
def test_forged_or_omitted_binding_proof_is_rejected(owner_facts, change):
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
    from archkeel.ir.protocol import CollectionResponse

    payload = json.loads(encode_response(CollectionResponse(owner_facts)))
    calls = next(s["records"] for s in payload["facts"]["sections"] if s["name"] == "calls")
    data = next(r["data"] for r in calls if r["data"]["expression"] == "client.page")
    binding = data["call_binding"]
    if change == "missing":
        del data["call_binding"]
    elif change == "origin":
        binding["origin"] = "runtime_guess"
    elif change == "extended-origin":
        binding["origin"] = "stored_receiver"
    elif change == "target":
        binding["target"] = "sample.storage.settle"
    elif change == "call-evidence":
        binding["evidence_ids"] = [
            e for e in binding["evidence_ids"] if e not in calls[0]["evidence_ids"]
        ]
    elif change == "dangling":
        binding["evidence_ids"].append("missing-evidence")
    else:
        binding["allowed"] = True
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


@pytest.mark.parametrize("change", ["field", "parameter", "write_evidence", "annotation_evidence"])
def test_forged_stored_receiver_links_are_rejected(tmp_path, change):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    _observe(
        tmp_path,
        "from .storage import Storage\nclass Holder:\n"
        "    def __init__(self, client: Storage): self.client = client\n"
        "    def run(self): self.client.page()\n",
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    payload = json.loads(encode_response(CollectionResponse(facts)))
    calls = next(s["records"] for s in payload["facts"]["sections"] if s["name"] == "calls")
    call = next(r for r in calls if r["data"]["expression"] == "self.client.page")
    proof = call["data"]["call_binding"]["proof"]
    if change in {"field", "parameter"}:
        proof[change] = "other"
    else:
        unrelated = next(
            item.id for item in facts.evidence if item.id not in proof["witness_evidence_ids"]
        )
        proof["witness_evidence_ids"][0 if change == "write_evidence" else 1] = unrelated
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


def test_stored_receiver_cannot_be_retargeted_to_an_unrelated_method(tmp_path):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    _observe(
        tmp_path,
        "from .storage import Storage\nfrom .other import Other\nclass Holder:\n"
        "    def __init__(self, client: Storage): self.client = client\n"
        "    def run(self): self.client.page()\n",
        target="sample.storage.Storage.page",
        allowed=(),
        extra={
            "sample/other.py": "class Other:\n    def page(self): pass\n",
        },
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
    calls = next(s["records"] for s in sections if s["name"] == "calls")
    symbols = next(s["records"] for s in sections if s["name"] == "symbols")
    call = next(r for r in calls if r["data"]["expression"] == "self.client.page")
    other = next(r for r in symbols if r["data"].get("qualified_name") == "sample.other.Other")
    other_method = next(
        r for r in symbols if r["data"].get("qualified_name") == "sample.other.Other.page"
    )
    initializer = next(
        r for r in symbols if r["data"].get("qualified_name") == "sample.caller.Holder.__init__"
    )
    call["data"]["targets"] = ["sample.other.Other.page"]
    binding = call["data"]["call_binding"]
    binding["target"] = "sample.other.Other.page"
    binding["proof"]["target"] = "sample.other.Other"
    binding["evidence_ids"] = sorted(
        set(binding["evidence_ids"] + other["evidence_ids"] + other_method["evidence_ids"])
    )
    stored_write = next(
        item for item in initializer["data"]["stored_field_writes"] if item["field"] == "client"
    )
    stored_write["annotation_target"] = "sample.other.Other"
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


@pytest.mark.parametrize("change", ["assignment_name", "assignment_evidence"])
def test_forged_construction_assignment_link_is_rejected(tmp_path, change):
    from archkeel.analyzer.python.collect import collect
    from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    _observe(
        tmp_path,
        "from .storage import Store\ndef run():\n    store = Store()\n    store.page()\n",
        target="sample.storage.Store.page",
        extra={"sample/storage.py": "class Store:\n    def page(self): pass\n"},
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    payload = json.loads(encode_response(CollectionResponse(facts)))
    calls = next(s["records"] for s in payload["facts"]["sections"] if s["name"] == "calls")
    call = next(r for r in calls if r["data"]["expression"] == "store.page")
    proof = call["data"]["call_binding"]["proof"]
    if change == "assignment_name":
        proof[change] = "other"
    else:
        proof[change] = call["evidence_ids"][0]
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


def test_legacy_capability_cannot_certify_or_convict_the_new_rule(tmp_path, owner_facts):
    from archkeel.check.observation import assemble_observation
    from archkeel.ir.facts import CALL_BINDINGS_FEATURE

    legacy = replace(
        owner_facts,
        capabilities=replace(
            owner_facts.capabilities,
            resolution_features=tuple(
                f
                for f in owner_facts.capabilities.resolution_features
                if f != CALL_BINDINGS_FEATURE
            ),
        ),
    )
    observed, _ = assemble_observation(
        legacy,
        contract_root=tmp_path,
        contract_path=tmp_path / "contract.json",
        roots=("sample",),
        namespace="sample",
    )
    [row] = [r for r in rule_assessments(observed, undecided_by_rule={}) if r.kind == "call_owner"]
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    assert not observed.records("violations")


def test_call_owner_contract_schema_version_and_widening(tmp_path):
    from archkeel.ir.codec import contract_bytes, parse_contract
    from archkeel.ir.widening import contract_widening_changes, contract_widenings

    _observe(tmp_path, "VALUE = 1\n")
    raw = json.loads((tmp_path / "contract.json").read_bytes())
    schema = json.loads((ROOT / "schema/architecture-contract-3.7.schema.json").read_bytes())
    assert not list(Draft202012Validator(schema).iter_errors(raw))
    parsed = parse_contract(raw)
    assert parse_contract(json.loads(contract_bytes(parsed))) == parsed
    legacy = copy.deepcopy(raw)
    legacy["schema_version"] = "3.6.0"
    with pytest.raises(ValueError, match="3.7"):
        parse_contract(legacy)
    for field in ("allowed_sources", "exact_sources"):
        wider = copy.deepcopy(raw)
        wider["rules"][0].setdefault(field, []).append("sample.caller")
        assert any(
            c.field == field for c in contract_widening_changes(parsed, parse_contract(wider))
        )
    assert contract_widenings(parsed, replace(parsed, rules=()))


@pytest.mark.parametrize(
    "change",
    ["binding", "calls", "evidence", "source", "scope", "selected", "contract", "reads", "receipt"],
)
def test_saved_owner_receipt_is_bound_to_calls_and_evidence(tmp_path, change):
    from archkeel.ir.codec import observation_payload, parse_observation

    result, row = _observe(
        tmp_path, "class Other:\n    def page(self): pass\ndef run(c: Other):\n    c.page()\n"
    )
    assert row.status == "PASS" and row.evaluation_proven
    payload = observation_payload(result.observation)
    saved = parse_observation(json.loads(json.dumps(payload)))
    assert rule_assessments(saved, undecided_by_rule={}) == rule_assessments(
        result.observation, undecided_by_rule={}
    )
    changed = copy.deepcopy(payload)
    if change == "binding":
        changed["calls"][0]["data"]["call_binding"] = None
        changed["calls"][0]["data"]["call_arguments"] = None
    elif change == "calls":
        changed["calls"] = []
    elif change == "evidence":
        changed["evidence"][0]["excerpt"] = "changed evidence"
    elif change == "source":
        changed["source"]["source_digest"] = "0" * 64
    elif change == "scope":
        changed["source"]["scope"] = ["outside/**/*.py"]
    elif change == "selected":
        for record in changed["scope_observations"]:
            if record["kind"] == "rule_evaluation":
                record["data"]["call_scope_proof"]["selected_files"][0] = "outside.py"
    elif change == "contract":
        changed["contract"]["digest"] = "0" * 64
    elif change == "reads":
        changed["coverage"]["files_read"] -= 1
    else:
        for record in changed["scope_observations"]:
            if record["kind"] == "rule_evaluation":
                record["data"].pop("call_scope_proof", None)
    stale = parse_observation(changed)
    [row] = [r for r in rule_assessments(stale, undecided_by_rule={}) if r.kind == "call_owner"]
    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize(
    "mount, caller, source, expected",
    [
        ("prefix", "VALUE = 1\n", "sample", "PASS"),
        ("exact", "VALUE = 1\n", "sample", "PASS"),
        ("nested", "VALUE = 1\n", "sample", "PASS"),
        ("empty", "VALUE = 1\n", "sample", "UNKNOWN"),
        ("prefix", "", "sample", "UNKNOWN"),
        ("prefix", "VALUE = 1\n", "sample.other", "UNKNOWN"),
        ("ancestor", "VALUE = 1\n", "sample.other", "UNKNOWN"),
        (
            "prefix",
            "from ..storage import settle\nsettle()\n",
            "sample",
            "FAIL",
        ),
    ],
)
def test_mounted_call_owner_uses_actual_source_modules(tmp_path, mount, caller, source, expected):
    rule = _rule(
        "call_owner",
        source=source,
        target="sample.storage.settle",
        allowed_sources=[],
        exact_sources=[],
    )
    package = "sample.missing" if mount == "empty" else "sample.caller"
    parent = _component("narrow", [package], inside="inside.json")
    child = _component("child", [package])
    others = ["sample.storage", "sample.other"]
    files = {
        "sample/__init__.py": "",
        "sample/caller/__init__.py": caller,
        "sample/storage.py": "def settle(): pass\n",
        "sample/other.py": "from .storage import settle\nsettle()\n",
    }
    if mount == "exact":
        parent.update(packages=[], exact_modules=[package])
        child.update(packages=[], exact_modules=[package])
        others.append("sample.caller.child")
        files["sample/caller/child.py"] = "from ..storage import settle\nsettle()\n"
    inside = {"schema_version": "3.7.0", "components": [child], "rules": [rule]}
    if mount in {"nested", "ancestor"}:
        child["inside"] = "nested.json"
        inside["rules"] = []
        files["nested.json"] = json.dumps(
            {
                "schema_version": "3.7.0",
                "components": [
                    _component("leaf", ["sample.other" if mount == "ancestor" else package])
                ],
                "rules": [rule],
            }
        )
    files["inside.json"] = json.dumps(inside)
    result = _observe_tree(
        tmp_path,
        files,
        {
            "schema_version": "3.7.0",
            "components": [parent, _component("others", others)],
            "rules": [],
        },
    )
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "call_owner"
    ]
    assert row.status == expected, row
    assert row.evaluation_proven is (expected != "UNKNOWN")
    violations = result.observation.records("violations") or ()
    assert all(r.data.get("source_module") == "sample.caller" for r in violations)
    assert bool(violations) is (expected == "FAIL")
