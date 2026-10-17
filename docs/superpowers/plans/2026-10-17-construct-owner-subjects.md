# Qualified Construct Owner Subjects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make existing forbidden_construct class/function scopes work through subject preflight and evaluator receipts without vacuous PASS.

**Architecture:** Enforcement already matches construct owner qualified names. In the existing evaluation/rules owner, one private selector will admit actual class/function/method symbol facts only from the scanned/clipped module set; preflight and receipt issuance share it. Existing module/package receipts stay unchanged. The canonical EntityKind vocabulary is projected only while reading open symbol kinds; unknown/future record kinds stay open and are skipped.

**Tech Stack:** Python, existing RawRecord/EntityKind/native observe/report/pytest; GitHub Actions only.

**Spec:** Issue #542; existing forbidden_construct source semantics in docs/rules.md. Base 68b656668a3fdbbbe482881d0dab41ff89a21ca3.

## Global Constraints

- One existing production owner: src/archkeel/check/evaluation/rules.py; no schema, global Record.kind closure, selector framework, whitelist, guard widening or budget increases.
- Preserve other rule families, module/package behavior and source_modules clipping.
- Add only optional keyword symbols=() to rule_evaluation_facts; missing symbol evidence cannot certify a named owner.
- Owner receipts name actual owner symbols, never an entire containing module merely because one class/function was checked.
- Incomplete source coverage and partial construct capability remain UNKNOWN through existing assessment rules.
- Main/Root writes stay with the assigned steward; separate bounded source carrier and independent Astra review.

## Review Focus

- Clean real class/function/method owners must produce a complete scoped receipt and PASS.
- A real forbidden comparison mutation must produce a trace-valid FAIL with the same contract.
- Missing owners, symbol-free inputs and unscanned/outside modules cannot certify PASS.
- Module-prefix sibling names are not owner matches.
- Existing module/package receipts and no-source diagnostics remain compatible.

### Task 1: Reproduce both broken phases before source

**Files:** Extend tests/test_string_comparison_observation.py using its real native _observe_one_rule helper; reuse inside-rule/report helpers where necessary.

- [ ] Add actual class/function/method positive scopes and mutation controls, checking diagnostics, native RuleAssessment status and receipt subject/fact evidence.
- [ ] Add missing-owner, near-sibling, no-symbol/default keyword, outside-source_modules and incomplete-scan negatives.
- [ ] Run hosted RED and retain the real expected failure (current RULE_WITHOUT_SUBJECTS / missing owner receipt), with no production changes.

### Task 2: Fix the one shared responsibility

**Files:** Modify src/archkeel/check/evaluation/rules.py; document exact behavior in docs/rules.md.

- [ ] Add a private typed selector over actual structural symbol declarations and real module membership; use the canonical EntityKind subset, not raw control strings.
- [ ] Reuse it for ForbiddenConstruct-only preflight and the owner receipt fallback; pass actual symbols from _collect_rule_violations. Existing module receipts remain byte-compatible and owner subjects stay exact.
- [ ] Run native GREEN and relevant analyzer/inside/receipt/recorded-rule regressions, Ruff and strict type checks.
- [ ] Send Root the small production SHA early to unblock actual UI/result integration.

### Task 3: Verify and freeze

- [ ] Confirm unchanged baseline budgets and exact qualified guard behavior through real run_report; preserve incomplete-scan UNKNOWN.
- [ ] Provide the normal receipt/no-write and precise native site evidence as appropriate to the final isolated carrier.
- [ ] Freeze separate source for independent Astra review and Root integration; do not repeat the combined full suite owned by Root.
