# AD-416: The core names an empty contract and the product keeps its result

Date: 2026-11-13
Status: accepted
Owner: architecture lead
Issues: #1110, #1096, duplicate-rule-id item of #1099; part of #880

## Context

Python gives PASS and exit 0 for two complete zero-rule corpus cases.
The core also writes PASS, but the stage-1 shell refuses that frame with exit 2.
The statement in #1110 that Python exits 2 is incorrect. An issue comment corrects it.
A later reader must not accept a core PASS without a rule.

## Decision

1. Keep one zero-rule policy beside the frame maker in `native/report/src/ruling.rs`.
   The ruling constructor names `Unsupported::NoRules` before it folds the run status.
   It gives UNKNOWN, no PASS proof, and the reason `unsupported: contract has no rules`.
   `Ruling::frame` is the only maker of frame bytes. It cannot write an empty PASS.
   No request kind owns another zero-rule policy: report, check and scan share the ruling.
2. Keep the shipped Python result unchanged. The shell uses its existing fall-back path
   when the frame names this unsupported outcome. No decision compares reason strings.
   Switch off and switch on then give the same product verdict and exit code.
3. Refuse repeated outcome ids before map insertion, with `BuildError::DuplicateRule`.
   This includes unsupported and declaration outcomes. No last row can replace an earlier row.
   The shell keeps its repeated-JSON-key refusal. A hostile duplicate frame gives exit 2.
4. Keep `Decision`, scope proofs and the run proof unchanged. An unsupported contract does
   not weaken a rule, turn UNKNOWN into PASS, or make an evaluator receipt.

## Product boundary and measurement

The 655-case dual-run corpus has 35 explicit empty rule arrays.
Thirteen cases also have an implicit UML rule. Twenty-two cases have no effective rule.
The real CLI with the switch off gives UNKNOWN in 20 of these cases and PASS in two:
`golden/typescript-excalidraw-laser-pointer` and `s4/a-contract-without-rules-passes`.
An invalid contract without a rule array is not counted as an empty contract.
Changing Python to UNKNOWN is a separate breaking product decision for the owner.
It would change these two current PASS results, not all 35 empty arrays.

## Rejected alternatives and limit

- Keep core PASS and relax the reader: a later reader could accept a vacuous PASS.
- Change Python to UNKNOWN here: this changes the shipped product without the owner's decision.
- Detect an empty contract in each command: this duplicates policy and can split the answers again.

The core does not decide an empty contract. Stage 2 must keep this named unsupported outcome;
it cannot present it as a core PASS. Stage 1 can still show Python's established result.

## Checks

Rust frame tests require UNKNOWN, a named reason and no PASS proof for an empty contract.
Repeated supported and unsupported outcomes must give the typed duplicate-id error.
Real CLI tests compare both zero-rule corpus reports and a zero-rule check, switch off and on.
Removing the zero-rule refusal makes these tests fail with on exit 2 versus off exit 0.
The shell tests refuse a duplicate rule id and a hostile zero-rule PASS frame.
The dual-run comparison must keep zero differences against the unchanged Python oracles.
