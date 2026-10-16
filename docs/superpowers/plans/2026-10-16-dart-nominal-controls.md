# Dart nominal control boundaries — implementation plan

> **For agentic workers:** Use superpowers:executing-plans; implement and verify each step before final independent Astra review.

**Goal:** Replace Dart implementation parser/protocol string dispatch with owned nominal values while preserving collected evidence and conservative unknowns.
**Architecture:** The syntax module owns the existing immutable syntax DTOs and their finite semantic vocabulary; the parser owns raw grammar decoding. A private parse-local adapter decodes each Tree-sitter node kind once, preserves raw node identity, and delegates only the Tree-sitter operations already consumed. Resolution owns resolution outcomes; shared facts own runtime-requirement states.
**Tech Stack:** Python 3.11, StrEnum, Tree-sitter Dart, pytest, native ArchKeel contracts.
**Spec:** User #542 expansion and the parent-approved isolated Dart scope.

## Constraints and review focus

- No casts, Any, ignores, rule exceptions, increased debt budgets, or unproved Dart-project construct capabilities.
- Names, paths, source text, and free-form diagnostic payloads remain data. Closed grammar is decoded as grammar or nominal values.
- Unknown node kinds retain traversable children and never become a known default.
- The parse-local node cache must preserve parent/field identity and must not outlive a parse.
- SDK-free collection, URI/part resolution, directive combinators, source spans, and Compass reports preserve their existing meaning.
- Shared RuntimeRequirementState, Language, SourceProfile and SourceSectionName have one owner in ir.facts.

## Task 1: Native RED controls

- [x] Add actual-source DTO annotation checks and node-boundary tests.
- [x] Add native literal/equality/membership/match/Final probes and unchanged authored Target annotation mutation controls.
- [x] Run hosted tests against the unmodified Dart implementation and record expected failures.

## Task 2: Parser and resolution ownership

- [x] Add parser-owned nominal DTO control values and a private finite syntax vocabulary.
- [x] Implement the parse-local node view, including unknown-kind, parent and field tests.
- [x] Convert parser text grammar through real decoders, preserving source text as data.
- [x] Consume syntax enums in resolver and collection; resolver owns closed binding/outcome categories.
- [x] Preserve serialized fact bytes and ordering at the existing output boundary.

## Task 3: Snapshot and native contract

- [x] Reuse canonical RuntimeRequirementState and preserve the shared-wire producer changes.
- [x] Preserve metadata/root grammar rejection and platform behavior.
- [x] Publish named Dart ports and independently author nominal field intent in the existing Dart contract.
- [x] Enable complete module string-control guards only after real positive source evidence.

## Task 4: Verification and handoff

- [x] Run Dart SDK-free, parser, directives, resolver, partial UML, false-positive, rules, acceptance and Compass demo tests.
- [x] Run Ruff, mypy, hygiene, exact native Target/mutation controls and full self-observation; retain or tighten the baseline.
- [x] Regenerate the ordinary architecture amendment against the actual integrated predecessor.
- [x] Return a clean product-only ref, exact changed-file list, evidence and code-cost explanation for independent Astra review.

## Evidence and remaining review

The genuine original-source RED run is [38939822944](https://github.com/rapiddweller/archkeel/actions/runs/38939822944): 14 expected failures and five native source-guard controls passed. Checks use disposable actual source and unchanged authored Target intent, without historical JSON snapshots.

Independent final Astra review and the parent combined-stack gate remain required before merge; this workstream does not authorize itself to merge.

Final product source checks: [356 focused/native checks](https://github.com/rapiddweller/archkeel/actions/runs/38947340229), [24 complete Compass/Flutter/browser checks](https://github.com/rapiddweller/archkeel/actions/runs/38947367733). Native measurements: 0 violations, 52 typing, 58 unknown, 871 unresolved calls; the baseline tightens from 918. All 111 original-vs-nominal Compass syntax projections match. Parse-cache success/failure cleanup is directly tested. See the architecture note for measured cost and bootstrap scope.
