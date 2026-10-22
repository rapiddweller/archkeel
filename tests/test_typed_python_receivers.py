# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Receiver origins retain legacy inputs and conservative call evidence."""

import ast
import copy
import inspect
import json
from dataclasses import FrozenInstanceError
from enum import Enum
from pathlib import Path
from typing import get_type_hints

import pytest
from test_analyzer import _observe_one_rule, _parsed_module
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.analyzer.python import receiver_types
from archkeel.analyzer.python.calls import _bind_receiver, _local_receiver_types, collect_calls
from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.receiver_types import ReceiverType
from archkeel.analyzer.python.resolve import _resolve_receiver_bound_call, build_symbol_index
from archkeel.analyzer.python.scopes import LexicalScopes
from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
ORIGINS = ("literal", "annotation", "documented")


def _origin_type():
    annotation = get_type_hints(ReceiverType)["origin"]
    assert isinstance(annotation, type) and issubclass(annotation, Enum), annotation
    assert not issubclass(annotation, str)
    return annotation


def test_receiver_origin_field_and_existing_alias_are_nominal():
    assert receiver_types.Origin is _origin_type()


@pytest.mark.parametrize("raw", ORIGINS)
def test_receiver_constructor_normalizes_valid_legacy_origins(raw):
    value = ReceiverType("arbitrary.QualifiedType", raw)
    assert isinstance(value.origin, _origin_type())
    assert value.origin.value == raw and value.type_name == "arbitrary.QualifiedType"


@pytest.mark.parametrize("raw", ORIGINS)
def test_receiver_constructor_preserves_nominal_identity_and_immutability(raw):
    origin = _origin_type()(raw)
    value = ReceiverType("list", origin)
    assert value.origin is origin
    with pytest.raises(FrozenInstanceError):
        value.origin = origin


@pytest.mark.parametrize("raw", ["", "unknown", None, 7])
def test_receiver_constructor_rejects_invalid_origin(raw):
    with pytest.raises(ValueError):
        ReceiverType("list", raw)


def test_receiver_constructor_keeps_required_origin_parameter():
    assert inspect.signature(ReceiverType).parameters["origin"].default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        ReceiverType("list")


def test_actual_receiver_producers_publish_all_three_nominal_origins():
    module = _parsed_module(
        "from pathlib import Path\n"
        "def use(annotated: list[str]):\n"
        "    literal = []\n"
        "    documented = Path('value')\n"
    )
    collect_imports([module], set(), {}, namespace="sample")
    node = next(item for item in module.tree.body if isinstance(item, ast.FunctionDef))
    actual = _local_receiver_types(node, LexicalScopes(module))
    assert set(actual) == {"annotated", "literal", "documented"}
    assert all(isinstance(value.origin, _origin_type()) for value in actual.values())
    assert {name: value.origin.value for name, value in actual.items()} == {
        "annotated": "annotation",
        "literal": "literal",
        "documented": "documented",
    }


@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            "literal",
            ("resolved", ["builtins.list.append"], "literal-bound receiver of known type", 1),
        ),
        (
            "annotation",
            (
                "partially_resolved",
                ["builtins.list.append"],
                "annotated receiver of known type, unproven at runtime",
                1,
            ),
        ),
        (
            "documented",
            (
                "partially_resolved",
                ["builtins.list.append"],
                "receiver bound to a call result of documented type, unproven at runtime",
                1,
            ),
        ),
    ],
)
def test_legacy_origin_keeps_real_resolver_verdict_and_wire_values(raw, expected):
    assert (
        _resolve_receiver_bound_call(["items", "append"], {"items": ReceiverType("list", raw)})
        == expected
    )


@pytest.mark.parametrize(
    "first,second,expected",
    [
        ("literal", "literal", "literal"),
        ("literal", "annotation", "literal"),
        ("literal", "documented", "literal"),
        ("annotation", "literal", "literal"),
        ("annotation", "annotation", "annotation"),
        ("annotation", "documented", "annotation"),
        ("documented", "literal", "literal"),
        ("documented", "annotation", "documented"),
        ("documented", "documented", "documented"),
    ],
)
def test_legacy_origin_merge_keeps_existing_evidence_preference(first, second, expected):
    values = {"items": ReceiverType("list", first)}
    _bind_receiver(values, "items", ReceiverType("list", second))
    result = values["items"]
    assert result is not None
    origin = result.origin.value if isinstance(result.origin, Enum) else result.origin
    assert origin == expected


