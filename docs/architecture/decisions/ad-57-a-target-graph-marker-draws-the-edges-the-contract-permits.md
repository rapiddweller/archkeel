# AD-57 A target graph marker draws the edges the contract permits

Add optional `<!-- archkeel-target-graph -->` beside the observed
`<!-- archkeel-component-graph -->`. Observed edges include target violations;
the target graph instead draws permitted pairs from the union of `requires`
([AD-32](ad-32-a-component-names-what-it-requires-what-it-does-not-name-is.md)) and
`allowed_dependency` ([AD-15](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md)).
Contracts normally choose one model; the union handles either without changing
its meaning. Neither model means an empty permitted set.

Both readers share marker-aware `_marked_bodies`; drift diagnostics name the
marker. The observed graph still requires exactly one marker; target count errors
apply only to duplicates. `--write-graph` independently rewrites eligible blocks
under [AD-46](ad-46-validate-writegraph-regenerates-the-marked-component-graph.md),
returning a shared page once. Missing, ambiguous or unsupported blocks stay untouched.
`init` writes no target graph before the architect decides dependencies.

[Issue #16](https://github.com/rapiddweller/archkeel/issues/16) needed a view of intent
alongside debt. Changing the existing marker or switching it by invocation would
silently change page meaning, like the rejected scope change in
[AD-49](ad-49-an-allowance-may-name-its-module-exactly-so-a-package-root.md).

Limits: target graph parity proves agreement with the contract, not code conformance
or reviewed rationales. Symbol/source/`through` restrictions collapse to coarse
pairs. Two markers scan the page twice. The shop carries both; an identical second
self graph would add no evidence.

Checks: validation, CLI and demo tests cover target parity/drift, unchanged observed
behavior, both graphs on one page and unsupported target blocks. `docs/architecture/shop.md`
is committed dual-marker evidence.
