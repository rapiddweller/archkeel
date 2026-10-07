# TypeScript adapter decision

Status: superseded by [AD-210](decisions/ad-210-typescript-frontend-ships-in-the-package.md).
The frontend in `archkeel.analyzer.typescript` collects TypeScript; the old npm collector is
removed. A frozen output from its pinned revision remains the differential reference.

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

`make typescript-differential` compares the frontend with the 576-case frozen reference
captured from the old Node collector (504 equivalent, 72 conservative, 0 defects). Each
conservative case has a reason in `fixtures/typescript-differential-allowlist.json`; unexpected
differences fail. The low-resolution real-world corpus remains a limit of this evidence.

[The demo](typescript-demo.md) replays import-rule and revision cases. Process,
collector and snapshot tests cover executable replacement, malformed facts,
coverage and immutable inputs.
