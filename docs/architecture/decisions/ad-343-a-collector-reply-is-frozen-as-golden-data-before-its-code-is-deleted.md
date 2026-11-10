# AD-343 A collector reply is frozen as golden data before its code is deleted

**Decision.** Before a Python collector is deleted, its replies on the fixtures, the demos and
small corpus excerpts are recorded under `tests/golden/<language>/`. After the deletion, the
test compares the native collector with these replies. A golden reply changes only through a new
recording with a reason. This is the owner decision of epic #880 of 2026-11-09. TypeScript is
first (phase 4.5). Python and Dart use the same harness.

**Problem.** The Python collector is the only definition of the facts. Phase 4.5 deletes it. The
tests that use it as the oracle then have nothing to compare with.

1. **Canonical form.** A reply is compared without these fields: `protocol_version` (framing),
   `facts.adapter.code_digest` and `facts.adapter.version` (they name the producer, not the
   source), `facts.runtime` (the interpreter or binary), `facts.source.git_head` and
   `facts.source.dirty` (echo of the request). A path under the case root becomes `<root>`.
   The TypeScript reply has no run id and no timing. The canonical form fails when a key looks
   like one, so a new volatile field cannot enter a golden file.
2. **Storage.** `<case>.json.gz` holds the full canonical JSON when its gzip form is at most
   `FULL_REPLY_LIMIT` (64 KiB). A larger reply gets `<case>.digest.json`: the sha256 of the
   whole reply, of each section and of the rest, the section order, the features and counts per
   section and record kind. `RECORDINGS.md` has one line per recording: date, case, commit, reason.
3. **Recording.** `make golden-record LANGUAGE=<l> CASE=<case|all> REASON="<why>"` runs the
   current full Python collector. It refuses to run without `LANGUAGE`, `CASE` and `REASON`. It
   refuses a source that is not committed (`src` and the case folders), unless `ALLOW_DIRTY=1`.
   Then the log names the commit with `+dirty`.
4. **Compare.** The whole-reply digest and the section order must be equal. A duplicate section
   name is an error. A missing section fails, unless `tests/golden/<language>/allowances.json`
   names it for the phase in `ARCHKEEL_GOLDEN_PHASE`, with a reason. A phase variable alone
   grants nothing. Everything outside the allowed sections (files, evidence, coverage, ...) is
   still compared. The test warns with the skipped sections and the reason.
   `ARCHKEEL_GOLDEN_GATE=delete` is the deletion gate: it ignores every allowance. The variable
   `ARCHKEEL_GOLDEN_PRODUCER=native` switches the producer.
5. **Cases.** `cases.json` lists them. TypeScript: four fixtures, two excerpts of excalidraw
   (MIT, commit `701b901a`) and three synthetic cases: JSX with `paths`, bundler mode, and script
   gaps with `collection_gap` and `script_namespace_effect`. A test lists each section, record
   kind and feature that the collector can emit and fails when a golden case does not cover it.
   The collector does not fill `type_shapes`, `uncertain_reexports` and `candidate_evidence`.
   A test fails when it starts to, and checks that they stay empty.
6. **Python (added 2026-11-09, changed 2026-11-10).** A case is `<case>` (the host sequence),
   `<case>-providers` (the survey with provider sources) and `<case>-imports` (the survey of phase
   `imports`, stored in full: the oracle of the first native slice). The reply depends on the
   interpreter: `symbols`, `calls`, `evidence`, `inputs`, `provider_bindings`, `source` and
   `provider_sources` hold the standard library text, digests or version. They differ on 3.11 to
   3.14; the other sections are equal. They do not depend on the count of built-in modules: the
   goldens, recorded on macOS (101), are equal on Linux (102). `python/interpreter.json` names
   the parts and the interpreter of the recording (CPython 3.11.12). On that kind and version
   the whole reply is compared. CI, a phase and the deletion gate fail on another one. A local
   run compares the rest and warns. The cases: six fixtures, synthetic sources and two excerpts
   of fastapi (MIT, commit `ba47d6d7`) in `fixtures/golden-python`. `E-runtime` needs 3.12.

**Rejected.**
- **Keep the Python collector as an oracle.** It is the code that phase 4.5 deletes.
- **Store only hashes.** A change would show no field. Full replies show the first difference.
- **Run the corpus in CI.** It is large and untrusted. Only the small excerpts are in the repo.
- **The Studio UI as a case.** It is live source: each edit would need a new recording.
- **A reply of a demo variant for each overlay.** The four fixtures hold the constructs that the
  variants mutate. Add a variant when a gap shows.

**Limit.** The coverage test checks kinds, not every shape inside a kind. The golden replies hold the Python result, including its mistakes. A native fix of
such a mistake needs a new recording with a reason. The golden test does not check the facts
against the TypeScript compiler. The comparison of sections needs equal record identities.

**Checked by** `tests/test_collector_golden_replies.py`: each case equals its golden reply; the
canonical form drops the listed fields and the paths; a timing key fails; the size limit selects
the form; a changed record, an extra section, a swapped order and a duplicate section fail; a
subset fails without an allowance, passes with one and still compares the rest, and the gate
ignores the allowance; the recorder refuses an empty reason, a dirty source and a missing
variable; the kinds and features are covered (the collector writes the effect kind as a literal); Git keeps the sources in LF.
`test_collector_golden_python.py`: each Python kind site is known and covered; the pin skips a part only on another interpreter.
