# AD-100 An unresolved-call change names its call sites

## Decision

`check/ratchets.py::call_rows` projects unresolved/partially resolved calls and their
status, caller, expression, reason, owner, path and line from existing records.
Rows must match coverage totals. Optional result fields are null when unused.
Dart has no call measurement: `--only calls` exits 2, unsupported by profile (AD-97).

| Command | JSON field | Rows |
| --- | --- | --- |
| `report --only calls` with optional component; rule refused | `filtered_calls` | all listed calls |
| `check` | `unresolved_call_changes` | unresolved counts differing from accepted commit |
| failing `validate --against` with moved call budget | `unresolved_call_changes` | same comparison with ref code |

Change identity is file, caller and expression, excluding lines. Rows retain added/
removed kind, reason, component, path, lines and before/after counts. Identical calls
share identity; lines name all candidates on the side with more occurrences.
Only unresolved status participates in `calls_unresolved` comparison.

Failing budget comparison uses `observe_revision` on the ref's archive and contract.
Compare removed rows and files present in the snapshot. For absent files, drop
added rows outside Git's tracked/unignored scan listing, or tracked at ref but
omitted by its `export-ignore`, including folder exclusions.
Unscannable revisions, unreadable listings or mismatched totals leave rows null;
explanations never change verdicts. `unresolved_call_note` explains missing/dropped/
unchanged sites, or points plain validation to `--against`. Terminal output caps
rows at five. Call-only HTML uses a table and the violation-only section hiding.

## Why

Issue #131's DATAMIMIC CE refactoring showed only `unresolved +1`; agents had to
find the site manually. Existing report encoding offered no direct component rows.

## Rejected

Line or occurrence-index identity churns after insertions. Baseline call lists
would expand 242 bytes by 74 KB; default results would add 1,157 rows to 1.2 KB.
Scanning every against run measured 7.5→15 seconds, so scan only failing moved budgets.

## Limit

Caller/file moves appear removed/added. Identical occurrences remain indistinguishable.
Ignored, submodule and ref-export-ignored new files name no site. Roots below Git
top level and non-UTF-8 names leave null. Check HTML shows no sites.

## Check

`tests/test_unresolved_call_sites.py` covers identities, counts, ref policy, Git
exclusions/errors, notes, terminal limits and call filters. The scalar demo pins
`shop/app/probe_unresolved.py:10`; demo case A pins `handlers[key]` at `sample/work.py:9`.
