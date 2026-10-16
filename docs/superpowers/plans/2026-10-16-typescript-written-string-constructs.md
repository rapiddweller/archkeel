# Native TypeScript written-string constructs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Produce trace-valid written-string comparison facts from real TypeScript and JavaScript without claiming complete absence.

**Architecture:** The existing parse.py owner decodes raw Tree-sitter kinds with _node_kind and emits a frozen syntax.StringComparison(span: Span, scope: str | None). Collection publishes canonical construct facts and PARTIAL capability; profiles own independent optional receipt groups and the existing evaluator registry authenticates actual source/capability combinations.

**Tech Stack:** Python 3.11, pinned Tree-sitter, existing immutable lexical DTOs and HRC Core; hosted GitHub Actions only.

**Spec:** docs/architecture/typescript-written-string-controls.md

## Global Constraints

- Base fa37f59600cfae64ba0528cb56e609c6bbd756e4; use the direct _node_kind decoder, never the obsolete adapter/cache.
- Written ==, ===, !=, !==, switch case values, plain templates and parenthesized literals only; no imported/alias/closure value propagation.
- Shared ForbiddenConstructKind.STRING_LITERAL_COMPARE and ConstructSupport.PARTIAL; empty or unknown syntax never proves PASS.
- Reuse the existing AST walk, Span and named scope inventory. Anonymous scopes do not gain fabricated names.
- Genuine JS selection uses allowJs/checkJs; no compiler/runtime authority, browser-wide guard, new casts/Any/ignore/allowances or increased budgets.
- All work remains in isolated remote branches; no executor, filesystem or local Git calls. Final independent Astra review is coordinated by Root.

## Review Focus

- IIFEs/callbacks retain only existing named lexical ownership; actual JS fixtures prove module fallback and containing named function.
- Unicode before a written literal keeps real UTF-16 evidence coordinates; actual TS/JS source asserts the citation.
- Unknown parent nodes remain traversable, while unknown template children cannot become plain literals.
- Legacy inner UML arrays with constructs=null still replay; separate construct receipts do not weaken the four-section atomic group.
- Spoofed DECIDED/other-kind/missing capabilities and legacy construct authority are rejected at the registered source boundary.

## Task 1: Native lexical facts and authenticated receipts

Files: parse.py, syntax.py and collect.py under src/archkeel/analyzer/typescript; ir/profiles.py; ir/codec_observation.py; check/evaluation/evaluate.py; tests/test_typescript_string_constructs.py; tests/test_nullable_profile_measurements.py.
Consumes: parse(rel_path: str, data: bytes) -> Syntax; existing _node_kind/_walk/_Source.span and named scopes.
Produces: syntax.StringComparison(span: Span, scope: str | None); Syntax.string_comparisons: tuple[StringComparison, ...]; canonical witnessed SourceSectionName.CONSTRUCTS facts with PARTIAL capability.

- [x] Preserve the independently authored fixed HRC contract and original 38956449624 RED (25 expected failures, 44 controls).
- [x] Extend native JS callback/IIFE, comment-unwrapping and UTF-16 probes; run on untouched fa37 and inspect expected missing-feature/registry failures.
- [x] Implement the smallest producer/DTO/profile/registry change; keep enum vocabulary private and derived from consumed AST kinds.
- [ ] Run focused native tests, legacy/profile replay, Ruff and strict mypy; correct implementation failures, then commit.

## Task 2: Authored API intent and native type mutations

Files: docs/architecture/contracts/typescript.json; docs/architecture/contracts/ir.json; tests/test_typescript_control_target.py; Makefile.
Consumes: the actual new syntax port and independent typed Profile receipt grouping.
Produces: named public lexical port plus authored Span/sequence/receipt-group annotations and genuine source-widening rejection.

- [x] Add actual source-widening probes against unchanged current Target; observe the missing new field guard.
- [ ] Author the smallest independent Target intent and include tests in normal TypeScript/PR commands.
- [ ] Prove normal real source PASS and changed Span/sequence/group types trace-valid FAIL without changing intent during each mutation.

## Task 3: Freeze, full verification and independent review

- [ ] Run TypeScript native/differential, pinned compiler, all legacy DTO/byte controls, repository hygiene and complete project suite.
- [ ] Measure own native validation against exact fa37; preserve UNKNOWN positions/routes and tighten or retain every budget.
- [ ] Generate the ordinary baseline/amendment receipt, freeze clean source, and rerun the committed exact no-write gate.
- [ ] Send the clean source and precise evidence for independent final Astra review, address actual Important findings, then create a Part of #542 PR; Root controls integration.

## Execution ledger

Ruling: Root explicitly authorized implementation of this previously reviewed bounded design; no new confirmation pause is needed. Remote GitHub branches and hosted Actions replace local worktree/scripts because the task explicitly forbids local execution.
Pre-flight: parser -> syntax DTO -> collector uses one lexical port; collector -> registry shares the canonical construct identity; profile -> codec shares atomic receipt groups. No independent competing vocabulary or AST layer is introduced.
Task 1: refreshed native RED 38964339186/job117186950096: 36 expected failures, 47 controls passed. The existing legacy source registry accepted an unimplemented DECIDED construct claim; that exact boundary is now covered. Minimal product implementation is next; no success claim yet.

Task 1: focused native 38964957065: 83 tests passed, 405 lexical/protocol regressions passed, strict mypy 133 files passed; two formatter issues were corrected in the candidate.
Task 2: native Target RED 38965409045/job117190542715: all three real Span/scope/sequence source widenings incorrectly remained PASS under the prior Target. Independently authored port intent is now added; GREEN is pending.
