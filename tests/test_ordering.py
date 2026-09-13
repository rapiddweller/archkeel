# Pledge
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from pledge.check.ordering import check_order
from pledge.host.records import HostRecord, OrderingError, parse_records

E = "e" * 40
H = "c" * 40


def record(sha: str, event: str, timestamp: str) -> HostRecord:
    return HostRecord(sha=sha, event=event, timestamp=timestamp)


def test_submission_before_publication_is_a_failure() -> None:
    assert check_order(
        (
            record(H, "candidate_submitted", "2026-01-01T10:00:00+00:00"),
            record(E, "expectation_published", "2026-01-01T11:00:00+00:00"),
        ),
        expectation_sha=E,
        candidate_sha=H,
    ) == ("expectation was not published before the first candidate submission",)


@pytest.mark.parametrize(
    "records",
    [
        (),
        (record(E, "expectation_published", "2026-01-01T10:00:00+00:00"),),
        (record("a" * 40, "candidate_submitted", "2026-01-01T11:00:00+00:00"),),
    ],
)
def test_missing_or_mismatched_evidence_is_unknown(records: tuple[HostRecord, ...]) -> None:
    with pytest.raises(OrderingError):
        check_order(records, expectation_sha=E, candidate_sha=H)


def test_equal_times_are_a_failure() -> None:
    timestamp = "2026-01-01T10:00:00+00:00"
    assert check_order(
        (
            record(E, "expectation_published", timestamp),
            record(H, "candidate_submitted", timestamp),
        ),
        expectation_sha=E,
        candidate_sha=H,
    )


def test_first_submission_cannot_be_hidden_by_resubmission() -> None:
    assert check_order(
        (
            record(E, "expectation_published", "2026-01-01T10:00:00+00:00"),
            record(H, "candidate_submitted", "2026-01-01T09:00:00+00:00"),
            record(H, "candidate_submitted", "2026-01-01T11:00:00+00:00"),
        ),
        expectation_sha=E,
        candidate_sha=H,
    )


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(OrderingError):
        parse_records(
            [{"sha": E, "event": "expectation_published", "timestamp": "2026-01-01T10:00:00"}]
        )
