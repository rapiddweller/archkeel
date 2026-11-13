# AD-408 Forbidden construct evaluation keeps the fact boundary closed

**Status.** Proposed. Epic #880, slice S11. Implementation is stopped at the missing-facts boundary.

**Decision.** Keep the named `forbidden_construct` fallback until the lead decides the fact change.
Do not extend the fact schema, store acceptance or collectors in this evaluator slice without that decision.
Do not infer absence from an empty inventory or replace an unrecognized fact with a recognized kind.
No production behavior changes in this record.

**Reason.** Three required fact kinds are absent from `ConstructFact` in `native/facts/src/sections.rs:136`:
`assert_statement`, `placeholder_body` and `dunder_dict`.
The Python collector emits them in `analyzer/python/constructs.py:1422`, `:1438` and `:1554`.
The frozen `tests/golden/python/synthetic-constructs.json.gz` reply contains all three.
Decoding each record as a typed `Section` refuses it with
`the kind <kind> is not a kind of ConstructFact`.
The store decodes this type before validation (`native/store/src/decode.rs:29`).
Adding those variants changes the typed fact schema, which is stop point (i) of this slice.

The root contract tree has 72 rules of this kind. Three rules require these missing fact kinds:
the assertion rule, the placeholder rule and the dynamic-construct rule with `dunder_dict`.
The other 69 rules comprise one broad-exception rule, one annotation rule and 67 string-comparison rules.
The parser already holds all contract options (`native/contract/src/construct.rs:17`).
Contract parsing alone cannot supply the missing observations.

**Existing limits.** The store refuses Python and Dart replies (`native/store/src/validate.rs:117`).
It also refuses protocol 10 (`:107`). This slice does not remove either refusal.
The Rust collector declares no construct capability (`native/rust/src/reply.rs:83`).
The TypeScript collector gives only partial string-comparison evidence; empty observations cannot prove absence (`docs/rules.md:285`).
These limits are separate from the missing typed fact kinds.

**Measurement.** The 655-case dual-run corpus contains 1 506 rules of this kind in 254 cases.
The recorded Python verdicts are 1 407 PASS, 34 FAIL and 65 UNKNOWN.
The PR lists the option combinations. Counts join oracle rule ids to the fixture contracts and their overlays.
No rule is ported in this stopped slice. All 72 root rules retain the existing named fallback.
No Python source, Rust source, PASS proof, API pin or expected-gap pin changes.

**Rejected.** Add fact kinds silently: this exceeds the stated boundary.
Treat an absent kind as an empty inventory: a known forbidden occurrence could become PASS.
Make the store accept Python replies: the independent collector acceptance condition remains open (AD-389).

**Limit.** This record does not claim evaluator parity, fault injection or a green implementation gate.
Those checks require an implementation after the lead resolves stop point (i).
No Python false PASS was established by this measurement.

**Checks.** Decode the three frozen records through `archkeel_facts::Section` with Rust 1.97.0.
Check that each refusal names its original kind. Count all oracle rule ids before grouping options.
The existing reference and repository-hygiene tests check the decision links and repository rules.
