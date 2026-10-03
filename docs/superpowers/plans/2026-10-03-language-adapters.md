# Language adapters implementation plan

> Execute continuously from the approved target. Use isolated workers for independent
> prerequisites and a fresh independent review before each implementation PR.

**Goal:** interchangeable Python/Dart/TypeScript collection, Core-owned evaluation,
then initialize the DATAMIMIC IDE project against its approved target.

**Architecture:** adapters own parsing/resolution/local IR. A versioned facts-only
process port feeds shared IR; Core owns rules and canonical observations.

**Tech stack:** Python 3.11+, existing stdlib/pytest/mypy/ruff; Node with TypeScript 5.9.3.

**Spec:** `docs/architecture/language-adapter-target.md`, owner approved 2026-10-03.

## Global constraints

- No contract, baseline, verdict or policy threshold in an adapter request/response.
- No language adapter imports another language adapter or Core evaluation.
- Keep Python/Dart behavior and external `archkeel.api` compatible.
- Unknown versions/profiles, malformed evidence, unsafe inputs and incomplete
  resolution cannot produce clean proof. Unsupported evidence stays UNKNOWN/null.
- Configure executable plus argv; no shell, daemon, discovery framework or auto-install.
- Preserve source/revision/runtime provenance and distinct runtime/declaration files.
- No implementation of future HTTP/queue interactions. No Marketplace publication.
- Small separate PRs; local gates precede remote CI. No remote merges in this task.

## Review focus

- Context selection changes binding interpretation; collect ordered raw events,
  then project them in Core. Preserve nested-function ordering/duplicates.
- Re-export proofs and stable bindings survive transport until evaluation completes.
- One collected snapshot evaluates multiple contracts without mutation/recollection.
- TypeScript local JS closure and declaration targets have separate evidence roles.
- Historical snapshots never borrow current files, dependencies or configuration.

### Task 1: active-profile evidence (#274)

**Files:** `ir/profiles.py`, `ir/codec.py`, codec/profile tests, relevant fixtures/ADR.
**Interface:** `profile_for(analyzer: str) -> Profile` rejects unknown identity;
`parse_observation` accepts null only for the identified profile's absent sections.

- [ ] Write/run negative tests for Python null sections and unknown analyzer identity;
      preserve real published Python/Dart identifiers; test Dart supported nulls.
- [ ] Implement explicit profile lookup and profile-specific section validation.
      Replace synthetic fixture identities with official identities where needed.
- [ ] Run targeted checks, `make check`, `make self-observation`; independent review.
- [ ] Commit, push and open separate PR against main; attach it to this task.

### Task 2: collection boundary and Python/Dart migration (#122)

**Files:** `ir/facts.py`, `ir/protocol.py`, `ir/facts_codec.py`,
`schema/source-facts.schema.json`, `analyzer/process.py`, `analyzer/python/*`,
`analyzer/dart/*`, `check/observation.py`, `check/evaluation/*`, `check/ports.py`,
CLI configuration/wiring, architecture contracts/ADRs and affected tests/tools.

**Interfaces:** `SourceCollector.collect(CollectionRequest) -> SourceFacts | CollectionError`;
`collect(request)` process facade; `assemble(facts, contract) -> Observation`.
Protocol owns envelopes; facts owns capabilities, coverage and source values.
Source facts include exports, stable bindings, re-export uncertainty, blank modules,
ordered context events and type-shape facts. No AST crosses the port.

- [ ] Write/run a real contract-free process collection test and a two-contract
      evaluation test (different contexts/facades, immutable facts).
- [ ] Extract shared values and validate bounded typed protocol messages; test malformed
      versions, profiles, identities, references, coverage and process failure/timeout.
- [ ] Move language collectors/local models into Python/Dart modules. Collect
      context events/class fields and existing annotation syntax distinctions as facts.
      Preserve re-export internals until final observation serialization.
- [ ] Move graph algorithms to `ir.graph`; topology, root/inside policy, context
      projection and canonical observation assembly to Core. No AST dependency in Core.
- [ ] Wire every language through the same configured port. Prove replacement by a
      second executable and changed contract semantics without another collection.
- [ ] Migrate internal test imports/spies, tools, docs and active target contracts;
      public API remains compatible. Run focused suites, `make check`, self-observation,
      native target/actual review and independent review before its separate PR.

### Task 3: revision and target identities (#275)

**Files:** `check/snapshot.py`, runtime comparison/profile inputs, module-target
codec/schema/renderer and tests.
**Interfaces:** profile-specific snapshot inputs; collision-free repository path
file identity; deterministic logical selector mapping, preserving Python names.

- [ ] Write/run tests for same-revision sources/resolver inputs, missing/unsafe inputs,
      TypeScript filename collisions and distinct runtime/declaration targets.
- [ ] Implement language-aware snapshots and comparability, generic target paths and
      file/module ownership mapping. Record the mapping in ADR and conformance fixtures.
- [ ] Run profile/snapshot/target suites, `make check`, self-observation and review;
      create separate stacked PR.

### Task 4: TypeScript import profile (#276)

**Files:** `packages/typescript-adapter/{package.json,package-lock.json,src/*}`,
Python profile/config/init integration, cross-runtime fixtures and documentation.
**Interfaces:** entry serves the shared protocol; project owns compiler Program and
resolver; collect returns source facts/coverage; protocol owns the TS binding.

- [ ] Write/run fixtures covering imports/reexports/import types/dynamic literals,
      TSConfig paths/extends, JS/CJS/declarations, unresolved/shadowed/computed imports,
      invalid syntax/config, graph closure and capability refusal/UNKNOWN.
- [ ] Implement pinned Compiler API collection, strict protocol binding and explicit
      install/build/check commands; execute no project code or plugins.
- [ ] Integrate TypeScript init/config/report/check and profile-aware coverage;
      run adapter conformance plus Core gates and review; create separate stacked PR.

### Task 5: native planned-interface display (#278)

**Files:** `render/html.py`, target detail tests.
**Interface:** `planned` displays as proposed/unimplemented, separate from `public`.

- [ ] Reproduce missing proposed interfaces in a nested future target; implement
      truthful detail display without granting permission; run target/browser checks.
- [ ] Review and create separate PR.

### Task 6: IDE onboarding

**Files:** IDE ArchKeel config/contracts/architecture docs and gate entry point.
**Interfaces:** host APIs in hosts; application consumes ports; Platform decoding
in platform. Platform remains owner of files/locks/LSP/MCP/auth/persistence.

- [ ] Run the implemented TypeScript init once; preserve existing copied/user files.
- [ ] Encode the accepted target, review every maintained subtree and mark current
      exceptions explicitly. Generate native Target/Actual report.
- [ ] Run `npm run verify` and ArchKeel local checks; commit only onboarding files.
      Report host/Marketplace checks as unverified unless actually exercised.
