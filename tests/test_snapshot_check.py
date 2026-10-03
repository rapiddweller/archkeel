# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from pathlib import Path

import pytest

from archkeel.ir.profiles import Language
from fixtures.reproduce_snapshot_check import run_snapshot_check


@pytest.mark.parametrize("language", ["python", "dart"])
@pytest.mark.parametrize("incomplete", [False, True])
def test_committed_language_check_only_passes_complete_unchanged_candidate(
    tmp_path: Path, language: Language, incomplete: bool
) -> None:
    outcome = run_snapshot_check(tmp_path, language, incomplete=incomplete)
    assert outcome["exit_code"] == (2 if incomplete else 0), outcome["result"]
    result = outcome["result"]
    if incomplete:
        assert result["diagnostics"]
        assert result["coverage"]["status"] == "FAIL"
    else:
        assert result["expectation_fulfilled"] == "PASS"
        assert result["git_predicate"] == result["host_order"] == "PASS"
