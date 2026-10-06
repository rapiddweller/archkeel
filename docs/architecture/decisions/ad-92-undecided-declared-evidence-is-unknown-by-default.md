# AD-92 Undecided declared evidence is UNKNOWN by default and measured

The aggregate verdict derivation is superseded by [AD-124](ad-124-rule-pass-requires-complete-scope-receipt.md).
The measurement below remains unchanged.

## Decision

`check/ratchets.py::unknown_positions` owns undecided-position counting:

| `unknowns` record | counts |
| --- | --- |
| id also in `coverage.failures` | 0: incomplete scan already exits 2 |
| `dynamic_call_limit`, `context_alias_limit`, `private_attribute_access_limit` | 0: standing disclaimers or separate scalar |
| `boundary_type_limit` | per-kind counts, excluding totals and `external_type` (AD-67) |
| any other kind | positive integer `data.undecided`, else 1 |

Originally `inspect_observation` used this count: violations FAIL, otherwise positive
counts UNKNOWN, otherwise PASS. Exit codes stayed unchanged.
The scalar is a ratchet and selectable baseline budget (AD-83, AD-89). `check`
fails rises; budgeted validation also fails unrecorded falls. Legacy payloads
without it read as 0. The self-contract selects it.

## Why

An allowlist of contract-limit kinds let new analyzer kinds silently leave PASS.
`check` caught new unknown records, but validation had no scalar budget. Naming
only exceptions closes that default while preserving existing Python verdicts.

## Rejected

Do not gate all UNKNOWN exits; budget changes are clearable. Counting only records
with `rule_ids` would omit declaration-level `api_surface_limit`.

## Limit

Without a positive count, a record contributes one regardless of covered positions.
Profiles supply finer counts. New standing exceptions must justify why they fire
independently of contract intent.

## Check

Unknown/verdict, ratchet and measurement-budget tests cover old behavior, novel
kinds, counts, exclusions, legacy payloads and round trips. Self tests and
`make self-validate` check the committed value.
