# Typed Diagnostic Owner Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline; parent obtains a fresh independent Astra review after the complete bounded change.

**Goal:** Give diagnostics one nominal owner while shrinking ir.model and preserving valid wire and constructor behavior.
**Architecture:** ir.diagnostics owns DiagnosticKind, DiagnosticCode, Diagnostic, DiagnosticError and ReportLocation. ir.model explicitly reexports the exact same classes; current producers use these nominal values. Existing governance owns the module, with independently authored API intent and a whole-module control guard.
**Tech Stack:** Python3.11 StrEnum, frozen dataclasses, native observation, pytest, Ruff, Mypy; remote GitHub branch and hosted Actions only.
**Spec:** docs/superpowers/specs/2026-10-16-typed-diagnostic-owner.md; parent approved extraction including ReportLocation and compatibility facades.

## Global Constraints

- Preserve11 DiagnosticKind and32 DiagnosticCode wire spellings and ordering, existing schemas and valid direct constructor strings.
- Preserve invalid-kind/code messages, contract_invalid/code consistency, empty-field, newline-remedy and JSON Pointer checks.
- No Core-to-CLI import, generic conversion framework, global miscellaneous enum or alias-constant dispatch.
- Keep unrelated Result/Comparison/Amendment/Command work separate; preserve RuleGrammar and Version colleagues' changes through targeted integration.
- Protect only the fully migrated diagnostic owner; no whole-model absence claim.
- No baseline, cap or allowance increase. Compare exact native type-position and unresolved-call evidence against the actual integrated predecessor.
- Use an isolated remote branch and hosted checks; never a local executor.

## Review Focus

- Invalid kinds/codes and missing/forbidden codes preserve exact error categories and messages.
- Legacy valid string construction produces the same serialized diagnostics and mutable/frozen behavior.
- DiagnosticError and ReportLocation preserve public model identity and field/signature types.
- Native fixed Target rejects kind/code widening; the control guard rejects raw equality, membership, match and Final-string dispatch.
- Resolving a nested diagnostic field may reveal a later existing unknown; distinguish unchanged position IDs from genuine new sites.

### Task1: Owner, producers and source-backed controls

**Create:** src/archkeel/ir/diagnostics.py; tests/test_typed_diagnostic_owner.py.
**Modify:** src/archkeel/ir/model.py, necessary diagnostic producers/decisions and existing enum-iteration tests; architecture-contract.json, docs/architecture/contracts/ir.json, Makefile and diagnostic scope notes.
**Interfaces:** Existing model.DiagnosticKind/DiagnosticCode/Diagnostic/DiagnosticError/ReportLocation imports retain identity. Diagnostic.kind:DiagnosticKind; code:DiagnosticCode|None; locations:tuple[ReportLocation,...]. New owner classes preserve existing constructors and errors.

- [ ] Write nominal identity, legacy-byte/error, independent API Target, actual-source widening and guard mutation tests.
- [ ] Run hosted RED on unchanged production; inspect that nominal owner/protection are absent.
- [ ] Extract and normalize the diagnostic owner, retain explicit model facades, update real producers and decisions without a second vocabulary.
- [ ] Run diagnostic/schema/report/validation regressions, native controls, strict Mypy, Ruff and hygiene; fix only demonstrated defects.
- [ ] Run actual own validation and exact before/after type-position and unresolved-call evidence; generate normal amendment only for owned contract intent.
- [ ] Freeze a clean product ref with notes and evidence for parent's independent Astra, combined full-suite gate and separate PR.
