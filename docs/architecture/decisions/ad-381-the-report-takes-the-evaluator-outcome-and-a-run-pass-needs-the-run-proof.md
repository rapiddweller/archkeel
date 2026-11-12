# AD-381 The report takes the evaluator outcome, and a run PASS needs the run proof

**Status.** Accepted. Epic #880, the report seam of #1073 (items 1, 2, 3, 6, 7, 11). The wiring of
`report` into `core` (items 4 and 5) is a later slice.

**Decision.**
1. Run proof (item 3). `model/src/run.rs` adds `RunComplete<'id>`. Only `Scope::run_complete`
   makes it, with the brand of its scope, so it cannot leave the scope or pass another model.
   It needs `Scope::run` (the one scope state) and a PASS of this model for each rule of the
   contract, and each given decision must be such a PASS (`RunGap::Scope`, `Rule`, `NotPass`).
   `Scope::pass_run` uses it up and gives `RunPass`, which names the model serial (`RunPass::of`).
2. Zero rules. The reference engine gives PASS for a complete observation without rules
   (`src/archkeel/check/run.py:76-95`: no violation, no unknown position, no UNKNOWN rule). The
   run proof is the same: a complete scope and no rule give PASS. An incomplete scope never does.
3. `Scope::run` keeps its answer `Result<(), Reason>`: `core/src/rules.rs` reads it, and the core
   is out of scope here. The proof maker is a second method in a new file; `scope.rs` is unchanged.
4. Rule rows (items 1, 2). `report` uses `eval` (AD-359 point 2). `RuleOutcome` has private
   fields. `RuleOutcome::evaluated(&Outcome, RuleText)` takes the id, the kind and the decision
   from one outcome; `RuleOutcome::declaration` holds no decision. `build(outcome, records,
   Option<&Model>)` checks each PASS row with `Decision::passes(model, rule)`; a PASS of another
   rule or model, or a PASS without a model, is `BuildError::ForeignPass`. The check stays
   because a type cannot stop a `Decision` from moving (AD-378 point 6).
5. Observation and status. `RunOutcome` has no observation. The observation is PASS only when
   `Scope::run` of the model is `Ok`. A PASS status needs `RunPass` from the model over the
   decided rules, else `BuildError::PassWithoutProof(Option<RunGap>)`. A declaration row gives
   no decision, so a contract rule that is a declaration blocks the run PASS (stricter).
6. Bytes (item 6). The payload type, its fields, `encode` and `decode` are private to the crate.
   Bytes leave only through `Report<Decided>::encode`; `Report::read` checks bytes.
7. `WhyUnknown::of(&Reason)` (item 7) maps each reason with no wildcard (`report/src/why.rs`):
   a dynamic import is `undecided`; no receipt (a kind or inside rule not ported, no subjects, an
   uncited child) is `no_receipt`; each other reason is `scope_incomplete`. No reason maps to
   `ownership_blocker` yet.
8. Names (item 11). `Level`, `Measure`, `Reason`, `Verdict` and `Graph` of the report are now
   `NodeLevel`, `MeasureDef`, `FindingReason`, `BudgetVerdict` and `GraphRows`. `code_list!`
   keeps the schema name (`as "Level"`), so the wire bytes and the code lists do not change.
9. The no-language test reads `report` and each subdirectory; test files and `test_support.rs`
   name oracle files and are out of it.

**Reason.** The wiring must not be able to write a PASS without proof. Each PASS of a frame now
needs the model that made it: a row its rule PASS, the observation its scope, the status its
run proof.

**Rejected.**
- `report -> model` only, with a public row constructor that takes a `Decision` and an id.
  `eval` already pairs them, and AD-359 names `report -> eval`.
- A changed `Scope::run`. The core would have to change, and the core is in parallel work.
- A run PASS as a `Decision`. A `Decision` PASS names a rule; a run has no rule.

**Limit.** A `RunPass` is not branded after `pass_run`; `RunPass::of` checks the serial. The
report tests copy the reply fixture of `eval`. `evaluated` of a row is the word of the caller,
but a PASS row without it is refused.

**Tests.** `native/report/src/run_tests.rs`, `build_tests.rs`; the doctests 21 to 28 of
`native/model-barrier` and of `native/model/src/run.rs`; `tests/test_native_report.py`;
`tests/test_native_core.py` (`test_the_model_the_evaluator_and_the_core_name_no_language`).
