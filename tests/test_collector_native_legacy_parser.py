# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-394: keep every recorded parser probe as native syntax and complete-fact coverage."""

import base64
import gzip
import json
from pathlib import Path

import pytest
from test_collector_native_imports import _request, _view
from test_collector_native_syntax import _in_document_order, _native
from test_collector_native_syntax import dump_binary as dump_binary

from archkeel.analyzer.process import ProcessCollector
from archkeel.ir.facts import SourceFacts

ARCHIVE = Path(__file__).with_name("typescript_legacy_parser.json.gz")
RECORDED = json.loads(gzip.decompress(ARCHIVE.read_bytes()))
CASES = [
    (f"{test}::{index}", case)
    for test, cases in RECORDED["cases"].items()
    for index, case in enumerate(cases)
]


@pytest.mark.parametrize("identity,case", CASES, ids=[identity for identity, _ in CASES])
def test_retired_parser_probe_keeps_native_syntax_and_facts(
    tmp_path: Path, native_binary: Path, dump_binary: Path, identity: str, case: dict
) -> None:
    source = tmp_path / case["rel"]
    source.parent.mkdir(parents=True)
    source.write_bytes(base64.b64decode(case["source"], validate=True))
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"allowJs":true},"include":["src"]}'
    )
    syntax = _native(dump_binary, [(case["rel"], source)])[0]["syntax"]
    syntax["import_bindings"] = _in_document_order(syntax["import_bindings"])
    assert syntax == case["syntax"], identity
    facts = ProcessCollector((str(native_binary),)).collect(
        _request(tmp_path, "app", "tsconfig.json")
    )
    assert isinstance(facts, SourceFacts), facts
    assert _view(facts) == case["facts"], identity
