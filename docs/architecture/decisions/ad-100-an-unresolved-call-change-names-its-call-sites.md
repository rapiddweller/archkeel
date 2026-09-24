# AD-100 An unresolved-call change names its call sites

## Decision

Where Archkeel compares the calls of two revisions, the JSON result carries
`unresolved_call_changes`: one row per unresolved call whose count differs, with `change`
(`added` or `removed`), `caller`, `expression`, `reason`, `component`, `path`, `lines`, `before`
and `after`. Otherwise the field is `null`.

| Command | Compares | `unresolved_call_changes` |
| --- | --- | --- |
| `check` | the accepted commit and the candidate it already observes | always |
| `validate --against <ref>` with a `calls_unresolved` budget | the code at `<ref>` and the working tree | always |
| `report`, other `validate` runs | nothing | `null` |

A row's identity is the module, the calling scope and the call expression, never the line. Code
that only moves is no change. Identical expressions in one caller share one identity: the row
counts them, and `lines` names every line on the side holding more. Only `unresolved` calls count,
the status behind `calls_unresolved`; partially resolved calls feed no regression check.

`unresolved_call_changes` in `check/ratchets.py` reads the observation's existing `calls` records
and their evidence; it is not a second call analysis. The rows must add up to `calls_unresolved`,
or the run is not checked. A passing run's terminal stays as it was; a rejected one adds a heading
and at most five rows, then the number left for the JSON.

## Why

Issue #131: on DATAMIMIC CE an agent saw `unresolved +1` during a refactoring and had to find
the call by hand. On the shop sample, `origin/main` printed only
`measurement budget exceeded in calls_unresolved: 7->8`, `measurement budget widened:
calls_unresolved (8 now, 7 before)` under `--against`, and `regression check failed in
calls_unresolved: 7->8` in `check`.

## Rejected

- **An occurrence index in the identity.** A new identical call above an old one shifts every
  index, so the row names the old line. A count names every candidate instead.
- **The line in the identity.** Every edit above a call would add one row and remove one.
- **The call list in the validation baseline**, so that plain `validate --baseline` can name a
  site. Archkeel's own baseline would grow from 242 bytes by 74 KB (427 identities), DATAMIMIC's
  by about 1,288 entries, and every renamed caller would churn it.
- **Every unresolved and partially resolved call in the default `--json`.** D-self would add
  1,157 rows to a 1.2 KB result. `architecture.json` already holds each call with its caller,
  expression, reason, status and evidence line.
- **Observing `--against`'s code on every run.** It doubles the cost for contracts that gate
  nothing on calls.

## Limit

A renamed caller or a call moved to another function is one removed and one added row. Of two
identical calls in one caller, the new one cannot be told apart. Plain `validate --baseline`
still reports the count; `--against <ref>` names the sites. Both `--against` scans read the
working tree's contract, so a removed row names today's component; a revision whose source
cannot be observed completely leaves the field `null`. The check HTML page does not list sites.

## Check

`tests/test_unresolved_call_sites.py` covers an added and a removed call, a moved call, two
identical calls, `validate --against` with and without the budget, a revision that cannot be
scanned and the capped terminal list.
The `SCALARS:calls_unresolved` check row in `tests/test_architecture_demo.py` asserts
`shop/app/probe_unresolved.py:10`, and every other check row asserts no change.
