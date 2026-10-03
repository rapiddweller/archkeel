# TypeScript adapter decision

Status: approved. The collector is integrated with the current Core protocol.
Final independent acceptance and exact-head CI remain pending; no publication. Detailed architecture
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

## Delivery and verification

The work is split by dependency: active-profile validation (#274), language-aware
revision evidence (#275), the TypeScript vertical slice (#276), then extension
onboarding. Python and Dart use the same process port and retain their own parser,
resolver and local IR. Replacement acceptance must prove the configured executable
can return valid and invalid facts while Core retains all policy decisions.

LOCAL VERIFIED: 39 collector tests, 25 onboarding tests, strict TypeScript build and an isolated,
locked offline tarball install. The actual Core decoder and runtime range checks
are included. The extension target previously observed 78 files across five
owners and seven hosts-to-Platform type-import violations.

PENDING: the integrated gate, independent final review and exact-head Linux,
native Windows and Node 22/24/26 CI. The package has not merged or been published.

Local acceptance covers Python/Dart parity, replacement through configuration,
malformed protocol and incomplete-coverage cases, deterministic revision-bound
observations, and positive/negative fixtures for enabled rules. Exact-head CI is
still required.
