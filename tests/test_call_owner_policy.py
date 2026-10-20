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


@pytest.mark.parametrize("allowed,expected", [((), "FAIL"), (("sample.caller",), "PASS")])
def test_constructed_receiver_owner_is_proven_and_replays(tmp_path, allowed, expected):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes

    result, row = _observe(
        tmp_path,
        "from .storage import Storage\ndef run(): Storage().page()\n",
        allowed=allowed,
        extra={"sample/storage.py": "class Storage:\n    def page(self): pass\n"},
    )
    assert row.status == expected and row.evaluation_proven
    assert row.count == (1 if expected == "FAIL" else 0)
    path = tmp_path / "constructed-report.json"
    path.write_bytes(canonical_report_bytes(result.observation))
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed == row


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_ordinary_member_read_does_not_escape_constructed_receiver(tmp_path, mounted, columnar):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        "from .storage import Storage\ndef run():\n"
        "    built = Storage()\n    built.backend == 'flat'\n    built.page()\n",
        target="sample.storage.Storage.page",
        allowed=(),
        mounted=mounted,
        extra={"sample/storage.py": "class Storage:\n    def page(self): pass\n"},
    )
    [call] = [
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "built.page"
    ]
    assert call.data.get("call_binding").get("target") == "sample.storage.Storage.page"
    assert row.status == "FAIL" and row.evaluation_proven
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"ordinary-member-read-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed == row


def test_bare_constructed_receiver_comparison_remains_unknown(tmp_path):
    result, row = _observe(
        tmp_path,
        "from .storage import Storage\ndef run():\n"
        "    built = Storage()\n    built == object()\n    built.page()\n",
        target="sample.storage.Storage.page",
        allowed=(),
        extra={"sample/storage.py": "class Storage:\n    def page(self): pass\n"},
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "built.page"
    )
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven


def test_stored_receiver_member_comparison_keeps_public_owner_unknown(tmp_path):
    result, row = _observe(
        tmp_path,
        "from .storage import Storage\nclass Holder:\n"
        "    def __init__(self, client: Storage): self.client = client\n"
        "    def route(self):\n"
        "        self.client.backend == 'flat'\n        self.client.page()\n",
        target="sample.storage.Storage.page",
        allowed=(),
        extra={"sample/storage.py": "class Storage:\n    def page(self): pass\n"},
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "self.client.page"
    )
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven


def test_constructed_receiver_owner_escape_is_unknown_and_replays(tmp_path):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes

    result, row = _observe(
        tmp_path,
        "from .storage import Storage\n"
        "def replacement(self): pass\n"
        "def mutate(cls): cls.page = replacement\n"
        "mutate(Storage)\n"
        "def run(): Storage().page()\n",
        allowed=(),
        extra={"sample/storage.py": "class Storage:\n    def page(self): pass\n"},
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "Storage().page"
    )
    assert call.data.get("call_binding") is None
    path = tmp_path / "escaped-constructed-report.json"
    path.write_bytes(canonical_report_bytes(result.observation))
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_constructed_receiver_call_may_mutate_instance_method(tmp_path, mounted, columnar):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        "from .storage import Storage\n"
        "def run():\n"
        "    value = Storage()\n"
        "    value.prepare()\n"
        "    value.page()\n",
        target="sample.storage.Storage.page",
        allowed=(),
        mounted=mounted,
        extra={
            "sample/storage.py": "class Storage:\n"
            "    def prepare(self): self.page = lambda: None\n"
            "    def page(self): pass\n"
        },
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "value.page"
    )
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"method-mutation-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


def test_constructed_receiver_unrelated_instance_write_keeps_method_static(tmp_path):
    _, row = _observe(
        tmp_path,
        "from .storage import Storage\n"
        "def run():\n"
        "    value = Storage()\n"
        "    value.audit()\n"
        "    value.page()\n",
        target="sample.storage.Storage.page",
        allowed=(),
        extra={
            "sample/storage.py": "class Storage:\n"
            "    def audit(self): self.count = 1\n"
            "    def page(self): pass\n"
        },
    )
    assert row.status == "FAIL" and row.evaluation_proven and row.count == 1


