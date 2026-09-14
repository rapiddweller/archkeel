# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate the ordering evidence supplied by a forge host."""

from __future__ import annotations

from datetime import datetime

from archkeel.ir.host_records import HostRecord, OrderingError, parse_timestamp, validate_sha


def check_order(
    records: tuple[HostRecord, ...], *, expectation_sha: str, candidate_sha: str
) -> tuple[str, ...]:
    """Return ordering failures; invalid or incomplete evidence raises."""
    expectation_sha = validate_sha(expectation_sha, "expectation_sha")
    candidate_sha = validate_sha(candidate_sha, "candidate_sha")
    if expectation_sha == candidate_sha:
        raise OrderingError("expectation and candidate SHA must differ")

    published: list[datetime] = []
    submitted: list[datetime] = []
    for record in records:
        if not isinstance(record, HostRecord):
            raise OrderingError("host record is invalid")
        when = parse_timestamp(record.timestamp)
        if record.event == "expectation_published":
            if record.sha != expectation_sha:
                raise OrderingError("expectation publication SHA does not match")
            published.append(when)
        elif record.event == "candidate_submitted":
            if record.sha != candidate_sha:
                raise OrderingError("candidate submission SHA does not match")
            submitted.append(when)
        else:
            raise OrderingError("host record event is invalid")

    if not published or not submitted:
        raise OrderingError("host records do not contain both expectation and candidate evidence")

    if min(published) >= min(submitted):
        return ("expectation was not published before the first candidate submission",)
    return ()
