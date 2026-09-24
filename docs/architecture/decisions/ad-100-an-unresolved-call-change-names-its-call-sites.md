# AD-100 An unresolved-call change names its call sites

## Decision

`call_rows` in `check/ratchets.py` reads every unresolved and partially resolved call from the
observation's existing `calls` records and evidence: `status`, `caller`, `expression`, `reason`,
owning `component` (`null` when unowned), `path` and `line`. It is not a second call analysis,
and the rows must add up to the coverage counts, or the run is not checked. Two outputs use it.

| Command | JSON field | Rows |
| --- | --- | --- |
| `report --only calls` (with `--component`, never `--rule`) | `filtered_calls` | every listed call |
| `check` | `unresolved_call_changes` | unresolved calls whose count differs from the accepted commit |
| `validate --against <ref>` with a `calls_unresolved` budget | `unresolved_call_changes` | the same, against the code at `<ref>` |

Both fields are opt-in and absent otherwise, so a default result keeps its bytes. A change row
has `change` (`added` or `removed`), `caller`, `expression`, `reason`, `component`, `path`,
`lines`, `before` and `after`. Its identity is the file, the calling scope and the call
expression, never the line, so code that only moves is no change. Identical expressions in one
caller share one identity: the row counts them, and `lines` names every line on the side holding
more. Only `unresolved` calls are compared, the status behind `calls_unresolved`.

The terminal names at most five change rows, below the run's failures and through the same print,
and nothing on a passing run. `--only calls` also draws its rows as one HTML table in place of
the violations table and the sections `--only violations` hides (AD-60).

## Why

Issue #131: on DATAMIMIC CE an agent saw `unresolved +1` during a refactoring and had to find
the call by hand. On the shop sample, `origin/main` printed only
`measurement budget exceeded in calls_unresolved: 7->8`, `measurement budget widened:
calls_unresolved (8 now, 7 before)` under `--against`, and `regression check failed in
calls_unresolved: 7->8` in `check`; `architecture.json` is string-table encoded and names no
component, so an agent could not list the calls either.

## Rejected

- **An occurrence index in the identity.** A new identical call above an old one shifts every
  index, so the row names the old line. A count names every candidate instead.
- **The line in the identity.** Every edit above a call would add one row and remove one.
- **The call list in the validation baseline**, so that plain `validate --baseline` can name a
  site. Archkeel's own baseline would grow from 242 bytes by 74 KB (427 identities), DATAMIMIC's
  by about 1,288 entries, and every renamed caller would churn it.
- **Every call row in the default `--json`.** D-self would add 1,157 rows to a 1.2 KB result.
- **Observing `--against`'s code on every run.** It doubles the cost for contracts that gate
  nothing on calls.

## Limit

A renamed caller or a call moved to another function is one removed and one added row. Of two
identical calls in one caller, the new one cannot be told apart. Plain `validate --baseline`
still reports the count; `--against <ref>` names the sites. Both `--against` scans read the
working tree's contract, so a removed row names today's component; a revision whose source
cannot be observed completely leaves the field absent. The check HTML page lists no sites.

## Check

`tests/test_unresolved_call_sites.py` covers an added, removed, moved and doubled call,
`validate --against` with and without the budget, an unscannable revision, the capped terminal
list, `report --only calls` with `--component`, `--rule` and the HTML table, and a default
result without either field. The `SCALARS:calls_unresolved` check row asserts
`shop/app/probe_unresolved.py:10`; `make demo` case A asserts the `--only calls` row
`handlers[key]` at `sample/work.py:9` (`tests/test_demo.py`).
