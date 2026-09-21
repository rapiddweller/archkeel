# AD-72 A rule that could not decide everything reports UNKNOWN

## What changes

`declared_rules` was derived from violations alone, so a report could say both of these at once:

```
CHECK-TYPES-DECLARED   8 positions, 6 decided, 2 undecidable
declared_rules: PASS
```

| Observation | Verdict |
|---|---|
| a violation | FAIL |
| no violation, a position undecidable for a checker limit | **UNKNOWN** |
| no violation, everything the contract governs decided | PASS |

A violation outranks an undecidable: a proven wrong is not an unknown.

## Why

AD-26's vocabulary is PASS, VIOLATION, UNKNOWN, and `RunResult.declared_rules` already allowed
all three. Reading "no violation" as PASS is the same mistake
[AD-67](ad-67-an-undecidable-boundary-position-is-unknown-not-silence.md) removed inside the
rule, left standing one level up.

Not every undecidable position is a gap, though, and the difference decides whether the field
is worth reading:

| Reason | Meaning | Flips the verdict |
|---|---|---|
| `external_type` | the type's module belongs to no declared component | no |
| every other kind | the checker could not read the code | yes |

`external_type` has no `public` list to be read against, so the question does not apply.
Counting it measured out like this:

| Sample | positions | undecided | reasons |
|---|---:|---:|---|
| clean shop demo | 6 | 1 | `external_type` |
| Archkeel itself | 8 | 2 | `external_type` |

Behind all three: `pathlib.Path` and `datetime.datetime`. So counting `external_type` would
make every repository whose facade takes a `Path` report UNKNOWN forever, PASS unreachable,
and the field worthless -- the mirror of the defect this fixes. The count stays visible in the
record's breakdown either way.

## Rejected

| Alternative | Why not |
|---|---|
| Any undecided position flips the verdict | Six existing tests, the clean demo among them, go yellow forever. Measured, not predicted. |
| Any `unknowns` record flips it | `dynamic_call_limit` and `context_alias_limit` fire on every run; PASS would be unreachable. |
| Treat `external_type` as a decided pass | Hides it. It is a limit, and the breakdown should keep saying so. |
| Name the kinds that DO flip it | A kind added later would default to silent PASS, which is this defect again. |
| Let UNKNOWN change the exit code | A separate decision. This reports; it does not gate. |

## Limit

A module inside the repository that no component claims also lands in `external_type`, and that
is a genuine gap -- but `complete_assignment` already reports it as a violation of its own, and
a violation outranks UNKNOWN, so the run still fails. Whether UNKNOWN should gate is open.

## Check

`test_undecided_boundary_position_with_no_violation_reports_unknown_not_pass` and
`test_undecided_positions_that_are_all_external_type_still_pass` pin both directions;
`test_a_proven_violation_outranks_an_undecidable_boundary_position` pins the precedence; two
more pin that `report` and `check` keep their exit code and diagnostics.
