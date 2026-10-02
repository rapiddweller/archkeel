# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from archkeel.check.ordering import check_order
from archkeel.ir import host_records
from archkeel.ir.host_records import HostRecord, OrderingError, parse_records

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


def initial_pr_head():
    return host_records.InitialPRHeadEvidence(
        repository="example/project",
        repository_id=7,
        pull_request=11,
        pull_request_id=13,
        head_repository_id=17,
        initial_sha=E,
        head_sha=H,
        published_at="2026-01-01T10:00:00Z",
        collector_sha="b" * 40,
        run_id=19,
        artifact_id=23,
        artifact_digest="a" * 64,
        event_digest="f" * 64,
    )


def test_initial_expectation_head_proves_scoped_order_without_a_candidate_timestamp() -> None:
    proof = initial_pr_head()
    assert check_order(proof, expectation_sha=E, candidate_sha=H) == ()


@pytest.mark.parametrize(
    "changes",
    [
        {"initial_sha": H},
        {"head_sha": E},
        {"head_sha": "a" * 40},
        {"published_at": "2026-01-01T10:00:00"},
        {"repository_id": True},
        {"pull_request_id": 0},
        {"run_id": -1},
        {"collector_sha": "short"},
        {"artifact_digest": "not a digest"},
        {"event_digest": "not a digest"},
    ],
)
def test_invalid_initial_head_proof_is_unknown(changes: dict) -> None:
    from dataclasses import replace

    with pytest.raises(OrderingError):
        check_order(replace(initial_pr_head(), **changes), expectation_sha=E, candidate_sha=H)
