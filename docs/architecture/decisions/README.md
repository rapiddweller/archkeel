# Decision archive

Internal reasons and proof references. Later records can amend earlier ones.
For current behavior, use the [contract of `native/`](../../../native/architecture-contract.json), source and tests.
Records before AD-432 can link to source and tests of the Python engine. AD-432 deleted these files, so
such a link has no target on `main`. The files are in the Git history before that change (commit `c838a00cb`).

## The index is generated

A record is the file `ad-<number>-<words>.md` in this folder. The list of the records is not committed, because
every pull request that adds a record edited the same lines and conflicted with the next one (AD-752).

- `python tools/decision_index.py` prints the list: number, title (the first heading) and link, newest first.
- `python tools/decision_index.py --write PATH` writes it; `make decision-index` writes `test-artifacts/decision-index.md`.
- `python tools/decision_index.py --check` fails on a record that no number or heading identifies and on a number that
  two records share. The tests of CI run the same check.
- [INDEX.md](INDEX.md) keeps the hand-written list as it was on 2026-11-17.

To add a record, add one file with the next free number from the board. Do not edit another file.