@pytest.mark.parametrize(
    "mutator",
    [
        "alias = self if flag else object(); alias.page = replacement",
        "self.__dict__['page'] = replacement",
    ],
)
def test_constructed_receiver_alias_and_dict_writes_revoke_member(tmp_path, mutator):
    _, row = _observe(
        tmp_path,
        "from .storage import Storage\ndef run():\n    value = Storage()\n    value.page()\n",
        target="sample.storage.Storage.page",
        allowed=(),
        extra={
            "sample/storage.py": "class Storage:\n"
            f"    def prepare(self, flag=False, replacement=None): {mutator}\n"
            "    def page(self): pass\n"
        },
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_multi_target_constructed_allocation_alias_mutation_is_unknown_and_replays(
    tmp_path, mounted, columnar
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        "from .storage import Storage\n"
        "def replacement(self): pass\n"
        "def run():\n    x = alias = Storage()\n"
        "    alias.page = replacement\n    x.page()\n",
        allowed=(),
        mounted=mounted,
        extra={"sample/storage.py": "class Storage:\n    def page(self): pass\n"},
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "x.page"
    )
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"multi-target-constructed-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    "setup,escaped_receiver",
    [
        ("", "x"),
        ("alias = x\n", "alias"),
        ("box = [x]\n", "box[0]"),
        ("holder = Holder()\nholder.value = x\n", "holder.value"),
    ],
    ids=["direct-argument", "alias-argument", "container-argument", "attribute-storage"],
)
def test_constructed_receiver_escape_to_helper_is_unknown_and_replays(
    tmp_path, mounted, columnar, setup, escaped_receiver
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    caller = (
        "from .storage import Storage\n"
        "class Holder: pass\n"
        "def mutate(value): value.page = lambda: None\n"
        "def run():\n    x = Storage()\n"
        + "".join(f"    {line}\n" for line in setup.splitlines())
        + f"    mutate({escaped_receiver})\n    x.page()\n"
    )
    result, row = _observe(
        tmp_path,
        caller,
        target="sample.storage.Storage.page",
        allowed=(),
        mounted=mounted,
        extra={"sample/storage.py": "class Storage:\n    def page(self): pass\n"},
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "x.page"
    )
    assert call.data.get("call_binding") is None
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"escaped-constructed-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


def test_constructed_receiver_with_unproven_inherited_constructor_is_unknown(tmp_path):
    result, row = _observe(
        tmp_path,
        "from .storage import Storage\ndef run(): Storage().page()\n",
        target="sample.storage.Base.page",
        allowed=(),
        extra={
            "sample/storage.py": "class Base:\n def page(self): pass\nclass Storage(Base): pass\n"
        },
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "Storage().page"
    )
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven


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


@pytest.mark.parametrize(
    "allowed,expected",
    [((), "FAIL"), (("sample.caller",), "PASS")],
)
def test_stored_receiver_through_static_reexport_has_canonical_policy_result(
    tmp_path, allowed, expected
):
    result, row = _observe(
        tmp_path,
        "from .pkg import Vault as Selected\nclass Holder:\n"
        "    def __init__(self, client: Selected): self.client = client\n"
        "    def run(self): self.client.page()\n",
        allowed=allowed,
        target="sample.pkg.types.Vault.page",
        extra={
            "sample/pkg/__init__.py": "from .types import Vault\n",
            "sample/pkg/types.py": "class Vault:\n    def page(self): pass\n",
        },
    )
    [call] = [
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "self.client.page"
    ]
    assert call.data.get("call_binding").get("target") == "sample.pkg.types.Vault.page"
    assert row.status == expected and row.evaluation_proven
    assert row.count == (1 if expected == "FAIL" else 0)


@pytest.mark.parametrize(
    "allowed,expected",
    [((), "FAIL"), (("sample.caller",), "PASS")],
)
def test_declared_receiver_through_static_reexport_replays_canonical_policy(
    tmp_path, allowed, expected
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes

    result, row = _observe(
        tmp_path,
        "from .pkg import Vault as Selected\ndef run(client: Selected): client.page()\n",
        allowed=allowed,
        target="sample.pkg.types.Vault.page",
        extra={
            "sample/pkg/__init__.py": "from .types import Vault\n",
            "sample/pkg/types.py": "class Vault:\n    def page(self): pass\n",
        },
    )
    [call] = [
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "client.page"
    ]
    assert call.data.get("call_binding").get("target") == "sample.pkg.types.Vault.page"
    assert row.status == expected and row.evaluation_proven
    assert row.count == (1 if expected == "FAIL" else 0)
    saved = tmp_path / "reexport-report.json"
    saved.write_bytes(canonical_report_bytes(result.observation))
    [replayed] = run_saved_report(saved).rule_assessments
    assert replayed == row


def test_ambiguous_reexported_stored_receiver_stays_unknown(tmp_path):
    result, row = _observe(
        tmp_path,
        "from .pkg import Vault\nfrom .other import Vault\nclass Holder:\n"
        "    def __init__(self, client: Vault): self.client = client\n"
        "    def run(self): self.client.page()\n",
        allowed=(),
        target="sample.pkg.types.Vault.page",
        extra={
            "sample/pkg/__init__.py": "from .types import Vault\n",
            "sample/pkg/types.py": "class Vault:\n    def page(self): pass\n",
            "sample/other.py": "class Vault:\n    def page(self): pass\n",
        },
    )
    [call] = [
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "self.client.page"
    ]
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven


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


@pytest.mark.parametrize("hook", ["__getattr__", "__getattribute__"])
@pytest.mark.parametrize("hook_shape", ["method", "class_attribute", "conditional_method"])
@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_constructed_dynamic_attribute_hook_withholds_method_identity(
    tmp_path, hook, hook_shape, mounted, columnar
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    hook_source = (
        f"    def {hook}(self, name): return lambda: None\n"
        if hook_shape == "method"
        else (
            f"    {hook} = lambda self, name: None\n"
            if hook_shape == "class_attribute"
            else f"    if flag:\n        def {hook}(self, name): return lambda: None\n"
        )
    )
    result, row = _observe(
        tmp_path,
        "from .storage import Storage\ndef run():\n    built = Storage()\n    built.page()\n",
        target="sample.storage.Storage.page",
        allowed=(),
        mounted=mounted,
        extra={
            "sample/storage.py": "class Storage:\n" + hook_source + "    def page(self): pass\n"
        },
    )
    [call] = [
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "built.page"
    ]
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"dynamic-hook-{hook}-{hook_shape}-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == row.status == "UNKNOWN"
    assert not replayed.evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_native_mutation_in_another_module_revokes_import_identity(tmp_path, mounted, columnar):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        "import random\ndef run(): random.random()\n",
        target="random.random",
        allowed=(),
        mounted=mounted,
        extra={
            "sample/mutation.py": "import random\n"
            "def replacement(): return 0\nrandom.random = replacement\n"
        },
    )
    [call] = [
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "random.random"
    ]
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"cross-module-native-mutation-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == row.status == "UNKNOWN"
    assert not replayed.evaluation_proven


@pytest.mark.parametrize(
    "mutation",
    [
        'import sys\nsys.modules["random"].random = replacement',
        'from sys import modules as loaded\nloaded["random"].random = replacement',
        'import sys as system\ntable = system.modules\ntable["random"].random = replacement',
        'import sys\nrng = sys.modules["random"]\nrng.random = replacement',
        'import sys\ntable, = sys.modules,\ntable["random"].random = replacement',
        'import sys\nrng, = sys.modules["random"],\nrng.random = replacement',
    ],
    ids=[
        "sys-modules",
        "imported-modules",
        "aliased-modules",
        "module-object",
        "unpacked-table",
        "unpacked-module",
    ],
)
@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_sys_modules_member_mutation_revokes_native_identity(tmp_path, mutation, mounted, columnar):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        "import random\ndef replacement(): return 0\n"
        + mutation
        + "\ndef run(): random.random()\n",
        target="random.random",
        allowed=(),
        mounted=mounted,
    )
    [call] = [
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "random.random"
    ]
    assert call.data.get("call_binding") is None
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"sys-modules-mutation-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == row.status == "UNKNOWN"
    assert not replayed.evaluation_proven


@pytest.mark.parametrize(
    "target,allowed,expected,expression",
    [
        ("random.random", (), "UNKNOWN", "random.random"),
        ("secrets.token_hex", ("sample.caller.run",), "PASS", "secrets.token_hex"),
    ],
)
@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_unresolved_sys_modules_key_revokes_only_matching_native_member(
    tmp_path, target, allowed, expected, expression, mounted, columnar
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        "import random\nimport secrets\nimport sys\n"
        "def replacement(): return 0\n"
        "name = 'random'\nsys.modules[name].random = replacement\n"
        "def run():\n    random.random()\n    secrets.token_hex()\n",
        target=target,
        allowed=allowed,
        mounted=mounted,
    )
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == expression
    )
    expected_proven = expected != "UNKNOWN"
    assert row.status == expected and row.evaluation_proven is expected_proven
    assert (call.data.get("call_binding") is not None) is expected_proven
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"unresolved-sys-modules-key-{target}-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == expected and replayed.evaluation_proven is expected_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_native_provider_escape_to_mutating_helper_revokes_identity(tmp_path, mounted, columnar):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        "import random\n"
        "def replacement(): return 0\n"
        "def mutate(provider): provider.random = replacement\n"
        "def run():\n    mutate(random)\n    random.random()\n",
        target="random.random",
        allowed=(),
        mounted=mounted,
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "random.random"
    )
    assert call.data.get("call_binding") is None
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"escaped-native-provider-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    "setup,mutation",
    [
        ("alias = random\n", "mutate(alias)"),
        ("alias = random\nif flag: alias = other\n", "mutate(alias)"),
        ("", "mutate([random])"),
        ("", "mutate(provider=random)"),
    ],
    ids=["alias", "conditional-alias", "container", "keyword"],
)
def test_native_provider_escape_tracks_aliases_and_argument_shapes(
    tmp_path, mounted, columnar, setup, mutation
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    mutate = (
        "def mutate(provider): provider.random = replacement\n"
        if "provider=" not in mutation
        else "def mutate(*, provider): provider.random = replacement\n"
    )
    result, row = _observe(
        tmp_path,
        "import random\nother = object()\n"
        "def replacement(): return 0\n"
        + setup
        + mutate
        + f"{mutation}\n"
        + "def run(): random.random()\n",
        target="random.random",
        allowed=(),
        mounted=mounted,
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "random.random"
    )
    assert call.data.get("call_binding") is None
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"escaped-provider-shape-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_shadowed_setattr_is_not_treated_as_the_builtin(tmp_path, mounted, columnar):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        "import random\ndef replacement(): return 0\n"
        "def setattr(provider, *args): provider.random = replacement\n"
        "setattr(random, 'unrelated', 0)\n"
        "def run(): random.random()\n",
        target="random.random",
        allowed=(),
        mounted=mounted,
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "random.random"
    )
    assert call.data.get("call_binding") is None
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"shadowed-setattr-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    "shadow",
    [
        "def run(setattr):\n    setattr(random, 'unrelated', 0)\n    random.random()\n",
        "def run():\n    setattr = injected\n    setattr(random, 'unrelated', 0)\n"
        "    random.random()\n",
    ],
    ids=["parameter", "local"],
)
def test_native_mutator_name_must_be_an_unbound_builtin(tmp_path, mounted, columnar, shadow):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        "import random\n" + shadow,
        target="random.random",
        allowed=(),
        mounted=mounted,
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "random.random"
    )
    assert call.data.get("call_binding") is None
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"shadowed-native-mutator-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_stored_receiver_escape_to_mutating_helper_revokes_identity(tmp_path, mounted, columnar):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        "from .storage import Storage, Other\n"
        "def mutate(holder): holder.client = Other()\n"
        "class Holder:\n"
        "    def __init__(self, client: Storage): self.client = client\n"
        "    def run(self):\n        mutate(self)\n        self.client.page()\n",
        target="sample.storage.Storage.page",
        allowed=(),
        mounted=mounted,
        extra={
            "sample/storage.py": "class Storage:\n def page(self): pass\n"
            "class Other:\n def page(self): pass\n"
        },
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "self.client.page"
    )
    assert call.data.get("call_binding") is None
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"escaped-stored-receiver-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


