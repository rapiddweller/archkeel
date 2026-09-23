# AD-92 Undecided declared evidence is UNKNOWN by default and measured

## Decision

One function, `unknown_positions` in `src/archkeel/check/ratchets.py`, counts what the scan left
undecided. The same count decides `declared_rules` and fills the `unknown_positions` scalar, so
the verdict and the measurement cannot disagree.

| `unknowns` record | counts |
| --- | --- |
| id also in `coverage.failures` | 0: the scan is already incomplete, exit 2 |
| `dynamic_call_limit`, `context_alias_limit`, `private_attribute_access_limit` | 0: standing disclaimers, or a scalar of their own |
| `boundary_type_limit` | its per-kind counts, without the totals and without `external_type` (AD-67) |
| any other kind | `data.undecided` when it is a non-negative integer, else 1 |

`inspect_observation` reads: a violation is `FAIL`; else a count above 0 is `UNKNOWN`; else
`PASS`. Exit codes do not change.

`unknown_positions` is a regression scalar and a selectable measurement budget, the path
`untyped_private_accesses` took (AD-83, AD-89). `check` fails on a rise, and `validate
--baseline` with the budget declared fails on a rise and on an unrecorded fall. Older measurement
payloads without the key read as 0. Archkeel selects the budget in its own contract.

## Why

Before, `declared_rules` became UNKNOWN only for `boundary_type_limit` and `api_surface_limit`.
Any other kind a new analyzer profile emits left the verdict at PASS: no violation read as
probably fine, the defect AD-67 fixed for one rule, left open at the record-kind level.
`check` already failed on a new `unknowns` record, but `validate --baseline` had no scalar a
budget could pin, so a new UNKNOWN kept exit 0.

For every observation the Python analyzer produces today the verdict is unchanged:
`api_surface_limit` counts 1 per record, `boundary_type_limit` counts exactly the positions that
flipped the verdict before, and `git_metadata_failure`, parse failures and
`rule-without-subjects` are coverage failures.

## Rejected

- **An allow-list of counted kinds.** That is the defect: a new kind defaults to PASS. The code
  names only the exceptions.
- **Gating the exit code on UNKNOWN.** A gate nobody can clear gets deleted (AD-67). The budget
  gates a rise instead, which a team can hold at its current value.
- **Counting records by `rule_ids`.** `api_surface_limit` names a declaration, not a rule, and
  would fall out of the count.

## Limit

A record without a usable `undecided` count counts once, however many positions it covers. A
profile that wants a finer count writes `data.undecided`. A kind added to the standing
disclaimers must argue that it fires regardless of the contract.

## Check

`tests/test_boundary_type_unknown_verdict.py` keeps AD-67's verdicts unchanged.
`tests/test_unknown_positions.py` covers a novel kind, the `undecided` count, the disclaimers and
coverage failures; `tests/test_ratchets.py` the legacy payloads and the codec round trip;
`tests/test_measurement_budgets.py` a rise under `validate --baseline`. `tests/test_self.py` and
`make self-validate` check Archkeel's own value in `architecture-baseline.json`.
