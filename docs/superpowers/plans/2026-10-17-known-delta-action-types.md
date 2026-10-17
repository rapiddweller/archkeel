# Known Delta Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Type the four actions actually produced and checked by Delta governance while keeping public future Delta actions open.

**Architecture:** The existing `ir.model` owns `KnownSemanticChangeKind` (`added`, `removed`, `relocated`, `changed`). `check.delta` uses it to classify actual changes; `check.expectation` converts open wire text once into the known domain at its real governance ingress and retains typed keys through decisions. No new production module or generic conversion framework.

**Tech Stack:** Python 3.11 StrEnum/dataclasses, pytest, native ArchitectureReport/Target, GitHub Actions.

**Spec:** Issue #542 and the approved bounded Core action design; `docs/architecture/known-delta-action-types.md` records the final boundary/evidence.

## Global Constraints

- Base: `68b656668a3fdbbbe482881d0dab41ff89a21ca3`; preserve its Parameter/Context/Comparison/Permission/Evidence work.
- `SemanticChange.change: str` and dimension strings remain future-open wire data; no codec/schema changes.
- Preserve selected-change field validation/error order, all supported Delta wire versions, count truth tables, fingerprint order, and valid legacy expectation constructors.
- Preserve `UnresolvedCallChange.change`'s narrower added/removed domain unchanged: its count-difference producer family is outside this slice.
- Actual closed decisions use the canonical enum, never string aliases, `.value` comparisons, or copied vocabularies.
- No budget increases, manual baseline edits, additional allowances, or whole-Model/mixed-module string-absence claims.
- Production is limited to `ir/model.py`, `check/delta.py`, `check/expectation.py`; independently authored Target/test/docs/Makefile accompany the feature.

## Review Focus

- Future extension actions must roundtrip through the public codec, but fail the known-action governance ingress with the original error.
- Valid legacy ExpectedSemanticChange constructor strings normalize to the canonical type; invalid known-action inputs do not become declared changes.
- All four actions retain their existing zero/positive cardinality rules and exact selected/change error labels.
- Duplicate semantic fingerprint errors retain plain wire spellings rather than enum reprs.
- Actual source type widening and raw equality/membership/match/alias mutations fail a fixed authored Target/guard without changing the fixture contract.

### Task 1: Pin the actual action boundary and observe RED

**Files:** Create `tests/test_known_delta_action_types.py`; extend `docs/architecture/contracts/ir.json` with a small independent API Target; create the boundary doc.

**Interfaces:** `KnownSemanticChangeKind` owns exactly four tags; `_change(..., kind: KnownSemanticChangeKind, ...) -> SemanticChange`; `ExpectedSemanticChange.change: KnownSemanticChangeKind`; `_require_change_kind(value: object, label: str) -> KnownSemanticChangeKind`; `_validate_change_counts(change: KnownSemanticChangeKind, ...) -> None`.

- [ ] Add behavioral assertions for the missing enum/nominal ingress, real Delta producer outputs, legacy constructor normalization, open codec/future rejection, validation order/counts, and wire/plain error parity.
- [ ] Add authored exact enum/field/parameter/return Target entries against actual source members; guard only the genuinely migrated source projection, since dimensions/schema/cycle vocabularies remain pending.
- [ ] Run hosted native tests before production, confirm semantic/API assertions fail because the nominal contract is missing, and retain the exact run/job.

### Task 2: Implement the existing-owner action boundary

**Files:** Modify the three production files above; add the test to the existing Makefile PR gate.

- [ ] Define the four-value enum beside SemanticChange; keep SemanticChange.change open str.
- [ ] Use nominal actions for `_change` and actual four producer classifications; serialize at the open SemanticChange port and classify consumer actions once before grouping fingerprints.
- [ ] Normalize ExpectedSemanticChange's valid legacy strings once; parse known actions at governance ingress, retain typed identity keys through match/guardrail decisions, and preserve old error text/order.
- [ ] Run the full new native/mutation file and existing Delta/expectation/version/parity/profile regressions; fix source, not golden outputs.

### Task 3: Verify and freeze a separate reviewable increment

- [ ] Run Ruff, strict mypy, hygiene and required relevant gates; measure production line cost and explain its actual responsibility.
- [ ] Observe before/after with the actual engine, compare full selected UNKNOWN records, call AST/targets/reasons/candidate counts/multiplicity, and report actual site deltas rather than aggregate netting.
- [ ] Generate the normal amendment against the exact base using unchanged baseline budgets, commit it, then run committed no-write validation.
- [ ] Freeze a clean intended ref, publish a separate draft PR Part of #542, and provide source/gate/receipt evidence for independent Astra review; Root owns combined full-suite integration and merge.
