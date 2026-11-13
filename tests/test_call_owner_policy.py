# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Call ownership follows bound declarations, not matching method names."""

from pathlib import Path

import pytest
from test_exact_module_ownership import _component, _observe_tree, _rule

from archkeel.ir.decisions import rule_assessments

ROOT = Path(__file__).parents[1]


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
