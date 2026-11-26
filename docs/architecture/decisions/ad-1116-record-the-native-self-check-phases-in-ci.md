# AD-1116 Record the native self-check phases in CI

**Status.** Accepted. Builds on AD-878. Part of #659.

**Decision.** The PR gate and main CI request the existing timing sidecar for the native
self-check report. Each job writes the sidecar in its own runner temporary directory.
The job log and summary show its JSON. If the report produces no file, they say so.
The report runs once. Its frame and gate verdict do not change.

**Reason.** A phase budget needs independent measurements of the workload that the gate runs.
The existing nightly measures a pinned public project, not the native self-check.
Four nightly SymPy report receipts from November 22–25 show collect medians from 8.69 to
18.14 seconds across different revisions and runners. They do not establish a safe gate limit.

**Limit.** This records samples; it sets no limit and makes no speed claim.
The sidecar is not part of the deterministic result frame. A refused report gives no timings.
The difference between `core_seconds` and the sum of phases is time without a phase label.
Evidence-based budgets and a nightly ratchet are tracked in #2036.

**Tests.** `tests/test_make_self_check.py` checks opt-in wiring and both CI summaries.
`tests/test_cli_timings.py` checks a real report, sidecar and unchanged result.