@pytest.mark.parametrize(
    "caller,expression,extra",
    [
        (
            "from .storage import Storage\n"
            "def replacement(self): pass\n"
            "def run():\n store=Storage()\n store.page=replacement\n store.page()\n",
            "store.page",
            {"sample/storage.py": "class Storage:\n def page(self): pass\n"},
        ),
        (
            "from .storage import Storage, Other\n"
            "storage=Storage()\n"
            "class Holder:\n"
            " def __init__(self, client: Storage): self.client=client\n"
            " def run(self): self.client.page()\n"
            "holder=Holder(storage)\nholder.client=Other()\nholder.run()\n",
            "self.client.page",
            {
                "sample/storage.py": (
                    "class Storage:\n def page(self): pass\nclass Other:\n def page(self): pass\n"
                )
            },
        ),
        (
            "from .storage import Storage\n"
            "class Holder:\n"
            " def __init__(self, client: Storage): self.client=client\n"
            " def run(self): self.client.page()\n"
            "storage=Storage()\nholder=Holder(storage)\n"
            "def run(): holder.run()\n",
            "self.client.page",
            {
                "sample/storage.py": (
                    "class Storage:\n def page(self): pass\nclass Other:\n def page(self): pass\n"
                ),
                "sample/mutator.py": (
                    "from .caller import holder\nfrom .storage import Other\n"
                    "holder.client=Other()\n"
                ),
            },
        ),
    ],
    ids=["constructed-instance-write", "external-stored-field-write", "cross-module-field-write"],
)
@pytest.mark.parametrize("columnar", [False, True])
def test_receiver_member_mutation_is_unknown_in_native_and_saved_reports(
    tmp_path, caller, expression, extra, columnar
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        caller,
        target="sample.storage.Storage.page",
        allowed=(),
        extra=extra,
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == expression
    )
    assert call.data.get("call_binding") is None
    path = tmp_path / "mutated-receiver-report.json"
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


