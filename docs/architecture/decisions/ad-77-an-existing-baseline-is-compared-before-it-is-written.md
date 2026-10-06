# AD-77 An existing baseline is compared before it is written

## Decision

`validate --baseline <path> --write-baseline` writes initial or resolved-only debt.
New/increased fingerprints in an existing file exit 1 without an artifact unless
`--accept-new` explicitly approves them. Exit 2 never writes a baseline.
Validation without writing retains its comparison behavior.

`baseline_new` and `baseline_resolved` count changed fingerprints once each,
regardless of occurrence-count differences.

## Why

Writing had bypassed comparison and could accidentally overwrite the debt budget.
Reuse baseline comparison before producing bytes.

## Rejected

Implicit acceptance hides approval; a second baseline format adds no needed behavior.

## Check

Baseline and CLI tests cover creation, resolution, refused additions, explicit
acceptance, deterministic counts and exit-2 refusal. The demo catalog includes
`baseline.accept_new`.
