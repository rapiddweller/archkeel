# AD-546 A baseline accepts an UNKNOWN by what it is and the core compares it in both directions

**Status.** Proposed. Part of #880. Slice B of the CE package for 5.0.0. It builds on AD-386 (the
baseline codec) and AD-432 (the core decides). It replaces `Unsupported::Baseline` for the scan
request.

**Reason.** Release 4.0.1 gated a repository with `validate --baseline FILE`. CE needs one command
and accepts exit 0 or 2. The core refused `--baseline`, so no user could gate a repository that
has an UNKNOWN. The owner decision (L-221): an accepted entry is bound to WHAT it is (kind,
subject, reason), never to a line, an evidence id, an analyzer digest or a source digest.

**Decision.**
1. Schema 1.4.0 adds the list `unknowns`: `{kind, subject, reason}` and a `count` that is written
   only above 1. The list is sorted by (kind, subject, reason) and unique. The codec reads 1.0.0 to
   1.4.0. A file without the list (1.0.0 to 1.3.0) accepts no UNKNOWN. One writer gives one byte
   string for one run.
2. The core builds the key of each entry from typed values (`gap_key.rs`, `Reason::stable`). It
   builds it from the typed `Reason` of each rule row and from the typed gap of the collector. A
   display text is never read. A line, a pointer into the contract, an evidence id and a sum of other
   entries are not in a key. A hygiene row has the key (`hygiene.<code>`, contract file, subject).
   Each open dependency decision and each pair gap is one entry. A number is the `count` of an
   entry only when no other entry counts the same thing (unresolved imports with no gap, undecided
   imports). The count of coverage gaps is not in any key: each gap has its own entry.
3. The compare is in both directions. A violation, a gap or a budget above the file is new and
   red. A violation, a gap or a budget below the file is stale and red: the file must be written
   again. Two sites with one key are counted: one acceptance never covers a second site.
4. Status never changes. A rule with an accepted UNKNOWN stays UNKNOWN. The exit code is 1 for any
   difference, 2 while the run has any UNKNOWN, and 0 only when nothing is unknown. An accepted
   violation is known debt (the freeze use of 4.0.1): it does not make the exit code 1.
5. A part that no key can name (a refused reply, a refused or unread contract, a section or the
   report that no slice ports) cannot be accepted. The state is `not_compared` and the exit code
   is 1. A refused scan with `--baseline` also exits 1. Exit 2 with a baseline means only that
   every UNKNOWN is accepted; CE treats exit 2 as green, so a refusal must not give it.
6. A baseline that is absent, outside the repository, malformed, repeated, not sorted, with an
   unknown field or with a count of 0 is `invalid` and exits 1 with the entry. CE treats exit 2 as
   green, so exit 2 for a damaged file would be a false green.
7. Budgets. `cycle_edges` (the internal edges of all cycles) and `private_crossings` (a symbol
   import that starts with `_` across two packages) are measured when each selected file was read
   and parsed. A budget that the run cannot measure, or that this core does not measure
   (`calls_unresolved`, `typing_positions`, `untyped_private_accesses`, `unknown_positions`, the
   name budgets), is the named gap `budget.unmeasured` and never 0. A file of an older schema
   holds the three numbers of another analyzer: the core names `baseline.budget_of_older_schema`
   and does not compare them. A hidden edge is not a number: it is a gap that is keyed, so a new
   one is red. The call-count budgets come with slice D.
8. The `gaps` list of the result is built in the core with the kind of each gap. The shell checks
   that it restates `unsupported.rules` and reads no text prefix.
9. Options: `validate --baseline PATH` and `validate --write-baseline PATH`. The path is below the
   root. The same path for both is refused. `--write-baseline` writes the frame bytes through the
   atomic writer of `--output`, and writes nothing for a run that cannot be accepted.

**Rejected.** An analyzer or source digest in an entry (it moves on each edit). The line in the
key. A compare that only counts entries. Exit 0 for an accepted UNKNOWN (the owner decision). A
text prefix in the shell. A budget that reads 0 when it is not measured.

**Limits.** The violation identity is the rule and the sorted source and target, with the role. For
`from m import name`, 4.0.1 names the target `m.name` and the core names `m`. Cycle edges and
private crossings equal 4.0.1 on CE (2 and 0) and on a planted pair. A non-empty 1.3.0 file of
4.0.1 with such a violation reads as one new and one stale entry (exit 1, never a false pass): write
it again once. The key of a TypeScript parser gap and a Dart file
gap drops a trailing position by the text, because those collectors write the position into the
reason. A pair gap is one entry for each pair: a rule with many pairs gives many entries.
The HTML report does not mark accepted entries yet.

**Tests.** `core/src/baseline_tests.rs` (each compare condition), `gap_key_tests.rs`,
`baseline_frame_tests.rs` (write, read, round trip, a blank line above each source line, damaged
files), `model/src/reason_key_tests.rs`, `contract/src/policy/baseline_unknowns_tests.rs`,
`tests/test_cli_baseline.py`.
