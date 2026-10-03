# TypeScript adapter decision

Status: implemented locally; cross-platform CI and publication remain pending. Architecture
and contracts live in the [language-adapter target](language-adapter-target.md).

## Decision

Use the TypeScript Compiler API 5.9.3 in a separately versioned, pinned npm
artifact. The compiler already provides the parser, TSConfig handling and module
resolver this target needs. Python plus tree-sitter would add grammar/native
dependencies and require a second module resolver; regex cannot resolve the
observed syntax.

The TypeScript adapter owns parsing, project resolution and its local IR. It emits
validated `SourceFacts` through the configured process port. Python Core owns
ownership, rule availability, evaluation, metrics and verdicts. Adapters receive
revision, scope and resolver inputs; they never receive policy or decide PASS.
See the [target](language-adapter-target.md) for physical ownership, contracts
and interfaces.

The package is under `packages/typescript-adapter/`. Its source is split across
`entry.ts`, `project.ts`, `collect.ts` and `protocol.ts`; the Python scanner does
not inspect `.ts`, so the npm package has its own architecture contract.

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
positions or private-use metrics. Those values stay null/unknown, never zero.
Full Dart type and construct analysis is also outside this decision.

The npm package is locked and does not install dependencies during `report` or
`check`. Reproducibility depends on collector/compiler identity, TSConfig,
resolver settings and snapshot input digests. Analysis does not execute project
code or package scripts. HTTP and queue relationships need separate evidence;
this adapter adds no HTTP/broker observer or cross-language rule.

## Verification

`make typescript-adapter` checks the locked package, an isolated offline consumer,
and the actual Core decoder and Node runtime boundaries. Expanded CLI onboarding
and incomplete-coverage controls retain UNKNOWN and unavailable measurements.
Cross-platform CI, independent acceptance and publication remain separate gates.
