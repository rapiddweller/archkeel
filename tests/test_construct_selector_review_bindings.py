# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Review regressions for selector bindings and lexical shadowing."""

import json
import subprocess
from pathlib import Path

import pytest

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report, run_saved_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    canonical_json_bytes,
    decode_canonical_model,
    observation_payload,
    parse_observation,
)


def _contract_rule(
    rule_id: str,
    source: str,
    role: str,
    literal: str | None = None,
    receiver: str = "sample.core.Connection",
):
    selector = {
        "receiver": receiver,
        "member": "backend",
        "role": role,
    }
    if literal is not None:
        selector["literal"] = literal
    return {
        "id": rule_id,
        "kind": "forbidden_construct",
        "source": source,
        "constructs": ["string_literal_compare"],
        "selector": selector,
        "rationale": "Keep backend selection tied to its proven source binding.",
        "provenance": ["docs/architecture/selectors.md"],
        "decided_by": "architect",
    }


def _fixture_contract(*, mounted: bool) -> dict[str, object]:
    cases = (
        ("sample.core.class_constant", "equality", "flat", "sample.core.Connection"),
        (
            "sample.core.class_constant_parameter",
            "equality",
            "flat",
            "sample.core.Connection",
        ),
        ("sample.core.class_constant_local", "equality", "flat", "sample.core.Connection"),
        ("sample.core.global_tuple", "membership", "flat", "sample.core.Connection"),
        (
            "sample.core.global_tuple_parameter",
            "membership",
            "flat",
            "sample.core.Connection",
        ),
        (
            "sample.core.global_tuple_local",
            "membership",
            "flat",
            "sample.core.Connection",
        ),
        ("sample.core.inline_read", "read", None, "sample.core.Connection"),
        ("sample.holder._Holder.stored_read", "read", None, "sample.storage.Store"),
        (
            "sample.holder.EscapedHolder.escaped_read",
            "read",
            None,
            "sample.storage.Store",
        ),
        ("sample.core.inline_call", "call", None, "sample.core.Connection"),
        ("sample.holder._Holder.stored_call", "call", None, "sample.storage.Store"),
        (
            "sample.holder.EscapedHolder.escaped_call",
            "call",
            None,
            "sample.storage.Store",
        ),
    )
    rules = [
        _contract_rule(f"SELECT-{index}", source, role, literal, receiver)
        for index, (source, role, literal, receiver) in enumerate(cases, start=1)
    ]
    if not mounted:
        return {"schema_version": "3.11.0", "components": [], "rules": rules}
    provenance = ["docs/architecture/selectors.md"]
    child = {
        "schema_version": "3.11.0",
        "components": [
            {
                "id": "COMP-sample-child",
                "label": "sample child",
                "role": "component",
                "packages": ["sample"],
                "responsibilities": ["Own sample selectors."],
                "forbidden_responsibilities": [],
                "provenance": provenance,
            }
        ],
        "rules": rules,
    }
    return {
        "schema_version": "3.11.0",
        "components": [
            {
                "id": "COMP-sample-parent",
                "label": "sample parent",
                "role": "component",
                "packages": ["sample"],
                "responsibilities": ["Own the sample package."],
                "forbidden_responsibilities": [],
                "provenance": provenance,
                "inside": "inside.json",
            }
        ],
        "rules": [],
        "_inside": child,
    }


