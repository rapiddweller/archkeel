# AD-81 The project owns one fail-closed Make gate

Archkeel does not add a generic `archkeel gate` command, project-command configuration, or a
component-to-test policy. Those choices require project-specific semantics the tool cannot infer.

Each repository owns one Make entry point. Archkeel uses `make gate`, which reuses the locked
release checks and then runs `archkeel validate --root . --json`. CI invokes that target as its
single project-check entry point. The report command remains a separate artifact-producing step;
it does not decide the gate.

Make prerequisites provide the failure boundary. A nonzero project check stops the target, and no
pipe or output filter can replace its status. A negative test deliberately fails a project check
and proves that a later release step does not make `make gate` pass.

Rejected: a shell orchestrator, because Make already propagates prerequisite failures. Rejected:
`archkeel.toml` command lists and component-to-test declarations, because Archkeel would own
project policy without evidence that one policy fits all repositories.

Check: `tests/test_make_gate.py`, the CI workflow, and the target-first Make pattern.
