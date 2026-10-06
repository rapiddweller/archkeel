# TypeScript adapter decision

Status: the pinned npm package chosen here is superseded by
[AD-210](decisions/ad-210-typescript-frontend-ships-in-the-package.md). The frontend in
`archkeel.analyzer.typescript` now collects TypeScript; the npm package stays in
`packages/typescript-adapter` only as the reference its differential tests compare against.

The collector emits validated `SourceFacts`; Core owns policy and verdicts. See the
[language-adapter target](language-adapter-target.md) for the boundary.

## Evidence and limits

The collector measures import graphs, ownership, external scopes, cycles and
layout. It does not measure symbols, types, constructs, calls or private use.
Unavailable signals remain null/UNKNOWN; reports show n/a and budgets refuse them.
Older lock/delta zero sentinels remain readable as unmeasured.

Incomplete resolution, computed or indirect loaders and unproved runtime targets
cannot prove absence. Runtime JavaScript and declaration files retain distinct
identities. Historical scans use the same revision's source and resolver inputs;
they cannot borrow working-tree files or installed dependencies. Analysis installs
nothing and executes no project code or scripts. The frontend also leaves a gap where
the compiler would resolve: `extends` through a package, `exports` and `typesVersions`
maps, project references and constructs its grammar cannot parse. See
[known limits](../known-limits.md) and the
[runtime-alias](../../fixtures/typescript-runtime-aliases.json) and
[hidden-loader](../../fixtures/typescript-hidden-loaders.json) acceptance catalogs.

`make typescript-differential` runs the frontend and the reference adapter over the
acceptance catalogs, the demo variants and the shop fixtures. It fails on a wrong edge or
an unexplained difference; every case where the frontend claims less needs a one-line
reason in `fixtures/typescript-differential-allowlist.json`. The reference adapter is built
by `make typescript-adapter` until it is removed.

[The demo](typescript-demo.md) replays import-rule and revision cases. Process,
collector and snapshot tests cover executable replacement, malformed facts,
coverage and immutable inputs.
