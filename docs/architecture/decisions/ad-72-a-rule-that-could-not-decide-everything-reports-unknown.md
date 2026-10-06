# AD-72 A rule that could not decide everything reports UNKNOWN

## What changes

Declared-rule verdicts account for undecided contract evidence, not just violations:

```
CHECK-TYPES-DECLARED   8 positions, 6 decided, 2 undecidable
declared_rules: PASS
```

| Observation | Verdict |
|---|---|
| a violation | FAIL |
| no violation, something the contract declares left undecided | **UNKNOWN** |
| no violation, everything the contract governs decided | PASS |

FAIL outranks UNKNOWN.

## Why

[AD-67](ad-67-an-undecidable-boundary-position-is-unknown-not-silence.md)'s explicit
uncertainty must reach the result. Exclude `external_type` from verdict changes:
its module has no declared component/public list to check. Keep its limit count.
The clean shop's 1/6 and self analyzer's 2/8 undecided positions were all external
`Path`/`datetime` types; counting them would make PASS unreachable.

## Rejected

Not every unknown record concerns contract evidence: dynamic-call and context-alias
limits are expected scan limits. `boundary_type_limit` and `api_surface_limit`
(AD-73) do change the verdict. Default new contract-limit kinds to UNKNOWN rather
than silently PASS. Do not hide external uncertainty as decided pass or change
exit codes in this decision.

## Limit

Unassigned repository modules also count as external types; `complete_assignment`
already reports their violation. Whether UNKNOWN should gate remains open.

## Check

Tests cover undecidable-to-UNKNOWN, external-only PASS, violation precedence and
unchanged report/check exits and diagnostics.
