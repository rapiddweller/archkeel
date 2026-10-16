# Typed dependency contracts implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement the tasks in order with RED/GREEN evidence. The user explicitly ordered execution; preserve independent final Astra reviews and separate PRs.

**Goal:** Address #540 and #541 with shared typed selection and enforceable API intent, then complete the expanded #542 migration including parser and protocol controls. The initial dependency-only guard is one increment and must not close #542.
**Architecture:** The model owns selector vocabulary and pure matching. The existing contract codec owns conversion from wire/record strings. Core and projections consume the same selection; Core remains the verdict authority.
**Tech Stack:** Python 3.11+, dataclasses/NamedTuple/StrEnum, existing pytest, native ArchKeel contracts and GitHub Actions.
**Spec:** docs/superpowers/specs/2026-10-16-typed-component-contract-design.md at 8a5f650c66d13add619eaf38a4fc69dd6fffd8a8.

## Global constraints
- Keep Contract 3.4/3.5 grammar, old-version rejection, canonical default bytes and digests.
- Module/path/symbol data stays string data; closed modes/kinds use owned types.
- Missing/incomplete source evidence stays UNKNOWN.
- No increased UNKNOWN/coupling/call budgets, casts, reflection or hygiene exemptions.
- Decode dependency intent once per projection preparation, not per matrix cell.
- Isolate changes in GitHub branches; the exhausted local executor is unusable. Hosted checks provide RED/GREEN evidence.

## Review focus
- Real component labels differ from package names; all-package/exact ownership must agree in Core/explorer.
- Ambiguous ownership must not gain a whole-component decision.
- Explicit namespace intent must not expand to other packages of the same component.
- Missing/invalid selector fields must preserve valid legacy defaults and reject bad values.
- A native type/API mutation must fail independently of a snapshot or manufactured observed graph.

## Task 1: Shared dependency selection (#540)

**Files:** model.py, codec_contract.py/codec.py, module_explore.py, decisions.py, report_projection.py, current selector consumers and tests/test_dependency_selectors.py; add tests/test_typed_dependency_api.py.

**Interfaces:**
- SelectorMatch(StrEnum): PREFIX='prefix', EXACT='exact'.
- DependencyTargetKind(StrEnum): MODULE='module', IMPORT_NAMESPACE='import_namespace'.
- ModuleSelection(packages: tuple[str,...], exact_modules: tuple[str,...]); matches(module: str)->bool.
- DependencySelection(source: ModuleSelection, target: ModuleSelection).
- DependencySelector(source: str, target: str, target_symbol: str|None=None, source_match: SelectorMatch=PREFIX, target_match: SelectorMatch=PREFIX, target_kind: DependencyTargetKind=MODULE).
- DependencySelector.component_pair(components: tuple[ComponentOwnership,...])->tuple[str,str]|None and .select(components)->DependencySelection.
- ForbiddenDependencyRule.selector->DependencySelector; existing helper facades keep typed signatures.
- codec_contract.parse_dependency_selector(record: Record)->DependencySelector, re-exported through codec.

- [ ] Write a failing real-label both-prefix regression and typed API assertions.
- [ ] Run existing source plus new tests on a temporary hosted branch; observe expected applicability/type failures.
- [ ] Implement the typed model and codec conversion; shared selection replaces independent report matching.
- [ ] Prepare decoded selectors once in module exploration and permission projection; preserve filters and scope rules.
- [ ] Cover additional/exact packages, ambiguous ownership, all mode combinations, namespace nonexpansion, invalid inputs and old/default bytes.
- [ ] Run focused selector/namespace/model/widening suites, lint/type/hygiene and required CI; create independent PR closing #540.

## Task 2: Native own API contract (#541)

**Files:** docs/architecture/contracts/ir.json, focused native tests, own API/architecture documentation and required Makefile tests.

**Consumes:** Task 1 types and method signatures.
**Produces:** Independent declarations.uml intent and native mutation controls for the dependency API.

- [ ] Author intended enum, selector-field and selection-return declarations using the existing Target schema.
- [ ] Add native source controls: correct declarations pass; a field/parameter widened to str or an untyped return fails; unsupported proof remains UNKNOWN.
- [ ] Demonstrate an outside-API crossing is rejected by interface_boundary.
- [ ] Make the intended type/API owner explicit without restructuring all IR or creating a second model.
- [ ] Keep raw codec entry points distinct; classify remaining broad IR findings instead of wildcard exemption.
- [ ] Run required native/self/Target regressions and CI; create separate PR closing #541.

## Task 3: Enforce migrated control vocabulary (#542)

**Files:** architecture-contract.json, domain-control tests, docs/rules.md and architecture documentation; actual affected dependency policy functions.

**Consumes:** Typed selectors and independently declared API from Tasks 1–2.
**Produces:** Existing forbidden_construct enforcement on the migrated domain seam, native mutation proof and an honest scope/migration ledger.

- [ ] Locate remaining string control at the affected seam; migrate to the owned enums/type dispatch.
- [ ] Add native negative controls for literal equality, membership, match and Final-string disguises in protected source scope.
- [ ] Activate existing string_literal_compare policy for the migrated domain APIs; keep wire/data handling in its responsible boundary.
- [ ] Prove enums and legitimate data inputs remain accepted. Do not add blanket exemptions.
- [ ] Record measured protected/remaining scope and avoid claiming whole-repository string freedom.
- [ ] Run native self/guard/compatibility suites and CI; create a separate scoped PR contributing to #542; keep the expanded issue open.

## Execution and review

Pre-flight: Task 2 consumes Task 1 exact type names/signatures; Task 3 consumes both the typed API and its explicit scope. These are sequential dependencies. Read-only Target research may run independently.
For every task record hosted RED and GREEN run URLs in its PR. Independent Astra reviews each final issue diff and then the combined final state. Resolve all blockers, obtain required green checks at the final head, merge in order and verify issue closure.


## Expanded scope after user clarification

The user explicitly prohibits comparisons with parser/protocol control strings too. The execution ledger records the current staged work and evidence. Migrate each coherent owner independently: state; collector protocol/facts; language configuration and syntax DTOs; graph; CLI; contract grammar; presentation and browser ingress. Preserve existing bytes, malformed-input rejection, actual capability limits and unknown evidence. An input parser is not an exception. Structural JSON key identity remains open data and belongs to the input codec's field grammar, not a mirrored key enum.

Before activating each whole-module guard, demonstrate a native positive and fixed-contract source mutations on the actual source. Independently authored Target fields/returns must reject widening to strings. Never replace incomplete native proof with an inferred observed Target. Static compiler/protocol validators supplement rather than impersonate native capability.

Separate #544 grants may proceed as their own feature with exact caller/target module identity, schema-version compatibility, and negative symbol/forwarder controls. It must not broaden the publication inventory.