@pytest.mark.parametrize("operation", ["setattr", "delattr"])
@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_dynamic_stored_member_mutation_revokes_field_proof(tmp_path, operation, mounted, columnar):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    setter = (
        "def run(self, name, value):\n"
        "        setattr(self, name, value)\n"
        "        self.client.page()\n"
        if operation == "setattr"
        else "def run(self, name):\n        delattr(self, name)\n        self.client.page()\n"
    )
    result, row = _observe(
        tmp_path,
        "from .storage import Storage, Other\n"
        "class Holder:\n"
        "    def __init__(self, client: Storage): self.client = client\n"
        + "    "
        + setter
        + "storage = Storage()\nother = Other()\nholder = Holder(storage)\n"
        + ("holder.run(name, other)\n" if operation == "setattr" else "holder.run(name)\n"),
        target="sample.storage.Storage.page",
        allowed=(),
        mounted=mounted,
        extra={
            "sample/storage.py": "class Storage:\n    def page(self): pass\n"
            "class Other:\n    def page(self): pass\n"
        },
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "self.client.page"
    )
    assert call.data.get("call_binding") is None
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"dynamic-stored-mutation-{operation}-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


@pytest.mark.parametrize(
    "alias,mutation,allowed,expected",
    [
        ("alias = random\n", "alias.random = replacement", (), "UNKNOWN"),
        ("alias = random\nalias2 = alias\n", "alias2.random = replacement", (), "UNKNOWN"),
        ("alias = random\n", "setattr(alias, name, replacement)", (), "UNKNOWN"),
        ("alias = random\n", "delattr(alias, name)", (), "UNKNOWN"),
        ("box = [random]\n", "box[0].random = replacement", (), "UNKNOWN"),
        ("box, = [random]\n", "box.random = replacement", (), "UNKNOWN"),
        (
            "class Holder: pass\nholder = Holder()\n",
            "holder.provider = random\nholder.provider.random = replacement",
            (),
            "UNKNOWN",
        ),
        ("box = []\n", "box += [random]\nbox[0].random = replacement", (), "UNKNOWN"),
        (
            "def expose(): return random\n",
            "expose().random = replacement",
            (),
            "UNKNOWN",
        ),
        ("", "if flag:\n    alias = random\nalias.random = replacement", (), "UNKNOWN"),
        (
            "alias = random\n",
            "if flag:\n    alias = replacement\nalias.random = replacement",
            (),
            "UNKNOWN",
        ),
    ],
    ids=[
        "alias-member",
        "alias-chain",
        "alias-dynamic-setattr",
        "alias-dynamic-delattr",
        "provider-stored-in-container",
        "provider-unpacked-from-container",
        "provider-stored-on-object",
        "provider-stored-with-augassign",
        "provider-returned-and-mutated",
        "conditional-alias",
        "conditional-rebind",
    ],
)
@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_native_module_alias_mutation_revokes_only_matching_target(
    tmp_path, alias, mutation, allowed, expected, mounted, columnar
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        "import random\n"
        "def replacement(): return 0\n" + alias + mutation + "\n" + "def run(): random.random()\n",
        target="random.random",
        allowed=allowed,
        mounted=mounted,
    )
    proven = expected != "UNKNOWN"
    assert row.status == expected and row.evaluation_proven is proven
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "random.random"
    )
    assert (call.data.get("call_binding") is not None) is proven
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"native-alias-mutation-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == expected and replayed.evaluation_proven is proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_native_alias_mutation_preserves_unrelated_provider_identity(tmp_path, mounted, columnar):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        "import random\nimport secrets\n"
        "def replacement(): return 0\n"
        "alias = random\nalias.random = replacement\n"
        "def run(): secrets.token_hex()\n",
        target="secrets.token_hex",
        allowed=("sample.caller.run",),
        mounted=mounted,
    )
    assert row.status == "PASS" and row.evaluation_proven
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "secrets.token_hex"
    )
    assert call.data.get("call_binding").get("target") == "secrets.token_hex"
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"unrelated-native-provider-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == "PASS" and replayed.evaluation_proven


