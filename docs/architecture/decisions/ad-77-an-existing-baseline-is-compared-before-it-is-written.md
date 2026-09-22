# AD-77 An existing baseline is compared before it is written

## Decision

`validate --baseline <path> --write-baseline` has two cases:

- A missing path is an initial baseline. Write the observed fingerprints.
- An existing path is first compared with the observation. Resolved-only drift may be written.
  New or increased fingerprints fail with exit 1 and produce no baseline artifact.
- `--accept-new` is required to write new or increased fingerprints deliberately.

The result carries deterministic counts of changed fingerprints as `baseline_new` and
`baseline_resolved`. Each fingerprint contributes one regardless of its occurrence-count delta.
Exit 2 diagnostics always produce no baseline artifact. `validate --baseline` without
`--write-baseline` keeps the existing comparison behavior.

## Why

`--write-baseline` used to skip the comparison and overwrite an existing budget. A typo in a
write command could therefore approve new debt. The baseline already has the comparison logic;
the writer now uses that result before producing bytes.

## Rejected

| Alternative | Why not |
|---|---|
| Always overwrite | Turns an accidental command into approval. |
| Add a second baseline format | The existing fingerprint and count format is enough. |
| Accept new findings implicitly | New debt needs an explicit reviewer-visible decision. |

## Check

`tests/test_baseline.py` covers initial creation, resolved-only updates, refused new fingerprints,
explicit `accept_new`, deterministic counts and exit-2 write refusal. The CLI test covers the
same refusal and JSON counts. The validation demo catalog has a `baseline.accept_new` row.
