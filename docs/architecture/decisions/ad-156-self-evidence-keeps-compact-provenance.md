# AD-156 Self evidence keeps compact provenance

Commit compact self-result and provenance files; generate full JSON/HTML through
`make self-observation` or tests. Large generated copies add conflicts
without another source of truth.

Share one validated report per test session with a dev lock and atomic
completion marker. Failed generation cannot become cached evidence; sessions start
fresh. Provenance normalizes only Git HEAD/dirty and retains source, analyzer, policy,
coverage, UNKNOWNs and records in digest comparison. Mutation tests decode independent
copies.

[Fixture proof](../../../tests/test_self_fixture.py).
