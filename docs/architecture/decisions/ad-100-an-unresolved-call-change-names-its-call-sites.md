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

`validate --against` observes `<ref>`'s `git archive` snapshot under `<ref>`'s own contract, through
`observe_revision`, the helper `check` uses; only a failing run whose `calls_unresolved` moved from
an accepted value pays for it. The working tree is read from disk, so a removed row is always real.
An added row is dropped when its file is outside `git ls-files --cached --others
--exclude-standard` (ignored, or inside a submodule), or tracked at `<ref>` (`git ls-tree`) but
absent from the snapshot: what `<ref>`'s own `export-ignore` left out, folders included.
Unscannable revisions and records that do not add up leave the field `null`, and the verdict as
it was: the sites explain a finding, they never decide one. `unresolved_call_note` then says why
no site is named, as it does for an empty list. Without `--against` the rise points at it.

The terminal lists at most five change rows, or the note, below the failures.
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
be told apart. A rise carried by a git-ignored, submodule or `<ref>`-export-ignored file names no
site. `--root` below the Git top level leaves the field `null`. The check HTML lists no sites.

## Check

`tests/test_unresolved_call_sites.py`: added, removed, moved and doubled calls; `--against` under
`<ref>`'s contract, with ignored, submodule, folder and revision-attribute cases, a passing run,
unaddable records (also `check`), an unscannable revision, the notes; the capped terminal list;
`--only calls` with `--component`, `--rule` and HTML; null fields by default. The
`SCALARS:calls_unresolved` check row asserts `shop/app/probe_unresolved.py:10`; `make demo` case A
asserts `handlers[key]` at `sample/work.py:9` (`tests/test_demo.py`).
