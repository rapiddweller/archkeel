# AD-81 The project owns one fail-closed Make gate

Each repository owns its Make gate. Archkeel does not infer project commands or
component-to-test policy, and adds no generic gate command or config layer.

`make gate` validates head policy with
`archkeel validate --root . --baseline architecture-baseline.json --json`, then runs
locked release checks. With `BASE=<commit>`, `against` already validates head and
rejects unamended or stale widenings; do not validate twice.

`make ci` adds TypeScript CLI demos, Chromium acceptance and Mermaid rendering.
CI runs `ci-check` and `mermaid` in parallel, with separate runtime matrices.
It clears two fixed demo directories while retaining timings. Make serializes
policy, check, build and smoke under `-j`, stopping on failure. Before GNU Make 4.4,
the whole invocation serializes; pytest still uses two workers.

Superseded PR runs cancel; main groups stay unique. The main timeout is 60 minutes;
timing artifacts measure runtime, while the timeout bounds hangs. Remove the extra
CI self-report; retain self-evidence and validation tests.

Make already propagates failures. Shell orchestration and TOML test policies would
add ownership the tool cannot justify. Checks: `tests/test_make_gate.py`, CI workflow
and the target-first Make pattern.
