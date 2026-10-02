# AD-143 Initial PR head proves scoped order

## Problem

Recent pushes cannot prove the first H submission. An authentic original PR
opened with E proves E precedes every H submitted to that same PR.

## Decision

`InitialPRHeadEvidence` is a typed alternative at the existing Host/order boundary.
It binds original E and authoritative later H to exact provider repository/PR IDs,
the approved worker B, original run/attempt and artifact/payload digests.
`check` reobserves the accepted lock and emits `host_source: github_initial_pr_head`
with the receipt in existing provenance. HTML names and links the receipt.

The submission invariant stays scoped to one PR. This mode needs no H timestamp;
the timestamp mode still rejects equal times and retains the earliest H.
An opened(H), reopened, missing or unauthenticated receipt stays UNKNOWN.

## Trust

The collector saves only the original event and executes no candidate code.
Exactly one referenced worker binds reviewed source at B; the complete attempt's
job list must contain only its successful producer. Skipped jobs still count.
The artifact must bind that run and its provider digest. This proves worker origin,
not caller SHA; REST run heads describe the triggering PR, not workflow source.
The reader runs from an approved immutable Archkeel source checkout with its matching
pinned checker; a consumer does not vendor the reader into its accepted baseline.

## Rejected

Scheduler dates, current API head presented as an initial head, workflow names and
unverified source hashes cannot replace an authenticated original receipt.

## Limit and checks

A real forward check still needs an approved, CI-owned lock-only B immediately
after M, pinned runtime/configuration, and a retained authentic receipt. Missing
proof stays UNKNOWN; collector activation is an external owner decision.

`tests/test_ordering.py`, `tests/test_initial_pr_check.py`,
`tests/test_github_initial_pr.py`; `make demo-github` is explicitly simulated.
Live provider probes exercised a sole worker and a skipped worker plus fake uploader;
the latter retains two jobs and is rejected. They do not prove a live PR order.
