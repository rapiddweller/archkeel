# Report review pilot

> **Not on `main`.** This page describes the Python engine before [AD-432](architecture/decisions/ad-432-the-rust-core-is-the-only-decision-path.md). On `main`, the Rust core decides
> `archkeel validate` and `archkeel report` for Rust and TypeScript projects, and each other
> command gives a typed refusal with exit 2. See the [state of `main`](reference.md#state-of-main). The demo targets (`make demo*`) are deleted.

Status: prepared; no human results. [#236](https://github.com/rapiddweller/archkeel/issues/236)
tracks acceptance. Test whether findings and source evidence improve correct
review decisions. Browser tests prove controls work, not this hypothesis.

## Prepare

Generate control and candidate reports in clean checkouts, recording full commit
IDs. Use fresh destinations and these
[catalog](https://github.com/rapiddweller/archkeel/blob/4.0.1/fixtures/architecture_demo.py) cases:

- `class-a-forbidden-dependency-pair`: locate the crossing and source; decide
  whether to fix code or request a target decision.
- `class-a-boundary-types-mixed-evidence`: distinguish a confirmed FAIL from
  remaining UNKNOWN evidence.
- `class-a-boundary-types-opaque-map-values-unknown`: explain why no
  violation does not certify the interface.
- `class-a-recursive-wide-package`: locate the isolated module without claiming
  runtime behavior from absent static edges.
- The `check` demo: explain Check A's unresolved-call regression and distinguish
  revision comparison from As-Is/Target comparison.

Replay the catalog cases with release 4.0.1; `main` has no demo target.
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
