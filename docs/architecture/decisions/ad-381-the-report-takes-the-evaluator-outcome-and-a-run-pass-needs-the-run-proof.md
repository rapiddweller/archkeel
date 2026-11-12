# AD-381 The report takes the evaluator outcome, and a run PASS needs the run proof

**Status.** Accepted. Epic #880, the report seam of #1073 (items 1, 2, 3, 6, 7, 11). The wiring of
`report` into `core` (items 4 and 5) is a later slice.

**Decision.**
1. Run proof (item 3). `model/src/run.rs` adds `RunComplete<'id>`. Only `Scope::run_complete`
   makes it, with the brand of its scope. It needs `Scope::run` (the one scope state) and a PASS
   of this model for each rule of the contract of the model that is not a permission
   declaration; each given decision must be such a PASS (`RunGap::Scope`, `Rule`, `NotPass`).
   `Scope::pass_run` uses it up and gives `RunPass`, which names the model serial (`RunPass::of`).
2. Zero rules. The reference engine gives PASS for a complete observation without rules
   (`src/archkeel/check/run.py:76-95`). The run proof is the same. An incomplete scope never is.
3. `Scope::run` keeps `Result<(), Reason>`, because the core reads it; `scope.rs` is unchanged.
4. One contract (review B1). `eval::evaluate(model)` has no contract parameter: the rules and
   the sibling rules of `complete_external_scope` come from `model.contract()`. Before, a caller
   contract with one more `external_dependency_scope` rule gave a PASS bound to the model.
5. Rule rows (items 1, 2). `report` uses `eval` (AD-359 point 2). `RuleOutcome` has private
   fields. `RuleOutcome::evaluated(&Outcome, RuleText)` takes the id, the kind and the decision
   from one outcome. `build(outcome, records, Option<&Model>)` checks each PASS row with
   `Decision::passes(model, rule)` (`BuildError::ForeignPass`), because a type cannot stop a
   `Decision` from moving (AD-378 point 6).
6. Declarations (lead decision S1, review F3). A permission declaration (`allowed_dependency`)
   has no verdict (`ir/decisions.py:763`), so the run proof skips it, as Python does. The kind
   comes from the contract of the model, never from a row. A DECLARATION row needs a declaration
   rule of the model: `RuleOutcome::declaration(model, id, text)` is `None` otherwise, and
   `build` refuses such a row (`BuildError::ForeignDeclaration`). So a FAIL rule cannot hide as
   DECLARATION, and a declaration row does not stand in for a missing PASS.
7. Observation and status. `RunOutcome` has no observation: it is PASS only when `Scope::run`
   of the model is `Ok`. A PASS status needs `RunPass` over the decided rows, else
   `BuildError::PassWithoutProof(Option<RunGap>)`. A run without a model has no PASS.
8. Bytes (item 6). The payload type, `encode` and `decode` are private to the crate. Bytes leave
   only through `Report<Decided>::encode`; `Report::read` checks bytes.
9. `WhyUnknown::of(&Reason)` (item 7, `report/src/why.rs`) has no wildcard;
   `clippy::wildcard_enum_match_arm` and `match_wildcard_for_single_variants` are denied there,
   in `report/src/kind.rs` and in `model/src/run.rs`. The order of `ir/decisions.py:770-779` decides: `Cause::NoRuleSubjects`
   (a coverage failure of the run) is `scope_incomplete`; `Reason::NoSubjects`, a dynamic import
   (AD-378: no receipt) and an unported kind are `no_receipt`; `Cause::Undecided` is
   `undecided`. No reason maps to `ownership_blocker` yet.
10. Names (item 11, review F2). The report types `Level`, `Measure`, `Reason`, `Verdict`, `Graph`
    are `NodeLevel`, `MeasureDef`, `FindingReason`, `BudgetVerdict`, `GraphRows`; `code_list!`
    keeps the schema name, so the bytes do not change. A kind word comes from an exhaustive
    match (`report -> contract`), not from a serde fallback.
11. The no-language test reads `report` and its subdirectories, except test files.

**Seam for the wiring slice (review F4).** `core/src/rules.rs` counts `allowed_dependency` as a
decided kind; the run proof skips it. The run proof of the report wins: the wiring slice deletes
`core/src/status.rs` and takes the status only from `Report<Decided>`.

**Reason.** The wiring must not write a PASS without proof. Each PASS of a frame now needs the
model that made it and only its contract: a row its rule PASS, the observation its scope, the
status its run proof.

**Rejected.** `report -> model` only, with a public row constructor that takes a `Decision` and
an id. A changed `Scope::run`. A run PASS as a `Decision`: a `Decision` PASS names a rule. A
DECLARATION row taken from the caller: it could hide a FAIL rule.

**Limit.** `RunPass` is not branded after `pass_run`; `RunPass::of` checks the serial. A run
without a model accepts a DECLARATION row unchecked; it has no PASS. `evaluated` of a row is the
word of the caller, but a PASS row without it is refused. A stable rustdoc ignores the error
code of a `compile_fail` test; `tests/test_native_report.py` runs the barrier with
`RUSTC_BOOTSTRAP=1` so that the codes are checked.

**Tests.** `native/report/src/run_tests.rs`, `build_tests.rs`; `native/eval/src/external_tests.rs`
(`a_sibling_rule_comes_only_from_the_contract_of_the_model`); the doctests 21 to 29 of
`native/model-barrier` and of `native/model/src/run.rs`; `tests/test_native_report.py`;
`tests/test_native_core.py` (`test_the_model_the_evaluator_and_the_core_name_no_language`).
