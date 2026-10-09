# AD-156 Self evidence is generated per test session

Generate self evidence from current code; do not commit result or provenance
snapshots. Even compact snapshots change on unrelated branches and create merge
conflicts without adding a source of truth. This replaces the original decision
to commit two compact evidence files.

Share one validated report per test session with a dev lock and atomic completion
marker. Failed generation cannot become cached evidence; sessions start fresh.
Self tests retain coverage, rule, interface and contract checks. Reviewed baselines
and amendments remain versioned.

`make self-observation` writes local JSON/HTML under ignored `test-artifacts/`.
It uses the normal report command; no separate snapshot generator is needed.

[Fixture proof](../../../tests/test_self_fixture.py).
