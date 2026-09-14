# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read merge-request diff-version evidence from GitLab."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path

from archkeel.ir.host_records import HostRecord, OrderingError, parse_records, validate_sha


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name)
    if not isinstance(value, str) or not value.isdecimal():
        raise OrderingError(f"{name} must be set to digits")
    return value


def _rows(stdout: str) -> list[object]:
    text = stdout.strip()
    if not text:
        raise OrderingError("GitLab returned no diff-version records")
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        rows: list[object] = []
        for line in text.splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise OrderingError("GitLab returned invalid NDJSON") from error
        return rows
    if not isinstance(decoded, list):
        raise OrderingError("GitLab returned an invalid diff-version page")
    return decoded


def load_gitlab_records(
    root: Path,
    *,
    expectation_sha: str,
    candidate_sha: str,
    environ: Mapping[str, str],
) -> tuple[HostRecord, ...]:
    """Map exact expectation/candidate diff versions into replayable records."""
    project_id = _required(environ, "CI_PROJECT_ID")
    merge_request_iid = _required(environ, "CI_MERGE_REQUEST_IID")
    expectation_sha = validate_sha(expectation_sha, "expectation_sha")
    candidate_sha = validate_sha(candidate_sha, "candidate_sha")
    if environ.get("CI_COMMIT_SHA") != candidate_sha:
        raise OrderingError("CI_COMMIT_SHA must equal candidate_sha")

    try:
        result = subprocess.run(
            [
                "glab",
                "api",
                "--paginate",
                "--output",
                "ndjson",
                f"projects/{project_id}/merge_requests/{merge_request_iid}/versions",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise OrderingError(f"GitLab diff-version request failed: {error}") from error
    if result.returncode:
        detail = result.stderr.strip() or "unknown error"
        raise OrderingError(f"GitLab diff-version request failed: {detail}")

    raw_records: list[dict[str, str]] = []
    for row in _rows(result.stdout):
        if not isinstance(row, dict) or not {"head_commit_sha", "created_at"} <= set(row):
            raise OrderingError("GitLab returned an invalid diff-version record")
        sha = row["head_commit_sha"]
        timestamp = row["created_at"]
        validate_sha(sha, "GitLab head_commit_sha")
        if not isinstance(timestamp, str):
            raise OrderingError("GitLab created_at is invalid")
        if sha == expectation_sha:
            raw_records.append(
                {"sha": sha, "event": "expectation_published", "timestamp": timestamp}
            )
        elif sha == candidate_sha:
            raw_records.append({"sha": sha, "event": "candidate_submitted", "timestamp": timestamp})
    return parse_records(raw_records)