def _write_fixture(root: Path, *, mounted: bool) -> dict[str, object]:
    package = root / "sample"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "core.py").write_text(
        'class Backend:\n    DEFAULT = "flat"\n'
        "class Connection: pass\n"
        'BACKENDS = ("flat", "wide")\n'
        "def class_constant(conn: Connection):\n"
        "    conn.backend == Backend.DEFAULT\n"
        "def class_constant_parameter(conn: Connection, Backend):\n"
        "    conn.backend == Backend.DEFAULT\n"
        "def class_constant_local(conn: Connection):\n"
        "    Backend = object()\n"
        "    conn.backend == Backend.DEFAULT\n"
        "def global_tuple(conn: Connection):\n    conn.backend in BACKENDS\n"
        "def global_tuple_parameter(conn: Connection, BACKENDS):\n"
        "    conn.backend in BACKENDS\n"
        "def global_tuple_local(conn: Connection):\n"
        "    BACKENDS = unknown_values()\n"
        "    conn.backend in BACKENDS\n"
        "def inline_read():\n    Connection().backend\n"
        "def inline_call():\n    Connection().backend()\n"
    )
    (package / "storage.py").write_text("class Store:\n    backend: str\n")
    (package / "holder.py").write_text(
        "from .storage import Store\n"
        "class _Holder:\n"
        "    def __init__(self, conn: Store):\n        self.conn = conn\n"
        "    def stored_read(self):\n        self.conn.backend\n"
        "    def stored_call(self):\n        self.conn.backend()\n"
        "class EscapedHolder:\n"
        "    def __init__(self, conn: Store):\n        self.conn = conn\n"
        "    def route(self):\n        return self.conn\n"
        "    def escaped_read(self):\n        self.route().backend\n"
        "    def escaped_call(self):\n        self.route().backend()\n"
    )
    docs = root / "docs/architecture"
    docs.mkdir(parents=True)
    (docs / "selectors.md").write_text("Selector binding fixture.\n")
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    contract = _fixture_contract(mounted=mounted)
    inside = contract.pop("_inside", None)
    if inside is not None:
        (root / "inside.json").write_text(json.dumps(inside))
    (root / "contract.json").write_text(json.dumps(contract))
    for command in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "test@example.invalid"],
        ["git", "config", "user.name", "Test"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)
    return contract


@pytest.mark.parametrize("mounted", [False, True], ids=["root", "mounted"])
def test_native_selector_shadowing_and_receiver_bindings_replay(tmp_path: Path, mounted: bool):
    root = tmp_path / "repo"
    _write_fixture(root, mounted=mounted)
    result, encoded = run_report(
        root,
        config=ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        analyzer=observe,
    )
    assert encoded is not None, result.diagnostics
    expected = {
        "SELECT-1": "FAIL",
        "SELECT-2": "UNKNOWN",
        "SELECT-3": "UNKNOWN",
        "SELECT-4": "FAIL",
        "SELECT-5": "UNKNOWN",
        "SELECT-6": "UNKNOWN",
        "SELECT-7": "FAIL",
        "SELECT-8": "FAIL",
        "SELECT-9": "UNKNOWN",
        "SELECT-10": "FAIL",
        "SELECT-11": "FAIL",
        "SELECT-12": "UNKNOWN",
    }
    observed = {
        row.id.rsplit(":", maxsplit=1)[-1]: (row.status, row.evaluation_proven)
        for row in result.rule_assessments
    }
    assert {key: observed.get(key, (None, None))[0].value for key in expected} == expected, (
        observed,
        result.diagnostics,
    )

    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    selectors = [
        row
        for row in model.records("constructs")
        if row.kind == "construct_selector" and row.data.get("member") == "backend"
    ]
    assert any(
        row.data.get("owner") == "sample.core.class_constant"
        and row.data.get("literal") == "flat"
        and row.data.get("status") == "decided"
        for row in selectors
    )
    assert all(
        row.data.get("status") == "unknown"
        for row in selectors
        if row.data.get("owner")
        in {"sample.core.class_constant_parameter", "sample.core.class_constant_local"}
    )
    assert any(
        row.data.get("owner") == "sample.core.global_tuple"
        and row.data.get("literal") == "flat"
        and row.data.get("status") == "decided"
        for row in selectors
    )
    assert all(
        row.data.get("status") == "unknown"
        for row in selectors
        if row.data.get("owner")
        in {"sample.core.global_tuple_parameter", "sample.core.global_tuple_local"}
    )

    payloads = (observation_payload(model), json.loads(encoded))
    for index, payload in enumerate(payloads):
        saved = tmp_path / f"selectors-{mounted}-{index}.json"
        saved.write_bytes(canonical_json_bytes(payload))
        replay = run_saved_report(saved)
        assert not replay.diagnostics, replay.diagnostics
        replayed = {
            row.id.rsplit(":", maxsplit=1)[-1]: (row.status, row.evaluation_proven)
            for row in replay.rule_assessments or ()
        }
        assert {key: replayed[key][0].value for key in expected} == expected
        assert {key: replayed[key][1] for key in expected} == {
            key: observed[key][1] for key in expected
        }
