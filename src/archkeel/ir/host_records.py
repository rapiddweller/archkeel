# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Host evidence values and deterministic boundary validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_EVENTS = frozenset({"expectation_published", "candidate_submitted"})


class OrderingError(ValueError):
    """Host evidence is absent or cannot prove an ordering."""


@dataclass(frozen=True)
class HostRecord:
    sha: str
    event: str
    timestamp: str


@dataclass(frozen=True, slots=True)
class InitialPRHeadEvidence:
    """Authenticated original PR head and a later head within that same PR."""

    repository: str
    repository_id: int
    pull_request: int
    pull_request_id: int
    head_repository_id: int
    initial_sha: str
    head_sha: str
    published_at: str
    collector_sha: str
    run_id: int
    artifact_id: int
    artifact_digest: str
    event_digest: str
    run_attempt: int = 1

    def __post_init__(self) -> None:
        if type(self.run_attempt) is not int or self.run_attempt != 1:
            raise OrderingError("initial PR evidence requires the original run attempt")
        if (
            not isinstance(self.repository, str)
            or not re.fullmatch(r"[\w.-]+/[\w.-]+", self.repository, re.ASCII)
            or any(part in {".", ".."} for part in self.repository.split("/"))
        ):
            raise OrderingError("initial PR repository must be owner/name")
        for value in (
            self.repository_id,
            self.pull_request,
            self.pull_request_id,
            self.head_repository_id,
            self.run_id,
            self.artifact_id,
        ):
            if type(value) is not int or value < 1:
                raise OrderingError("initial PR provider IDs must be positive integers")
        for name, sha in (
            ("initial_sha", self.initial_sha),
            ("head_sha", self.head_sha),
            ("collector_sha", self.collector_sha),
        ):
            validate_sha(sha, name)
        parse_timestamp(self.published_at)
        for digest in (self.artifact_digest, self.event_digest):
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise OrderingError("initial PR evidence needs SHA-256 digests")


def parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise OrderingError("timestamp must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OrderingError("timestamp must be a timezone-aware ISO timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OrderingError("timestamp must be a timezone-aware ISO timestamp")
    return parsed


def validate_sha(value: object, name: str = "sha") -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise OrderingError(f"{name} must be a full SHA-40")
    return value


def parse_records(raw: object) -> tuple[HostRecord, ...]:
    """Parse replayable host records without accepting extra host metadata."""
    if not isinstance(raw, list):
        raise OrderingError("host records must be a list")

    records: list[HostRecord] = []
    for raw_record in raw:
        if not isinstance(raw_record, dict) or set(raw_record) != {"sha", "event", "timestamp"}:
            raise OrderingError("each host record must contain exactly sha, event, timestamp")
        sha = validate_sha(raw_record["sha"])
        event = raw_record["event"]
        if not isinstance(event, str) or event not in _EVENTS:
            raise OrderingError("host record event is invalid")
        timestamp = raw_record["timestamp"]
        parse_timestamp(timestamp)
        records.append(HostRecord(sha=sha, event=event, timestamp=timestamp))
    return tuple(records)
