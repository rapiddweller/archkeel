# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Recorded Python replies fail by name when a key or content is absent (AD-394)."""

import json

import pytest
import recorded_typescript as oracle


@pytest.mark.parametrize(
    "node",
    [
        "tests/test_example.py::test_case[x@y] (call)",
        "tests/test_example.py::test_case[x@y]@test_example.py (call)",
    ],
)
def test_xdist_group_is_not_a_recorded_key(node):
    assert oracle.call_id(node) == "tests/test_example.py::test_case[x@y]"


def test_a_missing_recorded_key_has_a_named_assertion(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text(json.dumps({"replies": {}}))
    monkeypatch.setattr(oracle, "DIRECTORY", tmp_path)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_missing.py::test_missing (setup)")
    monkeypatch.delenv("ARCHKEEL_RECORD_MAIN_WORKTREE", raising=False)
    with pytest.raises(AssertionError, match="typescript_oracle_missing_key: .*test_missing"):
        oracle.read("collect", None)


def test_snapshot_header_checks_the_content_digest(tmp_path):
    (tmp_path / "main-calls.zip").write_bytes(b"changed")
    (tmp_path / "main-calls.json").write_text(
        json.dumps(
            {
                "archive": "main-calls.zip",
                "content_digest": "0" * 64,
            }
        )
    )
    with pytest.raises(AssertionError, match="typescript_oracle_content_digest_mismatch"):
        oracle.main_calls(tmp_path)
