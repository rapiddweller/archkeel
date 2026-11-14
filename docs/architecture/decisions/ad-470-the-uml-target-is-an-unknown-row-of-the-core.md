# AD-470 The UML target is an UNKNOWN row of the core

**Status.** Proposed. Part of #880. It replaces the `uml_target` gap of AD-432.

**What 4.0.1 does** (`check/uml.py`, `check/uml_evaluation.py`, `check/uml_compare.py` at tag `4.0.1`).
- The target is `declarations.uml` inside the contract (contract 2.2 or later). It is not a separate file.
  A tree of contracts has one target row: `UML-TARGET-<stable id of the root path>`, kind `uml_target`.
- 4.0.1 compares the declared entities, relationships and scopes with the source facts: kind, parent,
  visibility, signature, annotation, modifiers, existence, relationships and closed-scope completeness.
- A conflict is FAIL (`rule.violated`, exit 2). A fact that is absent, ambiguous or unresolved is
  UNKNOWN (`no_receipt`, exit 0). An empty target is UNKNOWN (`UML-EMPTY`). PASS needs every assessment.
- A target that does not parse or link is `contract.invalid` (exit 2): an unknown kind or schema version,
  a repeated id, an unknown parent or relationship end. A missing provenance file is also `contract.invalid`.
- `fixtures/H-typescript` and `fixtures/H-uml-typescript` give UNKNOWN (9 and 3 undecided assessments).

**Decision.**
1. The core writes the target row as UNKNOWN with a typed cause, `archkeel_model::UmlGap`:
   `Empty`, or `NotCompared` with the counts of entities, relationships and scopes of the tree.
   The row reason is `no_receipt`, as in 4.0.1. The row is not a gap of the frame (`unsupported`).
2. `archkeel_report::Named` carries the row as `uml: Option<(String, UmlGap)>`. `UmlGap` has no
   verdict, so the row cannot PASS and cannot FAIL. It never enters `decisions` and no run proof reads it.
   A row is UNKNOWN, so the run status is UNKNOWN: the CLI gives exit 2.
3. A contract with only a target has one explaining row, so it is not "no decided rule" (AD-416).
4. Without a model the row is a gap with the reason of the run. With a reason for the whole contract
   there is no row. A target id equal to a rule id is refused (`DuplicateRule`).
5. `Unsupported::UmlTarget` and the shell gap kind `uml_target` are deleted.

**Bound input.** The target is in the contract bytes, so `contract_digest` and `contract_files` bind
it. A change after the core read it gives a refusal (exit 2). PR #1144 (contract hygiene) reads
and binds each provenance file that an entity, relationship or scope cites: its
`policy::provenance_paths` covers `declarations.uml`. This record uses that seam and adds no
reader. It does not wait for #1144.

**Proven subset.** Each `contract.invalid` case of 4.0.1 above, except the missing provenance file,
is a contract refusal of the core (`archkeel-contract` already parses and links the target).
No other assessment is proven. No UML PASS exists in the core.

**Named gaps (UNKNOWN in the core).**
- The comparison with the source facts. A conflict that 4.0.1 shows as FAIL is UNKNOWN in the core.
  This is stricter for PASS and less specific for FAIL; both give exit 2.
- A target that 4.0.1 can PASS (`H-uml-dart`, `H-uml` in 4.0.1) is UNKNOWN in the core.
- A missing provenance file: UNKNOWN until #1144 merges, then a refusal.
- The UML facts of the collectors (declarations, members, signatures, calls, references) are not in
  the model. A comparison slice needs them for each language before a row can PASS or FAIL.

**Rejected.** A row in the eval crate: the target is not a rule of `RuleKind`. A PASS for an
assessment subset: a rule PASS needs every assessment. Keep the gap: it hides the row count and
gives the run a named part that is not a missing port of a rule.

**Tests.** `tests/test_cli_core_uml_target.py` (both fixtures through `validate --json` and `report
--output`, 6 wrong targets, an empty target, 5 unparseable targets, a stale target).
`native/report/src/ruling_tests.rs` (`a_uml_target_*`), `native/core/src/contract_tests.rs`,
`native/core/src/engine_tests.rs`, `native/core/src/hostile_tests.rs`, and `fixtures/matrix.json`.
