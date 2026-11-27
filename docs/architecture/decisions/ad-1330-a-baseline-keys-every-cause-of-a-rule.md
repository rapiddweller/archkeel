# AD-1330: A baseline keys every cause of a rule

Status: accepted. Amends AD-546. Closes #2184 for the next write of a baseline.

## Why

A consumer compared a baseline of build `4.0.2.dev952` with build `dev1021` on the same source and contract: the
verdicts were equal (176 / 100 / 0), and `validate --baseline` reported 7,443 new and 1 gone entries.

Measured with the cores of the two commits (585b2e195 and main) on the same tree, never on two trees:

- A rule can have several causes. The row shows the first one, in the fixed order of `scope_order.rs`. The baseline keyed
  that first cause only. When a cause is resolved (here: an unread import of an `interface_boundary` rule), the row shows
  the next cause, and the keys of that cause are new entries although nothing was added. A plant shows it: the old
  baseline holds `interface_gap`; after the import is resolved the run has `gap_effect` and `incomplete_scope` as new.
  On ArchKeel's own `native/` the same flip gives 152 `pair_gap` entries on one side and one `interface_gap` on the other.
  This matches "7,443 new and 1 gone".
- A collector gap is keyed by the text of its reason (kind, subject, reason). A reworded text with the same kind, subject
  and count is one new and one gone entry. An earlier draft of this change paired such entries by kind and subject; the
  verification run showed that it took a real swap for no drift (`import_module` replaced by `reload` in one module;
  one orphan file of a Rust crate replaced by another, whose gap has an empty subject). It was removed.
- `validate` and `report` give the same `collection_gaps` and the same `gaps` on the DATAMIMIC EE copy (159 and 1633,
  equal digests, three runs, also `--text --all`). One function (`frame_parts::collection_gaps`) makes the list.
  A plant test pins it. The consumer's difference is not reproduced; the issue asks for the command sequence.

## Decision

1. `rule_causes` in `native/model/src/scope_order.rs` lists every source that holds a rule, in the same order. The
   first is the reason of the row (`Scope::complete`); the others are the causes beyond it.
2. The baseline keys all of them (`gap_key::of_run`). The key of a rule no longer moves when its first cause is
   resolved: the next cause was in the file already.
3. A run writes schema 1.5.0, which names every cause. A file of 1.4.0 names the first cause only, so the compare
   leaves the causes beyond the first out of the run for such a file: a file that an earlier build wrote stays current
   on the same source, and accepts no new finding. The first cause is still compared exactly.
4. A collector gap is matched by its exact key. The baseline file carries no typed code for a gap, so a reworded entry
   cannot be shown to be the same site; it stays one new and one gone entry (the honest old behaviour).
5. `validate` and `report` keep one maker of the gap list; a plant test compares both.

## Re-key of an existing file

None can be mechanical for the flip itself: a file of 1.4.0 does not hold the causes beyond the first, so a run whose
first cause changed shows the next cause as new, and no code can tell that from a new cause. Write the file once with
`validate --write-baseline` after you review the diff. From schema 1.5.0 on, a resolved first cause is `gone` and never `new`.

## Counter-examples tried

A swap of one dynamic import for another in one module is drift with one new entry (plant). An orphan file of a Rust
crate replaced by another is drift with one new entry (plant). A 1.5.0 file without a cause that the run has: new. A 1.4.0
file compares its first cause exactly. Mutations: without `rule_causes` two plant tests fail; without the 1.4.0 rule one fails.

## Not done yet

- A typed code for each collector gap (the gap kind and the typed site, for example the call form and the file of an
  orphan file) would let a reworded text keep its entry. The file would have to carry the code. Until then a reword of
  a collector text shows as one new and one gone entry.
