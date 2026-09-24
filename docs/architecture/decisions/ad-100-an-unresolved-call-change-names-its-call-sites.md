# AD-100 An unresolved-call change names its call sites

## Decision

`call_rows` in `check/ratchets.py` reads every unresolved and partially resolved call from the
observation's existing `calls` records and evidence: `status`, `caller`, `expression`, `reason`,
owning `component` (`null` when unowned), `path` and `line`. It is not a second call analysis,
and the rows must add up to the coverage counts. Two result fields use it; both are `null` when
unused, like every optional result field (AD-60).

| Command | JSON field | Rows |
| --- | --- | --- |
| `report --only calls` (with `--component`; `--rule` is refused) | `filtered_calls` | every listed call |
| `check` | `unresolved_call_changes` | unresolved calls whose count differs from the accepted commit |
| failing `validate --against <ref>` whose `calls_unresolved` moved | `unresolved_call_changes` | the same, against the code at `<ref>` |

A change row has `change` (`added` or `removed`), `caller`, `expression`, `reason`, `component`,
`path`, `lines`, `before` and `after`. Its identity is the file, the calling scope and the call
expression, never the line, so code that only moves is no change. Identical expressions in one
caller share one identity: the row counts them, and `lines` names every line on the side holding
more. Only `unresolved` calls are compared, the status behind `calls_unresolved`.

`validate --against` scans `<ref>`'s `git archive` snapshot under `<ref>`'s own contract, through
the `materialize_declarations` `check` uses. Rows whose file the archive never writes
(untracked git-ignored, or `export-ignore`) are dropped. The second scan runs only when the run
fails and the observed `calls_unresolved` differs from an accepted value. Records that do not add
up, or a revision that cannot be scanned, leave the field `null` and the verdict as it was: the
sites explain a finding, they never decide one. A plain `validate --baseline` rise says that
`--against <ref>` names the sites.

The terminal lists at most five change rows below the failures, through the same print.
`--only calls` draws its rows as one HTML table in place of the violations table and hides the
sections `--only violations` hides.

## Why

Issue #131: on DATAMIMIC CE an agent saw `unresolved +1` during a refactoring and had to find
the call by hand. On the shop sample `origin/main` printed only the counts: `measurement budget
exceeded in calls_unresolved: 7->8`, `measurement budget widened: calls_unresolved (8 now, 7
before)` under `--against`, and `regression check failed in calls_unresolved: 7->8` in `check`.
`architecture.json` is string-table encoded and names no component.

## Rejected

- **An occurrence index in the identity.** A new identical call above an old one shifts every
  index, so the row names the old line. A count names every candidate instead.
- **The line in the identity.** Every edit above a call would add one row and remove one.
- **The call list in the validation baseline**, for plain `validate --baseline`: Archkeel's
  242-byte baseline would grow by 74 KB, and every renamed caller would churn it.
- **Every call row in the default `--json`.** D-self would add 1,157 rows to a 1.2 KB result.
- **A second scan on every `--against` run.** It doubled Archkeel's own run (7.5 s to 15 s).

## Limit

A renamed caller, a call moved to another function, and a renamed or moved file are removed and
added rows, a file's rows all at once. Of two identical calls in one caller, the new one cannot
be told apart. A file the archive leaves out is not compared at all. The check HTML page lists
no sites.

## Check

`tests/test_unresolved_call_sites.py`: added, removed, moved and doubled calls; `--against` under
`<ref>`'s own contract, with archive-excluded files, on a passing run (one scan), with records
that do not add up (also for `check`) and an unscannable revision; the capped terminal list;
`--only calls` with `--component`, `--rule` and HTML; null fields by default. The
`SCALARS:calls_unresolved` check row asserts `shop/app/probe_unresolved.py:10`; `make demo` case A
asserts `handlers[key]` at `sample/work.py:9` (`tests/test_demo.py`).
