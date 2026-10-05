# AD-81 The project owns one fail-closed Make gate

Archkeel does not add a generic `archkeel gate` command, project-command configuration, or a
component-to-test policy. Those choices require project-specific semantics the tool cannot infer.

Each repository owns its Make entry point. `make gate` first validates the checked-out policy
with `archkeel validate --root . --baseline architecture-baseline.json --json`, then runs the locked
release checks. With `BASE=<commit>`, `against` also rejects unamended or stale policy widenings;
it already validates the head, so no second self-validation is needed.

`make ci` adds the TypeScript CLI demo, Chromium report acceptance and Mermaid rendering to the gate.
CI runs `make ci-check` and `make mermaid` in parallel. Runtime matrices stay separate.
CI clears its two fixed demo output directories before rebuilding; test timings remain intact.
Make serializes policy, check, build and smoke stages even under `-j`; failure stops later stages.
GNU Make before 4.4 serializes the whole invocation. Pytest still runs its two workers.

Superseded PR runs cancel; main runs have unique groups. The main job has a 60-minute timeout.
Timing artifacts measure runtime; the timeout bounds hangs rather than improving performance.
The extra CI self-report is removed; self-evidence and validation tests remain required.

Rejected: a shell orchestrator, because Make already propagates prerequisite failures. Rejected:
`archkeel.toml` command lists and component-to-test declarations, because Archkeel would own
project policy without evidence that one policy fits all repositories.

Check: `tests/test_make_gate.py`, the CI workflow, and the target-first Make pattern.
