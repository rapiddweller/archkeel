# Pledge reference

Exact rules behind the [README](../README.md). Code is the source of truth; this file explains it.

## Configuration

[schema/pledge.schema.json](../schema/pledge.schema.json) defines `pledge.toml`.
Only `[scan]` with required `roots`, `namespace` and `contract` is accepted.
Paths are relative to the repository root. Scan roots are directories, not globs.
The architecture schemas live once under `schema/`; builds include them as package data.

## Producer and runtime

The external Python producer is invoked through `--producer-root`; its scan algorithms are unchanged.
`PRODUCER_ROOT` in the Makefile defaults to the adjacent EE checkout.
D-self verifies the producer commit recorded in `fixtures/D-self/provenance.json`.

The producer records `python_version` separately from its analyzer digest. Missing or incompatible
`pyproject.toml` runtime requirements produce `runtime_mismatch`; AST parse errors only
use `parse_error` after a compatible runtime check. Git snapshots carry their own project metadata.
Delta comparison requires the same known full Python version; otherwise `incomparable_runtime`
returns exit 2. Historical observations without runtime provenance remain readable, not comparable.

The checker hashes its own installed Python package separately from the producer digest.
Delta schema 1.2.0 and expectation schema 1.2.0 bind `checker_digest`;
the evaluator verifies the running package.
Underscore-private imports belong to the Python decoded-IR profile in `check/python_profile.py`.

## Git predicate

`check` reads `architecture-accepted.json` from B and reobserves its accepted commit M.
B must be a lock-only child of M and the fetched accepted branch tip. E must be a
child of B changing only the expectation file, an ancestor of H, and present on the
fetched candidate branch. H must preserve the lock, configuration, contract and expectation.
The expectation binds B and the lock digest. The lock binds configuration, checker
and accepted observation digests, raw measurements and an opaque `approval_ref`.

## Host records

The GitLab adapter reads MR diff versions with `glab` using `CI_PROJECT_ID`,
`CI_MERGE_REQUEST_IID` and exact `CI_COMMIT_SHA == H`. It maps `head_commit_sha`
and host `created_at` into `(sha, event, timestamp)` records. Both E and H need
records; missing evidence is `UNKNOWN`, exit 2. E publication must precede the
first H submission. Commit author dates are not evidence.

`--host-records /trusted/records.json` replays records with exactly `sha`, `event`
(`expectation_published` or `candidate_submitted`) and timezone-aware `timestamp`.
CI owns record authenticity, fetched remote refs, branch protection and lock signing;
the core checks SHA binding and order. A local replay does not prove host authenticity.
The A/B/C fixtures use real local Git repositories and simulated host records and CI locks.

## Results

JSON results separate `observation_complete`, `declared_rules` and
`expectation_fulfilled`. `report` uses `n/a` for expectations. Exit codes: 0 for
complete report/successful check, 1 for a rejected check, 2 for unverifiable inputs.
Every exit 2 includes a Diagnostic with `kind`, `subject`, `unknown_claim` and a
one-line `remedy`. Partial producer observations retain their typed coverage and
are persisted by `report`. Invalid locks are never replaced with empty state.
IR JSON decoding and encoding belongs to `ir/codec.py`; core models are frozen dataclasses.

## Ratchets

Ratchets add these scalars to the existing record counts and fingerprint checks:

| Guardrail | Scalar in the Python decoded-IR profile |
| --- | --- |
| No new violations | Violation records |
| No new cycles | Internal SCC edges, summed across observed levels |
| No new private crossings | Private cross-package import records |
| No new typing signals | Missing boundary annotation positions; other signals count once |
| No new unknowns | Unresolved calls; unknown record counts and fingerprints remain checked |
| Coverage must pass | Scan failure records; any incomplete scan is unverifiable |

The delta stores raw measurements for the accepted observation and candidate.
Schema, scope, analyzer and contract must match.

`calls_total` is the producer's `calls_analyzed`. With `U = calls_unresolved` and `T = calls_total`,
checks require `U_candidate <= U_accepted` and, when both totals exceed zero,
`U_candidate * T_accepted <= U_accepted * T_candidate`. No rounded percentages are used.
Zero total means `resolution: n/a`; the absolute ratchet still applies.
Missing or inconsistent measurements produce `UNKNOWN`; regressions return failures.

## Fixtures

The original Phase-4 runs under `fixtures/A` and `fixtures/B` are unchanged archives,
not test or distribution inputs. `make fixtures` reproduces A, B and C from
`fixtures/A-dispatch`, `fixtures/B-posthoc` and `fixtures/C-valid`.

The current producer supports negative dependency rules. D-self also checks that
all observed modules have declared components, that new IR modules receive explicit
producer prohibitions, and that producer imports stay within the declared IR API.

## Dependencies

Runtime: `packaging` parses PEP 440 `requires-python` ranges; stdlib has no equivalent.
Build: Hatchling packages the root schemas. Development: Ruff (lint/format), MyPy (strict),
Pytest. The runtime fixture in `make check` requires Python 3.11 and 3.12.
