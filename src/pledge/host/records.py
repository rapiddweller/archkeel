"""Validated host evidence records shared by adapters and policy checks."""

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
