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
   whole reply, of each section and of the rest, with counts per section and record kind.
   `RECORDINGS.md` has one line per recording: date, case, commit, reason.
3. **Recording.** `make golden-record LANGUAGE=<l> CASE=<case|all> REASON="<why>"` runs the
   current full Python collector. It refuses to run without `REASON`.
4. **Test.** `tests/test_collector_golden_replies.py` runs one producer on each case. The
   variable `ARCHKEEL_GOLDEN_PRODUCER=native` switches it to the native binary. When the producer
   claims fewer sections than the golden reply, the test compares only the claimed sections. It
   lists the sections that it did not compare in a warning. It never passes on an empty compare.
5. **Cases.** `cases.json` lists them. TypeScript: four fixtures (`H-typescript`,
   `H-uml-typescript`, `F-typescript-story`, `L-nest-realworld`) and two excerpts of excalidraw
   (MIT, commit `701b901a`): `packages/math` and `packages/laser-pointer`, with the licence.

**Rejected.**
- **Keep the Python collector as an oracle.** It is the code that phase 4.5 deletes.
- **Store only hashes.** A change would show no field. Full replies show the first difference.
- **Run the corpus in CI.** It is large and untrusted. Only the small excerpts are in the repo.
- **The Studio UI as a case.** It is live source: each edit would need a new recording.
- **A reply of a demo variant for each overlay.** The four fixtures hold the constructs that the
  variants mutate. Add a variant when a gap shows.

**Limit.** The golden replies hold the Python result, including its mistakes. A native fix of
such a mistake needs a new recording with a reason. The golden test does not check the facts
against the TypeScript compiler. The comparison of sections needs equal record identities.

**Checked by** `tests/test_collector_golden_replies.py`: each case equals its golden reply; the
canonical form drops the listed fields and the paths; a timing key fails; the size limit selects
the form; a changed record fails in both forms; a producer with fewer sections is compared on its
sections and names the rest; the recorder refuses an empty reason; the native producer reads a
compressed reply.
