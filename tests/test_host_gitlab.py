# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from archkeel.host.gitlab import load_gitlab_records
from archkeel.ir.host_records import HostRecord, OrderingError

E = "e" * 40
H = "c" * 40
ENV = {"CI_PROJECT_ID": "7", "CI_MERGE_REQUEST_IID": "11", "CI_COMMIT_SHA": H}


def test_gitlab_versions_become_exact_host_records(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = "\n".join(
        (
            f'{{"head_commit_sha":"{E}","created_at":"2026-01-01T10:00:00Z"}}',
            f'{{"head_commit_sha":"{H}","created_at":"2026-01-01T11:00:00Z"}}',
        )
    )

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args[0] == [
            "glab",
            "api",
            "--paginate",
            "--output",
            "ndjson",
            "projects/7/merge_requests/11/versions",
        ]
        assert kwargs["cwd"] == tmp_path
        return subprocess.CompletedProcess(args[0], 0, stdout=output, stderr="")

    monkeypatch.setattr("archkeel.host.gitlab.subprocess.run", run)
    assert load_gitlab_records(tmp_path, expectation_sha=E, candidate_sha=H, environ=ENV) == (
        HostRecord(E, "expectation_published", "2026-01-01T10:00:00Z"),
        HostRecord(H, "candidate_submitted", "2026-01-01T11:00:00Z"),
    )


def test_gitlab_json_array_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "archkeel.host.gitlab.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout=json.dumps([{"head_commit_sha": E, "created_at": "2026-01-01T10:00:00Z"}]),
            stderr="",
        ),
    )
    assert load_gitlab_records(Path("."), expectation_sha=E, candidate_sha=H, environ=ENV) == (
        HostRecord(E, "expectation_published", "2026-01-01T10:00:00Z"),
    )


def test_gitlab_failed_request_is_not_silently_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "archkeel.host.gitlab.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, stdout="", stderr="denied"),
    )
    with pytest.raises(OrderingError, match="denied"):
        load_gitlab_records(Path("."), expectation_sha=E, candidate_sha=H, environ=ENV)


def test_gitlab_malformed_version_row_is_not_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "archkeel.host.gitlab.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=json.dumps([{"head_commit_sha": E, "extra": "value"}]), stderr=""
        ),
    )
    with pytest.raises(OrderingError, match="invalid diff-version record"):
        load_gitlab_records(Path("."), expectation_sha=E, candidate_sha=H, environ=ENV)


def test_missing_glab_is_not_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("glab")

    monkeypatch.setattr("archkeel.host.gitlab.subprocess.run", missing)
    with pytest.raises(OrderingError, match="glab"):
        load_gitlab_records(Path("."), expectation_sha=E, candidate_sha=H, environ=ENV)
