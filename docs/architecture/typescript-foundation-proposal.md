# TypeScript adapter decision

Status: approved. The collector is integrated with the Core protocol.
Detailed architecture and contracts live in the
[language-adapter target](language-adapter-target.md). Publication is separate delivery work.

## Decision

Use the TypeScript Compiler API 5.9.3 in a separately versioned, pinned npm
artifact. The compiler already provides the parser, TSConfig handling and module
resolver this target needs. Python plus tree-sitter would add grammar/native
dependencies and require a second module resolver; regex cannot resolve the
observed syntax.

The adapter emits validated `SourceFacts` through the configured process port;
Python Core owns policy and verdicts. See the [target](language-adapter-target.md)
for ownership, source layout, contracts and interfaces.

## Evidence and limits

The DATAMIMIC extension scan covers 78 files: 76 TypeScript files plus
`supportedHosts.cjs` and `supportedHosts.d.cts`. Keep the runtime file and its
declaration as distinct identities. Observe the local JavaScript dependency
closure from the same revision. Historical analysis must not borrow working-tree
files, installed dependencies or generated inputs.

The adapter measures the proven import graph, ownership, external scopes, cycles
and layout. Computed or shadowed imports, incomplete resolver inputs and
unobserved closure cannot prove absence; affected results stay UNKNOWN. TypeScript
does not measure symbols, references, bindings, types, constructs, calls, typing
positions or private-use metrics. Their signals and coverage counts remain
null/UNKNOWN. Fresh results use `calls_total: null` with `resolution: n/a`.
Older lock/delta zero sentinels remain readable as unmeasured. Reports show n/a
and budgets refuse unavailable signals. See
[the measurement contract](../reference.md#regression-checks).
Local value aliases and directory package metadata retain compiler evidence,
but their unproved runtime target stays null and coverage UNKNOWN. Non-explicit
CommonJS targets also stay UNKNOWN; direct CommonJS loads need a physical runtime
file. Static TypeScript imports keep compiler semantics. Existing explicit
JavaScript closure is observed even when the compiler substitutes TypeScript.
Node namespace assertions preserve loader identity; callback use and unproved
value escapes and rest bindings stay UNKNOWN. Known `Module` and `default`
exports use the same boundary; type-only references create no value gap.
Known loader-bearing value exports retain UNKNOWN at the export site; explicit
type-only exports and local exports of proven type-only imports remain supported.
Full Dart type and construct analysis is also outside this decision.

The npm package is locked and does not install dependencies during `report` or
`check`. Reproducibility depends on collector/compiler identity, TSConfig,
resolver settings and snapshot input digests. Analysis does not execute project
code or package scripts. HTTP and queue relationships need separate evidence;
this adapter adds no HTTP/broker observer or cross-language rule.

## Delivery and verification

Replacement acceptance must prove the configured executable can return valid
and invalid facts while Core retains policy decisions. Extension onboarding follows
active-profile validation (#274), revision evidence (#275) and the vertical slice (#276).

Acceptance requires the integrated local gate, independent review and exact-head
Linux, native Windows and Node 22/24/26 CI. Package checks include a strict build,
locked offline tarball install, actual Core decoding and runtime-range refusal
(`packages/typescript-adapter/test/`). Source implementation does not prove publication.

Core acceptance requires Python/Dart parity. Checks cover
[configured replacement](../../tests/test_collection_process.py),
[collector facts](../../tests/test_language_collectors.py),
[wire conformance](../../tests/test_collection_conformance.py),
[negative protocol/coverage cases](../../tests/test_collection_boundary_regressions.py),
[revision-bound inputs](../../tests/test_profile_comparison_commits.py) and
[explicit onboarding](../../tests/test_typescript_onboarding.py). Enabled rules need positive
and negative fixtures; unsupported capabilities retain null/UNKNOWN. The shared
[runtime-alias](../../fixtures/typescript-runtime-aliases.json) and
[hidden-loader](../../fixtures/typescript-hidden-loaders.json) catalogs cover
compiler substitution, unproved runtime targets and indirect loaders through
[CLI acceptance](../../tests/test_typescript_init_acceptance.py).

`make typescript-adapter` runs the package checks above.
`make demo-typescript OUTPUT=build/typescript-demo` replays the 32-variant catalog
and a committed revision check. See [the demo](typescript-demo.md).
