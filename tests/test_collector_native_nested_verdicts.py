# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-394: equal collector facts must also preserve the verdicts of mounted contracts."""

import hashlib
import shutil
from pathlib import Path
from unittest import mock

import pytest
from test_collector_native_typescript import _request

from archkeel.analyzer.process import ProcessCollector
from archkeel.cli import observe as bundled
from archkeel.ir.facts import SourceFacts
from tools import dual_run, dual_run_oracle, dual_run_python
from tools.dual_run_oracle import Selection

SCOPES = (
    "API composition",
    "Account and authentication",
    "Article and comment publishing",
)
CASES = (
    "fixture/L-nest-realworld",
    "demo/nest-realworld-project",
    "demo/nest-realworld-forbidden-edge",
    "demo/nest-realworld-signature-fail",
    "demo/nest-realworld-dynamic-unknown",
)


@pytest.fixture(scope="module", params=CASES, ids=CASES)
def mounted_verdicts(
    native_binary: Path, tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest
):
    directory = tmp_path_factory.mktemp("nested-native-install")
    binary = Path(
        shutil.copy2(native_binary, bundled.executable(bundled.TYPESCRIPT_COLLECTOR, directory))
    )
    Path(str(binary) + bundled.DIGEST_SUFFIX).write_text(
        hashlib.sha256(binary.read_bytes()).hexdigest(), encoding="ascii"
    )
    case = next(case for case in dual_run.corpus_cases() if case.id == request.param)
    with dual_run.materialized(case) as root:
        python = dual_run_oracle.read_oracle(dual_run.oracle_path(case))
        facts = ProcessCollector((str(binary),)).collect(_request(root))
        assert isinstance(facts, SourceFacts), facts
        # The debug binary has no wheel version. Normalize only its identity, as the harness does.
        with (
            mock.patch.object(bundled, "_NATIVE_DIRECTORY", directory),
            mock.patch.object(dual_run_python, "package_version", lambda: facts.adapter.version),
        ):
            native = dual_run.run_engine(case, root, None, Selection())
    assert native["architecture"] is not None
    for scope in SCOPES:
        assert python["rules"][f"{scope}:REQUIRES-COMPLETE"] == ["complete_requires", "PASS"]
    return python["rules"], native["rules"]


@pytest.mark.parametrize("scope", SCOPES)
def test_native_collection_preserves_each_mounted_requires_verdict(mounted_verdicts, scope):
    python, native = mounted_verdicts
    rule = f"{scope}:REQUIRES-COMPLETE"
    assert native[rule] == python[rule]
    assert native == python
