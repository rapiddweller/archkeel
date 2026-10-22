# AD-259 One plain wire, one validation

**Decision.** The native Python collector speaks collection protocol 8.0.0, called
"plain". Plain keeps the V7 semantics: feature gating (AD-257) and dropping the
records of families that an older collector cannot name. Its facts are the ordinary
fact objects, without the V6/V7 key and value pools of AD-253.

The response stream is zlib-compressed (level 1). The 64 MiB response cap applies to
the compressed bytes. The decompressed size is bounded at 16 times the cap.

A V8 encoder does not validate its own output. `decode_response` in the main process
is the single trust boundary. Encoders for V1–V7 keep their current behaviour, and
third-party collectors answer with the version they implement.

The levers are delivered one per PR, in this order:
1. the plain wire;
2. a single validation;
3. a profile of the main process, followed by its own measured decision on the
   observation, which is re-serialized four times, and on the survey pass that
   parses every source a second time;
4. per-module visitors in forked workers after the global passes. The worker count
   comes from `ARCHKEEL_COLLECT_JOBS`. Windows and a count of 1 stay sequential.

**Reason.** AD-253 introduced the columnar form only because V5 exceeded the stdout
cap. The pools cost the main process 17.5 s to expand, against 2.0 s to decode plain
JSON, and the collector 9 s to build. zlib keeps the cap meaningful at 0.4 s instead.
The collector's self-validation (7.2 s) repeats checks that `decode_response`
performs anyway.

ArchKeel's own report takes about 70 s locally and 191 s on CI, against the 120 s
budget of `make report-timing`. That budget blocks Full verification and Pages.
Estimated effect, to be measured per PR: lever 1 −13 s, lever 2 −3.5 s, lever 4
−5 s. Lever 3 decides the rest.

**Check.**
- The own report's `architecture.json` stays byte-identical before and after each
  lever (`cmp`), and so do the fixture outputs. The one exception is
  `analyzer.code_digest`, which hashes the analyzer's own source and changes with it.
- V1–V7 protocol fixtures still decode unchanged.
- Each lever has a 3-run median of `make report-timing` before and after, compared
  against ±0.7 s of noise.
- A V8 response with invalid facts is rejected at `ProcessCollector.collect_response`
  as `PROTOCOL_ERROR`.
- `make collector-safety` proves the sequential path on Windows.
- The own report meets the 120 s CI budget.