@pytest.mark.parametrize("columnar", [False, True])
def test_unmutated_holder_stored_receiver_remains_proven_on_replay(tmp_path, columnar):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        "from .storage import Storage\n"
        "class Holder:\n"
        " def __init__(self, client: Storage): self.client=client\n"
        " def run(self): self.client.page()\n",
        target="sample.storage.Storage.page",
        allowed=(),
    )
    assert row.status == "FAIL" and row.evaluation_proven
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "self.client.page"
    )
    assert call.data.get("call_binding").get("target") == "sample.storage.Storage.page"
    path = tmp_path / "unmutated-holder-report.json"
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == row.status
    assert replayed.evaluation_proven == row.evaluation_proven


@pytest.mark.parametrize("operation", ["setattr", "delattr"])
@pytest.mark.parametrize(
    "name_expression,expected",
    [("'random'", "UNKNOWN"), ("name", "UNKNOWN"), ("'shuffle'", "PASS")],
    ids=["matching-static-name", "unresolved-name", "unrelated-static-name"],
)
@pytest.mark.parametrize("columnar", [False, True])
def test_dynamic_native_mutation_is_bounded_and_replays(
    tmp_path, operation, name_expression, expected, columnar
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    mutation = (
        f"{operation}(random, {name_expression}, replacement)\n"
        if operation == "setattr"
        else f"{operation}(random, {name_expression})\n"
    )
    name_binding = "name = choose_name()\n" if name_expression == "name" else ""
    result, row = _observe(
        tmp_path,
        "import random\n"
        + name_binding
        + "def choose_name(): return 'random'\n"
        + "def replacement(): return 0\n"
        + "def mutate():\n    "
        + mutation
        + "mutate()\n"
        + "def run(): random.random()\n",
        target="random.random",
        allowed=("sample.caller.run", "sample.caller.mutate"),
        source="sample.caller.run",
    )
    proven = expected == "PASS"
    assert row.status == expected and row.evaluation_proven is proven
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "random.random"
    )
    if proven:
        assert call.data.get("call_binding").get("target") == "random.random"
    else:
        assert call.data.get("call_binding") is None
    path = tmp_path / "native-mutation-report.json"
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == row.status
    assert replayed.evaluation_proven == row.evaluation_proven


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


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    "caller,expected,expression",
    [
        (
            "import random\ndef run():\n    rng = random.Random()\n    rng.random()\n",
            "FAIL",
            "rng.random",
        ),
        (
            "import random\ndef replacement(self): pass\ndef run():\n"
            "    rng = alias = random.Random()\n    alias.random = replacement\n"
            "    rng.random()\n",
            "UNKNOWN",
            "rng.random",
        ),
        (
            "import random\ndef replacement(self): pass\ndef run():\n"
            "    rng = random.Random()\n    alias = rng\n"
            "    alias.random = replacement\n    rng.random()\n",
            "UNKNOWN",
            "rng.random",
        ),
        (
            "import random\ndef run(): rng = random.Random(); rng.random()\n",
            "FAIL",
            "rng.random",
        ),
        (
            "import random\ndef replacement(self): pass\ndef run():\n"
            "    rng = random.Random()\n    rng.random = replacement\n    rng.random()\n",
            "UNKNOWN",
            "rng.random",
        ),
        (
            "import random\ndef run():\n    rng = random.Random()\n"
            "    del rng.random\n    rng.random()\n",
            "UNKNOWN",
            "rng.random",
        ),
        (
            "import random\ndef run():\n    rng = random.Random()\n"
            "    delattr(rng, 'random')\n    rng.random()\n",
            "UNKNOWN",
            "rng.random",
        ),
        (
            "import random\ndef consume(value): pass\ndef run():\n"
            "    rng = random.Random()\n    consume(rng)\n    rng.random()\n",
            "UNKNOWN",
            "rng.random",
        ),
        (
            "import random\ndef run():\n    rng.random()\n    rng = random.Random()\n",
            "UNKNOWN",
            "rng.random",
        ),
    ],
    ids=[
        "unmutated-instance",
        "chained-alias-mutation",
        "assigned-alias-mutation",
        "same-line-allocation-and-call",
        "mutated-instance",
        "deleted-instance-method",
        "delattr-instance-method",
        "escaped-instance",
        "assignment-after-call",
    ],
)
def test_native_random_receiver_mutation_and_order_replay(
    tmp_path, caller, expected, expression, mounted, columnar
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        caller,
        target="random.Random.random",
        allowed=(),
        mounted=mounted,
    )
    assert row.status == expected and row.evaluation_proven is (expected != "UNKNOWN")
    [call] = [
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == expression
    ]
    if expected == "UNKNOWN":
        assert call.data.get("call_binding") is None
    else:
        assert call.data.get("call_binding", {}).get("target") == "random.Random.random"
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"random-receiver-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == expected
    assert replayed.evaluation_proven is (expected != "UNKNOWN")


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
def test_stored_property_receiver_stays_unknown_and_replays(tmp_path, mounted, columnar):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        "from .storage import Storage\nclass Holder:\n"
        "    def __init__(self, client: Storage): self.client = client\n"
        "    def run(self): self.client.page()\n",
        target="sample.storage.Storage.page",
        allowed=(),
        mounted=mounted,
        extra={
            "sample/storage.py": "class Storage:\n    @property\n    def page(self): return 1\n"
        },
    )
    assert row.status == "UNKNOWN" and not row.evaluation_proven
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == "self.client.page"
    )
    assert call.data.get("call_binding") is None
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"stored-property-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == "UNKNOWN" and not replayed.evaluation_proven


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(
    "caller,extra,expression,target,expected",
    [
        (
            "from .storage import Storage\ndef run(): Storage(\n    ).page()\n",
            {"sample/storage.py": "class Storage:\n    def page(self): pass\n"},
            "Storage().page",
            "sample.storage.Storage.page",
            "UNKNOWN",
        ),
        (
            "from .storage import Storage\nclass Holder:\n"
            "    def __init__(self, client: Storage): self.client = self.backup = client\n"
            "    def run(self): self.client.page()\n",
            {"sample/storage.py": "class Storage:\n    def page(self): pass\n"},
            "self.client.page",
            "sample.storage.Storage.page",
            "FAIL",
        ),
        (
            "from .storage import Child\ndef run(): Child().page()\n",
            {
                "sample/storage.py": "def replacement(self): pass\n"
                "class Base:\n    def page(self): pass\n"
                "class Child(Base):\n"
                "    def __init__(self): pass\n"
                "    page = replacement\n"
            },
            "Child().page",
            "sample.storage.Base.page",
            "UNKNOWN",
        ),
        (
            "from .storage import Child\ndef run(): Child().page()\n",
            {
                "sample/storage.py": "class Base:\n    def page(self): pass\n"
                "class Child(Base):\n"
                "    def __init__(self): pass\n"
                "    page = None\n"
            },
            "Child().page",
            "sample.storage.Base.page",
            "UNKNOWN",
        ),
        (
            "from .storage import Child\ndef run(): Child().page()\n",
            {
                "sample/storage.py": "class Base:\n    def page(self): pass\n"
                "class Child(Base):\n"
                "    def __init__(self): pass\n"
                "    page = 1\n"
            },
            "Child().page",
            "sample.storage.Base.page",
            "UNKNOWN",
        ),
        (
            "from .storage import Child\ndef run(client: Child): client.page()\n",
            {
                "sample/storage.py": "def replacement(self): pass\n"
                "class Base:\n    def page(self): pass\n"
                "class Child(Base):\n    page = replacement\n"
            },
            "client.page",
            "sample.storage.Base.page",
            "UNKNOWN",
        ),
    ],
    ids=[
        "multiline-constructor",
        "chained-stored-write",
        "inherited-class-attribute",
        "inherited-class-attribute-none",
        "inherited-class-attribute-literal",
        "declared-inherited-class-attribute",
    ],
)
def test_call_owner_multiline_chain_and_inherited_shadow_replay(
    tmp_path, caller, extra, expression, target, expected, mounted, columnar
):
    from archkeel.check.report import run_saved_report
    from archkeel.ir.codec import canonical_report_bytes, observation_payload

    result, row = _observe(
        tmp_path,
        caller,
        target=target,
        allowed=(),
        mounted=mounted,
        extra=extra,
    )
    assert row.status == expected
    assert row.evaluation_proven is (expected != "UNKNOWN")
    call = next(
        record
        for record in result.observation.records("calls")
        if record.data.get("expression") == expression
    )
    assert (call.data.get("call_binding") is not None) is (expected != "UNKNOWN")
    saved = (
        canonical_report_bytes(result.observation)
        if columnar
        else json.dumps(observation_payload(result.observation)).encode()
    )
    path = tmp_path / f"call-owner-proof-boundary-{mounted}-{columnar}.json"
    path.write_bytes(saved)
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.status == expected
    assert replayed.evaluation_proven is (expected != "UNKNOWN")


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


@pytest.mark.parametrize("change", ["relocate", "delete", "change"])
def test_saved_owner_receipt_binds_rule_result_section_and_contents(tmp_path, change):
    from archkeel.ir.codec import observation_payload, parse_observation

    result, row = _observe(
        tmp_path,
        "from .storage import Storage\ndef run(c: Storage):\n    c.page()\n",
        allowed=(),
    )
    assert row.status == "FAIL" and row.evaluation_proven
    payload = observation_payload(result.observation)
    [violation] = payload["violations"]
    if change == "relocate":
        payload["violations"].clear()
        payload["scope_observations"].append(violation)
    elif change == "delete":
        payload["violations"].clear()
    else:
        violation["title"] = "changed finding"
    saved = parse_observation(payload)
    [replayed] = [
        item for item in rule_assessments(saved, undecided_by_rule={}) if item.kind == "call_owner"
    ]
    assert replayed.status != "PASS" and not replayed.evaluation_proven


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
