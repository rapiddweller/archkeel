# Report review pilot

Status: prepared; no human results. [#236](https://github.com/rapiddweller/archkeel/issues/236)
tracks acceptance. Test whether findings and source evidence improve correct
review decisions. Browser tests prove controls work, not this hypothesis.

## Prepare

Generate control and candidate reports in clean checkouts, recording full commit
IDs. Use fresh destinations and these
[catalog](../fixtures/architecture_demo.py) cases:

- `class-a-forbidden-dependency-pair`: locate the crossing and source; decide
  whether to fix code or request a target decision.
- `class-a-boundary-types-mixed-evidence`: distinguish a confirmed FAIL from
  remaining UNKNOWN evidence.
- `class-a-boundary-types-ordinary-reexport-chain-unknown`: explain why no
  violation does not certify the interface.
- `class-a-recursive-wide-package`: locate the isolated module without claiming
  runtime behavior from absent static edges.
- `make demo`: explain Check A's unresolved-call regression and distinguish
  revision comparison from As-Is/Target comparison.

Replay catalog cases with `make demo-architecture VARIANT=<case> OUTPUT=<fresh-file>`.
Expected rejected fixtures can exit 2 while producing reports; inspect report
verdicts. Scored layouts must share the same saved result and canonical observation.
Freeze findings, UNKNOWNs and source/contract bindings. Keep renderer and observer
provenance separate. Reject evidence differences and hide answer keys.

## Run and record

Use 6–8 reviewing developers. Standardize introduction, browser and viewport;
alternate layouts and task order. Test keyboard use. Record decisions, missed
UNKNOWNs, false claims, source-location time, total time and handoff completeness.
Timeouts and navigation failures remain failures. Preserve anonymous raw rows.

Report outcomes per case without a combined score or significance claim. Retain
changes only when correctness and uncertainty handling hold. Repeated observed
navigation failures must justify any separate explorer.
