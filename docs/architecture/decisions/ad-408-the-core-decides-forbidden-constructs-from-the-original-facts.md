# AD-408 The core decides forbidden constructs from the original facts

**Status.** Proposed. Epic #880, slice S11. Lead decision L-87 authorizes the decoder correction.

**Decision.** The core decides `forbidden_construct` from the original construct and typing-signal records.
The model holds the occurrence inventory, actual symbol owners and construct capabilities.
One matcher serves the evaluator and the receipt proof. Exemptions retain their exact or prefix meaning.
Exact type-ignore allowances bind the qualified name, line, statement and tag.
Nominal selectors match the receiver, role, member and literal from the facts.
An unknown identity or an empty selected inventory cannot prove absence.
A known occurrence gives FAIL before coverage is checked.
Otherwise PASS requires the existing `Scope::complete` proof and the matching receipt.
Partial capabilities, a missing subject or a gap give UNKNOWN with a reason.

**Decoder correction.** Three required fact kinds were absent from `ConstructFact`:
`assert_statement`, `placeholder_body` and `dunder_dict`.
The Python collector emits them in `analyzer/python/constructs.py:1422`, `:1438` and `:1554`.
The frozen `tests/golden/python/synthetic-constructs.json.gz` reply contains all three.
L-87 permits these variants because the wire and the frozen replies already contain them.
Their closed data types reject missing and unknown fields. Placeholder forms are `empty` and `not_implemented`.
The golden test also found the missing selector role `reflect`; the decoder now includes it and `match`.
No collector or wire format changes. No fourth record kind was missing.
The generated facts schema is corrected from these types; the protocol and every emitted reply stay unchanged.
The store retains its generic evidence and owner checks (`store/src/records.rs:181`, `bindings.rs:103`).

**Reason.** The root contract tree has 72 rules of this kind.
All combinations are in the evaluator: three need the corrected decoder variants.
The parser already holds all options (`native/contract/src/construct.rs:17`); no new contract syntax is needed.

**Existing limits.** The store refuses Python and Dart replies (`native/store/src/validate.rs:117`).
It also refuses protocol 10 (`:107`). This slice does not remove either refusal.
The Rust collector declares no construct capability (`native/rust/src/reply.rs:83`).
The TypeScript collector gives only partial string-comparison evidence; empty observations cannot prove absence (`docs/rules.md:285`).
These limits are separate from the missing typed fact kinds.

**Measurement.** The 655-case dual-run corpus contains 1 506 rules of this kind in 254 cases.
The recorded Python verdicts are 1 407 PASS, 34 FAIL and 65 UNKNOWN.
The PR lists the option combinations. Counts join oracle rule ids to the fixture contracts and their overlays.
Of these, 1 503 use the Python profile, one Dart and two TypeScript. None uses the Rust profile.
Only the two TypeScript replies can pass the current store profile boundary.
One uses a configured collector, so the stage-one shell still falls back there.
Recorded-input unit tests enter below the store only under `cfg(test)`; the binary has no such entry.

**Rejected.** Infer absence from an unsupported or partial inventory: that can create a false PASS.
Remove the store refusal to increase the end-to-end count: collector acceptance remains separate (AD-389).
Give the core another trust entry: the shell trust and `Ruling::frame` stay unchanged.

**Limit.** Python replies still fall back, even when this evaluator can decide their rule combinations.
The PR separates end-to-end parity from recorded-input and synthetic proof tests.
The matcher has a bounded work count; exhaustion is a named UNKNOWN, never PASS.

**Tests.** `facts/src/construct_golden_tests.rs` decodes all construct and typing-signal records in every golden reply.
`model/src/construct_tests.rs` checks the scope proof, exemptions and selector roles without opening a production input path.
`eval/src/construct_tests.rs` checks partial evidence, FAIL before a gap and the absence of vacuous PASS.
