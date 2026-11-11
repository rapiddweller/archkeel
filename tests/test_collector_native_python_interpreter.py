# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The interpreter block of a native Python request equals what the isolated child sees (AD-334).

One host function builds the block from one `python -I` child. The Python collector runs in such a
child too, and it stays unmodified: the Python codec does not read 10.0.0, so the Python collector
refuses the request, and the host cannot decode a 10.0.0 reply. No native Python reply is a PASS.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from archkeel.analyzer.interpreter import interpreter, python_request
from archkeel.analyzer.process import ProcessCollector
from archkeel.ir.protocol import (
    CollectionError,
    CollectionRequest,
    ProtocolVersion,
    PythonCollectionPhase,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)

SCHEMA = Path(__file__).parents[1] / "native/facts/schema/archkeel-request.schema.json"
_PYTHON_COLLECTOR = (sys.executable, "-I", "-B", "-m", "archkeel.analyzer.python.entry")


def _request(root: Path, exclude_tests: bool = False) -> CollectionRequest:
    return CollectionRequest(
        SnapshotInput(str(root), "a" * 40, False),
        SourceScope(("src",), "shop", exclude_tests),
        PythonSettings(phase=PythonCollectionPhase.IMPORTS),
        ProtocolVersion.V9 if exclude_tests else ProtocolVersion.V4,
    )


def _child_tables() -> dict[str, list[str]]:
    # A second, independent child: it prints the tables one name a line.
    names: dict[str, list[str]] = {}
    for table in ("stdlib_module_names", "builtin_module_names"):
        script = f"import sys; print('\\n'.join(sorted(sys.{table})))"
        output = subprocess.run(
            (sys.executable, "-I", "-B", "-c", script), capture_output=True, text=True, check=True
        ).stdout
        names[table] = output.split()
    return names


def test_the_block_holds_the_version_that_the_python_collector_child_claims(tmp_path: Path) -> None:
    (tmp_path / "src/shop").mkdir(parents=True)
    (tmp_path / "src/shop/__init__.py").write_text("import os\n", encoding="utf-8")
    response = ProcessCollector(_PYTHON_COLLECTOR).collect_response(_request(tmp_path))
    assert not isinstance(response, CollectionError), response
    block = interpreter()
    assert block.version == response.facts.runtime.version
    assert block.version.count(".") == 2


def test_the_block_holds_the_module_tables_of_an_isolated_child() -> None:
    block = interpreter()
    tables = _child_tables()
    assert list(block.stdlib_module_names) == tables["stdlib_module_names"]
    assert list(block.builtin_module_names) == tables["builtin_module_names"]
    assert interpreter() is block


def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))


def test_the_request_is_version_10_and_matches_the_committed_schema(tmp_path: Path) -> None:
    for exclude_tests in (False, True):
        raw: dict[str, Any] = json.loads(
            python_request(_request(tmp_path, exclude_tests), interpreter())
        )
        assert raw["protocol_version"] == "10.0.0"
        assert raw["scope"]["exclude_test_sources"] is exclude_tests
        assert raw["resolver"]["interpreter"]["version"] == interpreter().version
        assert _validator().is_valid(raw), list(_validator().iter_errors(raw))
        older = {**raw, "protocol_version": "9.0.0"}
        assert not _validator().is_valid(older)


def test_the_unmodified_python_collector_refuses_a_version_10_request(tmp_path: Path) -> None:
    (tmp_path / "src/shop").mkdir(parents=True)
    completed = subprocess.run(
        _PYTHON_COLLECTOR,
        input=python_request(_request(tmp_path), interpreter()),
        capture_output=True,
        check=False,
    )
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr.rstrip().endswith(
        b"ProtocolError: unsupported collection protocol version"
    )
