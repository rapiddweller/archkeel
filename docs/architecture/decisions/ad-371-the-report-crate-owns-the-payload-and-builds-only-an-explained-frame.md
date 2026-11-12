# AD-371 The report crate owns the payload and builds only an explained frame

**Status.** Accepted. Epic #880, WP6 slice 0d (AD-359 point 1, AD-361 point 1, AD-363 point 4).

**Decision.**
1. `native/report` (`archkeel-report`) owns the report v2 payload in Rust: the typed head and
   tables, the code lists, the canonical bytes, the status rule and the check. It uses `model`
   only. It reads no file and decides no verdict. The core does not call it yet (unwired).
2. A `Report` exists only after the check. `build(Outcome, Records)` gives `Report<Decided>`;
   `Report::read(bytes)` gives `Report<Recorded>`. The fields are private, and a recorded report
   never becomes a decided one (`compile_fail` doctests in `report.rs`).
3. The builder takes the run status from `status_of` over the rows; `RunOutcome` has no status.
   Only for a PASS does it call `pass`, which must give a PASS `Decision` of the model (AD-363),
   else `BuildError::PassWithoutProof`. The observation and each rule verdict come from a
   `Decision`. The rule reason follows the verdict (PASS `evaluated`, FAIL `violations`, a
   declaration `declaration`); only UNKNOWN takes a `WhyUnknown`. Only `Report<Decided>` encodes.
4. `status_of` is the status rule of AD-361 point 4 over the rows; `unexplained` is point 5.
   The builder and the check call the same two functions. A frame whose stated status differs
   from the rule is `BuildError::Invalid`; a status without its explaining row is
   `BuildError::Unexplained`. No bytes are written for either.
5. The builder copies the Decision. It derives only what follows from the rows: the string
   table, the columns, the counts, the gap list, the violation count of each rule, and the
   unknowns rows of the diagnostics and of a missing Target.
6. A table that no slice produces is `Produced::NotProduced(Unsupported)`. Only the graph
   (`edges`, `via`, `crossings`) has a state in the schema for that: the empty columns and
   `imports` and `reexports` in `run.not_carried`. Every other table that the schema requires is
   `BuildError::NotProduced` with its slice, never an empty table.
7. The check has every rule of the Python checker of #1040 and adds: a code beyond the lists of
   this crate (never read as clean), the row order of each table (a repeated row in a table with
   a unique key), the flags, the permission of each component edge and package edge, a PASS rule
   without receipt, a verdict with a reason it cannot have, a FAIL rule without a violation row,
   a budget other than 8 MB, a `run` row with a Target, and the counts that follow from the rows.
   A sum of payload numbers that overflows is a named count, never an abort. Bytes above 8 MB are
   refused before the parse; other bytes must be canonical.
8. Seam: `RunOutcome` and `Records` (`input.rs`) are the inputs that the eval crate and the model
   slices fill. The core answers `Unsupported::Report` until a wiring slice calls `build`.

**Reason.** The payload is the frame of the core (AD-361). If the frame type and its check are
one crate, no producer can write a status that its rows do not explain.

**Rejected.**
- An empty table for a part that is not ported: it reads as "nothing found" (false PASS risk).
- A bare `Verdict` in the rule rows: another crate could write a PASS (AD-363 point 4).
- A JSON schema validator crate in Rust: a new dependency for a check that the Python test does.
- Deciding the status in the builder: a second evaluator (AD-361, rejected item c).

**Limit.**
- A PASS status or a PASS observation needs `imports`, `reexports` and `variants`: when
  `run.not_carried` names one, the frame is refused (`Unexplained::PassWithoutPart`, also in
  `checker.py`). The other relations are display parts that every 2.0 payload leaves out.
- Slice S4 makes the scope proof ([AD-378](ad-378-a-rule-passes-only-with-the-scope-proof-of-its-own-model.md)); the core does not call `build` yet.
- The schema says "level, then depth, then key" for nodes; the Python producer gives every
  module depth 0, so modules sort by key. The check follows the producer.
- The summary counts have no "not produced" state: without the graph the edge counts are 0, and
  only `run.not_carried` says that imports are not carried.
- The check does not compare the target of a module edge (the owner chains are not in the
  payload), the order of the violation rows (record ids are not in it), and `unowned_modules`.

**Tests.** `native/report/src/corpus_tests.rs` (18 oracle payloads: byte-equal round trip, check,
status rule), `fault_tests.rs` (planted payload faults), `build_tests.rs` (the frames of 4
payloads byte-equal to the Python producer, the named build errors), `codec_tests.rs`,
`schema_tests.rs`, `status_tests.rs`, `review_tests.rs`; `tests/test_native_report.py`,
`tests/test_report_checker.py` (each payload and frame against the schema).