def test_actual_receiver_merge_has_no_raw_origin_dispatch(tmp_path):
    result = _observe_one_rule(
        tmp_path,
        {
            "kind": "forbidden_construct",
            "source": "sample.core",
            "constructs": ["string_literal_compare"],
        },
        {"core.py": (ROOT / "src/archkeel/analyzer/python/calls.py").read_text()},
    )
    assert result.diagnostics == () and result.observation is not None
    assert not [
        row
        for row in result.observation.records("constructs")
        if row.kind == "string_literal_compare"
        and row.data.get("owner") == "sample.core._bind_receiver"
    ]


@pytest.mark.parametrize(
    "source",
    [
        "def use():\n    items = []\n    items = {}\n    items.append(1)\n",
        "def use(list):\n    items = list()\n    items.append(1)\n",
        "def use():\n    items = []\n    for items in (): pass\n    items.append(1)\n",
    ],
)
def test_ambiguous_and_shadowed_receivers_stay_unresolved(source):
    rows = collect_calls([_parsed_module(source)], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "items.append")
    assert call["status"] == "unresolved" and call["targets"] == []


@pytest.mark.parametrize(
    "source,expression,target",
    [
        (
            "from subprocess import Popen as Child\n"
            "def use(process: Child[bytes]): process.poll()\n",
            "process.poll",
            "subprocess.Popen.poll",
        ),
        (
            "import subprocess as sp\ndef use(process: sp.Popen[bytes]): process.wait()\n",
            "process.wait",
            "subprocess.Popen.wait",
        ),
        (
            "from threading import Thread as Worker\ndef use(worker: Worker): worker.join()\n",
            "worker.join",
            "threading.Thread.join",
        ),
        (
            "from threading import Event as Ready\ndef use(ready: Ready): ready.set()\n",
            "ready.set",
            "threading.Event.set",
        ),
        (
            "from subprocess import Popen as Child\n"
            "def use():\n process = Child(['tool'])\n process.kill()\n",
            "process.kill",
            "subprocess.Popen.kill",
        ),
        (
            "from threading import Thread as Worker\n"
            "def use():\n worker = Worker(target=work)\n worker.start()\n",
            "worker.start",
            "threading.Thread.start",
        ),
        (
            "import threading as th\ndef use():\n ready = th.Event()\n ready.is_set()\n",
            "ready.is_set",
            "threading.Event.is_set",
        ),
    ],
)
def test_import_bound_external_receiver_calls_are_partial(source, expression, target):
    module = _parsed_module(source)
    collect_imports([module], set(), {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == expression)
    assert call["status"] == "partially_resolved" and call["targets"] == [target]


@pytest.mark.parametrize(
    "source,expression",
    [
        ("def use(process: Popen): process.poll()\n", "process.poll"),
        ("def use(process: subprocess.Popen[bytes]): process.poll()\n", "process.poll"),
        (
            "from subprocess import Popen as Child\ndef use(process: Child[str]): process.poll()\n",
            "process.poll",
        ),
        (
            "from threading import Event as Ready\ndef use(ready: Ready[int]): ready.set()\n",
            "ready.set",
        ),
        (
            "from subprocess import Popen as Child\n"
            "bytes = object\n"
            "def use(process: Child[bytes]): process.poll()\n",
            "process.poll",
        ),
        (
            "from subprocess import Popen as Child\n"
            "Child = object\n"
            "def use(process: Child[bytes]): process.poll()\n",
            "process.poll",
        ),
        (
            "from subprocess import Popen as Child\n"
            "def use(Child):\n def nested(process: Child[bytes]): process.poll()\n",
            "process.poll",
        ),
        (
            "from subprocess import Popen as Child\n"
            "def use(process: Child[bytes] | object): process.poll()\n",
            "process.poll",
        ),
        (
            "from threading import Thread as Worker\n"
            "def use(worker: Worker | None): worker.join()\n",
            "worker.join",
        ),
        (
            "from typing import Optional\n"
            "from threading import Thread as Worker\n"
            "def use(worker: Optional[Worker]): worker.join()\n",
            "worker.join",
        ),
        (
            "from subprocess import Popen as dict\n"
            "def use(roles: dict[bytes] | None): roles.get('key')\n",
            "roles.get",
        ),
    ],
)
def test_unproven_external_receiver_annotations_stay_unresolved(source, expression):
    module = _parsed_module(source)
    collect_imports([module], set(), {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == expression)
    assert call["status"] == "unresolved" and call["targets"] == []


def test_builtin_optional_receiver_keeps_guarded_generator_call_partial():
    module = _parsed_module(
        "def _ordered(roles: dict[str, set[str]] | None, fingerprints):\n"
        "    return tuple(\n"
        "        (tuple(sorted(roles.get(fingerprint, set()))) if roles is not None else ())\n"
        "        for fingerprint in fingerprints\n"
        "    )\n"
    )
    collect_imports([module], set(), {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "roles.get")
    assert call["status"] == "partially_resolved"
    assert call["targets"] == ["builtins.dict.get"]


def test_builtin_optional_receiver_needs_certain_compiler_scope():
    module = _parsed_module("def use(roles: dict[str, str] | None): roles.get('key')\n")
    collect_imports([module], set(), {}, namespace="sample")
    module.source = "def incomplete("
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "roles.get")
    assert call["status"] == "unresolved" and call["targets"] == []


def test_unchecked_builtin_optional_receiver_stays_partial():
    module = _parsed_module("def use(roles: dict[str, str] | None): return roles.get('key')\n")
    collect_imports([module], set(), {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "roles.get")
    assert call["status"] == "partially_resolved"
    assert call["targets"] == ["builtins.dict.get"]
    assert call["reason"] == "annotated receiver of known type, unproven at runtime"


def test_external_receiver_annotation_needs_its_compiler_scope():
    module = _parsed_module(
        "from subprocess import Popen as Child\ndef use(process: Child[bytes]): process.poll()\n"
    )
    collect_imports([module], set(), {}, namespace="sample")
    module.source = "def incomplete("
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "process.poll")
    assert call["status"] == "unresolved" and call["targets"] == []


@pytest.mark.parametrize(
    "source,expected_targets",
    [
        (
            "import base64\ndef use(data: bytes): return base64.b64encode(data).decode()\n",
            ["builtins.bytes.decode"],
        ),
        (
            "from base64 import urlsafe_b64encode as encode\n"
            "def use(data: bytes): return encode(data).rstrip(b'=').decode()\n",
            ["builtins.bytes.rstrip", "builtins.bytes.decode"],
        ),
        (
            "import hmac\ndef use(key: bytes, message: bytes): "
            "return hmac.digest(key, message, 'sha256').hex()\n",
            ["builtins.bytes.hex"],
        ),
        (
            "from secrets import token_bytes as make_token\n"
            "def use(): return make_token(16).hex()\n",
            ["builtins.bytes.hex"],
        ),
    ],
)
def test_import_bound_stdlib_byte_results_keep_partial_method_evidence(source, expected_targets):
    module = _parsed_module(source)
    collect_imports([module], set(), {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    calls = [row["data"] for row in rows]
    for target in expected_targets:
        assert any(
            call["status"] == "partially_resolved" and call["targets"] == [target] for call in calls
        )


@pytest.mark.parametrize(
    "source",
    [
        "import hmac\n"
        "def use(key, message): return hmac.new(key, message, 'sha256').digest().hex()\n",
        "from hmac import new as make_hmac\n"
        "def use(key, message):\n"
        "    digest = make_hmac(key, message, 'sha256')\n"
        "    return digest.digest().hex()\n",
    ],
)
def test_import_bound_hmac_result_methods_keep_partial_evidence(source):
    module = _parsed_module(source)
    collect_imports([module], set(), {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    calls = [row["data"] for row in rows]
    for target in ("hmac.HMAC.digest", "builtins.bytes.hex"):
        assert any(
            call["status"] == "partially_resolved" and call["targets"] == [target] for call in calls
        )


@pytest.mark.parametrize(
    "source",
    [
        "import custom as hmac\ndef use(k, m): return hmac.new(k, m, 'sha256').digest().hex()\n",
        "import hmac\nhmac = custom\n"
        "def use(k, m): return hmac.new(k, m, 'sha256').digest().hex()\n",
        "import hmac\nif enabled: hmac = custom\n"
        "def use(k, m): return hmac.new(k, m, 'sha256').digest().hex()\n",
        "from hmac import new as make_hmac\n"
        "make_hmac = custom\n"
        "def use(k, m): return make_hmac(k, m, 'sha256').digest().hex()\n",
        "import hmac\ndef use(hmac, k, m): return hmac.new(k, m, 'sha256').digest().hex()\n",
        "import hmac\ndef use(value: hmac.HMAC | None): return value.digest().hex()\n",
        "import hmac\ndef use(k, m): return hmac.new(k, m, 'sha256').hexdigest()\n",
    ],
)
def test_unproven_hmac_result_methods_stay_unknown(source):
    module = _parsed_module(source)
    collect_imports([module], set(), {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    hmac_targets = {"hmac.HMAC.digest", "builtins.bytes.hex", "hmac.HMAC.hexdigest"}
    assert not any(
        row["data"]["targets"] and row["data"]["targets"][0] in hmac_targets for row in rows
    )


def test_hmac_result_methods_need_their_compiler_scope():
    module = _parsed_module(
        "import hmac\ndef use(k, m): return hmac.new(k, m, 'sha256').digest().hex()\n"
    )
    collect_imports([module], set(), {}, namespace="sample")
    module.source = "def incomplete("
    rows = collect_calls([module], build_symbol_index([]), {})
    assert not any(
        row["data"]["targets"]
        and row["data"]["targets"][0] in {"hmac.HMAC.digest", "builtins.bytes.hex"}
        for row in rows
    )


@pytest.mark.parametrize(
    "source",
    [
        "import custom\ndef use(data): return custom.b64encode(data).decode()\n",
        "import base64\nbase64 = custom\ndef use(data): return base64.b64encode(data).decode()\n",
        "from base64 import b64encode as encode\n"
        "encode = custom\ndef use(data): return encode(data).decode()\n",
        "from secrets import token_bytes as make_token\n"
        "def use(make_token): return make_token(16).hex()\n",
        "import base64\nif enabled: base64 = custom\n"
        "def use(data): return base64.b64encode(data).decode()\n",
        "def use(value: bytes): return value.decode()\n",
        "def use(value: bytes | None): return value.decode()\n",
        "def use(): return b'value'.decode()\n",
    ],
)
def test_unproven_stdlib_byte_result_bindings_stay_unknown(source):
    module = _parsed_module(source)
    collect_imports([module], set(), {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    byte_method_targets = {
        "builtins.bytes.decode",
        "builtins.bytes.hex",
        "builtins.bytes.rstrip",
    }
    assert not any(
        row["data"]["targets"] and row["data"]["targets"][0] in byte_method_targets for row in rows
    )


def test_stdlib_byte_result_needs_its_compiler_scope():
    module = _parsed_module(
        "import base64\ndef use(data): return base64.b64encode(data).decode()\n"
    )
    collect_imports([module], set(), {}, namespace="sample")
    module.source = "def incomplete("
    rows = collect_calls([module], build_symbol_index([]), {})
    assert not any(row["data"]["targets"] == ["builtins.bytes.decode"] for row in rows)


@pytest.mark.parametrize("source", ["str.split('a,b', ',')", "def use(): return str.split('a')"])
def test_unshadowed_builtin_class_methods_keep_partial_evidence(source):
    rows = collect_calls([_parsed_module(source)], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "str.split")
    assert call["status"] == "partially_resolved"
    assert call["targets"] == ["builtins.str.split"]


@pytest.mark.parametrize(
    "source",
    [
        "def use(str): return str.split('value')",
        "def use():\n str = other\n return str.split('value')",
        "if enabled: str = other\nstr.split('value')",
        "from custom import str\nstr.split('value')",
        "class str:\n def split(self): pass\n def use(self): return str.split(self)",
        "str.madeup('value')",
    ],
)
def test_builtin_class_method_resolution_keeps_shadowing_and_method_table_boundaries(source):
    module = _parsed_module(source)
    collect_imports([module], {module.module}, {}, namespace="sample")
    rows = collect_calls([module], build_symbol_index([]), {})
    call = next(
        row["data"] for row in rows if row["data"]["expression"] in {"str.split", "str.madeup"}
    )
    assert "builtins.str.split" not in call["targets"]
    if source == "str.madeup('value')":
        assert call["status"] == "unresolved" and call["targets"] == []


def test_unbound_non_builtin_type_does_not_use_builtin_class_method_evidence():
    rows = collect_calls([_parsed_module("Path.read_text('value')")], build_symbol_index([]), {})
    call = next(row["data"] for row in rows if row["data"]["expression"] == "Path.read_text")
    assert call["status"] == "unresolved" and call["targets"] == []


def _receiver_repository(tmp_path):
    contract = copy.deepcopy(
        json.loads((ROOT / "docs/architecture/contracts/python.json").read_text())
    )
    contract.pop("$schema", None)
    root_contract = json.loads((ROOT / "architecture-contract.json").read_text())
    contract["rules"] = [
        rule for rule in root_contract["rules"] if rule["id"] == "PYTHON-RECEIVERS-TYPED-CONTROL"
    ]
    contract["declarations"]["uml"]["entities"] = [
        item
        for item in contract["declarations"]["uml"]["entities"]
        if item["id"].startswith("PYTHON-RECEIVER-")
    ]
    files = {
        "archkeel/__init__.py": "",
        "archkeel/analyzer/__init__.py": "",
        "archkeel/analyzer/python/__init__.py": "",
        "archkeel/analyzer/python/receiver_types.py": (
            ROOT / "src/archkeel/analyzer/python/receiver_types.py"
        ).read_text(),
        "contract.json": json.dumps(contract),
        "docs/architecture/typed-python-receivers.md": "Owned receiver origins.\n",
    }
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def test_native_receiver_api_fulfils_owned_origin_target_and_module_guard(tmp_path):
    root, config = _receiver_repository(tmp_path)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assessment = next(
        row
        for row in rule_assessments(model, undecided_by_rule={})
        if row.id == "PYTHON-RECEIVERS-TYPED-CONTROL"
    )
    assert assessment.status == "PASS" and assessment.evaluation_proven
    assert not trace_valid_violations(model)


def test_native_receiver_origin_widening_fails_unchanged_target(tmp_path):
    root, config = _receiver_repository(tmp_path)
    path = root / "archkeel/analyzer/python/receiver_types.py"
    source = path.read_text()
    assert "origin: ReceiverOrigin" in source
    path.write_text(source.replace("origin: ReceiverOrigin", "origin: str", 1))
    contract = (root / "contract.json").read_bytes()
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None
    assert any(
        item.aspect == "annotation" and item.status == "FAIL" for item in comparison.assessments
    )
    assert trace_valid_violations(model)
    assert (root / "contract.json").read_bytes() == contract


@pytest.mark.parametrize(
    "probe",
    [
        'def _probe(value):\n    return value == "literal"\n',
        'def _probe(value):\n    return value in ("literal", "annotation")\n',
        "def _probe(value):\n    return value == ReceiverOrigin.LITERAL.value\n",
    ],
)
def test_native_receiver_model_rejects_raw_origin_dispatch(tmp_path, probe):
    root, config = _receiver_repository(tmp_path)
    path = root / "archkeel/analyzer/python/receiver_types.py"
    path.write_text(path.read_text() + "\n" + probe)
    model = _model(root, config)
    assert [
        row
        for row in trace_valid_violations(model)
        if "PYTHON-RECEIVERS-TYPED-CONTROL" in row.rule_ids
    ]
