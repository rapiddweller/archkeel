# TypeScript adapter decision

Status: approved and integrated with the Core protocol. Publication is separate.

Use TypeScript Compiler API 5.9.3 in a separately versioned, pinned npm package.
It supplies parsing, TSConfig handling and module resolution. The adapter emits
validated `SourceFacts`; Core owns policy and verdicts. See the
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
nothing and executes no project code or scripts. See
[known limits](../known-limits.md) and the
[runtime-alias](../../fixtures/typescript-runtime-aliases.json) and
[hidden-loader](../../fixtures/typescript-hidden-loaders.json) acceptance catalogs.

`make typescript-adapter` checks the strict build, locked offline tarball, Core
decoding and runtime-range refusal. Acceptance also requires the integrated local
gate, independent review, Python/Dart parity and Linux, native Windows and Node
22/24/26 CI. Package source does not prove publication.

[The demo](typescript-demo.md) replays import-rule and revision cases. Process,
collector and snapshot tests cover executable replacement, malformed facts,
coverage and immutable inputs.
