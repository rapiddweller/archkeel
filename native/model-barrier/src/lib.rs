// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-model-barrier: the type barrier of the scope proof, seen from another crate
//! (slice S4, AD-363, AD-378). The crate has no code: each document test below is one attempt.
//!
//! A crate outside `archkeel-model` must not build a PASS `Decision` without a `ScopeComplete`
//! of the same model and the same `Model::scope` call. Each attempt is a `compile_fail` test.
//! A stable `rustdoc` does not check the error code of a `compile_fail` test, so each attempt
//! has a twin that compiles: the same code with the legal call in place of the forbidden one.
//! A twin shows that the attempt fails for the barrier, and not for a typo.
//!
//! # The twin of each attempt
//!
//! ```
//! use archkeel_contract::Rule;
//! use archkeel_model::{Decision, Model, Reason, Verdict};
//!
//! // 1, 2: a decision comes from its constructors.
//! fn fail() -> Decision { Decision::fail() }
//! fn unknown(reason: Reason) -> Decision { Decision::unknown(reason) }
//! // 3: a verdict without the mark of the proof.
//! fn verdict() -> Verdict { Verdict::Fail }
//! // 4, 5, 8, 11, 12: one proof of the scope, used one time in the same scope.
//! fn pass(model: &Model, rule: &Rule) -> Option<Decision> {
//!     model.scope(|scope| scope.complete(rule).ok().map(|proof| scope.pass(proof)))
//! }
//! // 6, 7: two scopes, each proof in its own scope.
//! fn two(a: &Model, b: &Model, rule: &Rule) -> Option<Decision> {
//!     a.scope(|a| b.scope(|b| {
//!         let first = a.complete(rule).ok().map(|proof| a.pass(proof));
//!         b.complete(rule).ok().map(|proof| b.pass(proof)).or(first)
//!     }))
//! }
//! // 9: the decision leaves the scope through a capture.
//! fn keep(model: &Model, rule: &Rule) -> Option<Decision> {
//!     let mut kept = None;
//!     model.scope(|scope| kept = scope.complete(rule).ok().map(|proof| scope.pass(proof)));
//!     kept
//! }
//! // 10, 16, 17: the verdict of a decision is read by reference.
//! fn read(decision: &Decision) -> &Verdict { decision.verdict() }
//! fn passed(decision: &Decision) -> bool { matches!(decision.verdict(), Verdict::Pass(_)) }
//! // 18: the sides of a dependency rule come from the model (slice S5, AD-380).
//! fn sides<'c>(
//!     rule: &'c archkeel_contract::ForbiddenDependency,
//!     components: &'c [archkeel_contract::Component],
//! ) -> [archkeel_model::Selection<'c>; 2] {
//!     archkeel_model::dependency_sides(rule, components)
//! }
//! // 19: a judgement of an import is compared, never used as a decision.
//! fn judged(found: archkeel_model::Judged) -> bool { found == archkeel_model::Judged::Pass }
//! // 20: the contract source comes from its bytes.
//! fn sourced() -> archkeel_model::Settings {
//!     archkeel_model::Settings::default().with_contract_source("a.json", b"{}")
//! }
//! ```
//!
//! # The attempts
//!
//! 1. A decision literal: the fields of `Decision` are private.
//!
//! ```compile_fail
//! fn forge() -> archkeel_model::Decision {
//!     archkeel_model::Decision { verdict: archkeel_model::Verdict::Fail, reason: None }
//! }
//! ```
//!
//! 2. The constructor of a PASS: `Decision::passed` is private to the model.
//!
//! ```compile_fail
//! fn forge() -> archkeel_model::Decision { archkeel_model::Decision::passed() }
//! ```
//!
//! 3. A PASS verdict: the mark `Proven` has a private field.
//!
//! ```compile_fail
//! fn forge() -> archkeel_model::Verdict {
//!     archkeel_model::Verdict::Pass(archkeel_model::Proven { _scope: () })
//! }
//! ```
//!
//! 4. A proof literal: the brand of `ScopeComplete` is private.
//!
//! ```compile_fail
//! fn forge<'id>() -> archkeel_model::ScopeComplete<'id> {
//!     archkeel_model::ScopeComplete { brand: std::marker::PhantomData }
//! }
//! ```
//!
//! 5. A scope literal: only `Model::scope` makes a scope.
//!
//! ```compile_fail
//! fn forge(model: &archkeel_model::Model) -> archkeel_model::Decision {
//!     let scope = archkeel_model::Scope { model, _brand: std::marker::PhantomData };
//!     scope.pass(scope.complete(&model.contract().rules()[0]).ok().unwrap())
//! }
//! ```
//!
//! 6. A proof of one model passes a rule of another model.
//!
//! ```compile_fail
//! use archkeel_contract::Rule;
//! use archkeel_model::{Decision, Model};
//! fn two(a: &Model, b: &Model, rule: &Rule) -> Option<Decision> {
//!     a.scope(|a| b.scope(|b| a.complete(rule).ok().map(|proof| b.pass(proof))))
//! }
//! ```
//!
//! 7. A proof of one scope passes in a second scope of the same model.
//!
//! ```compile_fail
//! use archkeel_contract::Rule;
//! use archkeel_model::{Decision, Model};
//! fn twice(model: &Model, rule: &Rule) -> Option<Decision> {
//!     model.scope(|a| model.scope(|b| a.complete(rule).ok().map(|proof| b.pass(proof))))
//! }
//! ```
//!
//! 8. A proof leaves its scope as the return value.
//!
//! ```compile_fail
//! use archkeel_contract::Rule;
//! use archkeel_model::Model;
//! fn keep(model: &Model, rule: &Rule) {
//!     let proof = model.scope(|scope| scope.complete(rule).ok());
//!     drop(proof);
//! }
//! ```
//!
//! 9. A proof leaves its scope through a capture.
//!
//! ```compile_fail
//! use archkeel_contract::Rule;
//! use archkeel_model::Model;
//! fn keep(model: &Model, rule: &Rule) {
//!     let mut kept = None;
//!     model.scope(|scope| kept = scope.complete(rule).ok());
//!     drop(kept);
//! }
//! ```
//!
//! 10. A proof is cloned to pass two rules: `ScopeComplete` is not `Clone`.
//!
//! ```compile_fail
//! use archkeel_contract::Rule;
//! use archkeel_model::{Decision, Model};
//! fn two(model: &Model, rule: &Rule) -> Option<(Decision, Decision)> {
//!     model.scope(|scope| scope.complete(rule).ok().map(|proof| {
//!         (scope.pass(proof.clone()), scope.pass(proof))
//!     }))
//! }
//! ```
//!
//! 11. A proof is used two times: `pass` moves it.
//!
//! ```compile_fail
//! use archkeel_contract::Rule;
//! use archkeel_model::{Decision, Model};
//! fn two(model: &Model, rule: &Rule) -> Option<(Decision, Decision)> {
//!     model.scope(|scope| scope.complete(rule).ok().map(|proof| {
//!         let first = scope.pass(proof);
//!         (first, scope.pass(proof))
//!     }))
//! }
//! ```
//!
//! 12. A scope with a fixed brand: `Model::scope` takes only a closure for each brand.
//!
//! ```compile_fail
//! use archkeel_contract::Rule;
//! use archkeel_model::{Decision, Model, Scope};
//! fn fixed(model: &Model, rule: &Rule) -> Option<Decision> {
//!     model.scope(|scope: Scope<'static, '_>| {
//!         scope.complete(rule).ok().map(|proof| scope.pass(proof))
//!     })
//! }
//! ```
//!
//! 13. A default proof: `ScopeComplete` has no `Default`.
//!
//! ```compile_fail
//! fn forge<'id>() -> archkeel_model::ScopeComplete<'id> { Default::default() }
//! ```
//!
//! 14. A decision from a verdict: no conversion builds a `Decision`.
//!
//! ```compile_fail
//! fn forge(verdict: archkeel_model::Verdict) -> archkeel_model::Decision {
//!     archkeel_model::Decision::from(verdict)
//! }
//! ```
//!
//! 15. A model literal with a scope state of its own: the fields of `Model` are private.
//!
//! ```compile_fail
//! fn forge(graph: archkeel_model::Graph) -> archkeel_model::Model {
//!     archkeel_model::Model { graph }
//! }
//! ```
//!
//! 16. The mark of a PASS is copied into a new verdict: `Proven` is not `Copy` (E0507).
//!
//! ```compile_fail,E0507
//! use archkeel_model::{Decision, Verdict};
//! fn copy(decision: &Decision) -> Option<Verdict> {
//!     match decision.verdict() {
//!         Verdict::Pass(mark) => Some(Verdict::Pass(*mark)),
//!         _ => None,
//!     }
//! }
//! ```
//!
//! 17. A verdict is cloned out of its decision: `Verdict` is not `Clone` (E0308).
//!
//! ```compile_fail,E0308
//! fn copy(decision: &archkeel_model::Decision) -> archkeel_model::Verdict {
//!     decision.verdict().clone()
//! }
//! ```
//!
//! 18. A selection literal: a side of a dependency rule comes only from `dependency_sides`.
//!
//! ```compile_fail
//! fn forge<'c>() -> archkeel_model::Selection<'c> {
//!     archkeel_model::Selection { packages: Vec::new(), exact: Vec::new() }
//! }
//! ```
//!
//! 19. A judgement as a decision: an import that a matcher accepts is no PASS of its rule.
//!
//! ```compile_fail
//! fn forge() -> archkeel_model::Decision { archkeel_model::Judged::Pass }
//! ```
//!
//! 20. A contract source without its bytes: the evidence and the digest are private. The bytes
//!     are bound to the parsed contract by their digest; the path is not bound, it sets only
//!     the evidence id of a `layer_order` row.
//!
//! ```compile_fail
//! fn forge() -> archkeel_model::Settings {
//!     archkeel_model::Settings { contract_source: None, ..Default::default() }
//! }
//! ```
//!
//! # The run proof and the report (AD-381)
//!
//! A run PASS needs the run proof of its own scope (L-35b), and a report holds a PASS only from
//! an `Outcome` of the evaluator. The twin of each attempt below:
//!
//! ```
//! use archkeel_eval::Outcome;
//! use archkeel_model::{Decision, Model, RunPass};
//! use archkeel_report::{Decided, Report, RuleOutcome, RuleText};
//! // 21, 22, 23: the run proof of one scope, used in the same scope.
//! fn run(model: &Model, decisions: &[Decision]) -> Option<RunPass> {
//!     model.scope(|scope| scope.run_complete(decisions).ok().map(|proof| scope.pass_run(proof)))
//! }
//! // 24: a run PASS is read and checked against its model.
//! fn of(pass: &RunPass, model: &Model) -> bool { pass.of(model) }
//! // 25, 26: a rule row from an outcome of the evaluator.
//! fn row(outcome: &Outcome, text: RuleText) -> RuleOutcome { RuleOutcome::evaluated(outcome, text) }
//! // 27, 28: bytes come from a decided report.
//! fn bytes(report: &Report<Decided>) -> Option<Vec<u8>> { report.encode().ok() }
//! // 29: the evaluator reads the contract of the model.
//! fn outcomes(model: &Model) -> Vec<Outcome> { archkeel_eval::evaluate(model) }
//! ```
//!
//! 21. A run proof literal: the brand of `RunComplete` is private (E0451).
//!
//! ```compile_fail,E0451
//! fn forge<'id>() -> archkeel_model::RunComplete<'id> {
//!     archkeel_model::RunComplete { brand: std::marker::PhantomData }
//! }
//! ```
//!
//! 22. The scope proof of rule A as the run proof: `pass_run` takes only a `RunComplete` (E0308).
//!
//! ```compile_fail,E0308
//! use archkeel_contract::Rule;
//! use archkeel_model::{Model, RunPass};
//! fn run(model: &Model, rule: &Rule) -> Option<RunPass> {
//!     model.scope(|scope| scope.complete(rule).ok().map(|proof| scope.pass_run(proof)))
//! }
//! ```
//!
//! 23. The run proof of one model passes the run of another model: `pass_run` takes only a
//!     `RunComplete` with the `Scope` brand of its own scope, and each `Model::scope` call has
//!     its own brand (E0521).
//!
//! ```compile_fail,E0521
//! use archkeel_model::{Decision, Model, RunPass};
//! fn two(a: &Model, b: &Model, decisions: &[Decision]) -> Option<RunPass> {
//!     a.scope(|a| b.scope(|b| a.run_complete(decisions).ok().map(|proof| b.pass_run(proof))))
//! }
//! ```
//!
//! 24. A run PASS literal: the serial of `RunPass` is private (E0451).
//!
//! ```compile_fail,E0451
//! fn forge() -> archkeel_model::RunPass { archkeel_model::RunPass { serial: 0 } }
//! ```
//!
//! 25. A report rule row from a bare PASS `Decision`: `evaluated` takes an `Outcome` (E0308).
//!
//! ```compile_fail,E0308
//! use archkeel_model::Decision;
//! use archkeel_report::{RuleOutcome, RuleText};
//! fn row(pass: &Decision, text: RuleText) -> RuleOutcome { RuleOutcome::evaluated(pass, text) }
//! ```
//!
//! 26. A report rule row literal: its id and decision are private (E0451).
//!
//! ```compile_fail,E0451
//! fn row(kind: String, text: archkeel_report::RuleText) -> archkeel_report::RuleOutcome {
//!     archkeel_report::RuleOutcome {
//!         id: "B".into(), kind, title: text.title, decision: todo!(), evaluated: true,
//!         why_unknown: None, undecided: text.undecided, rationale: text.rationale,
//!         decided_by: text.decided_by,
//!     }
//! }
//! ```
//!
//! 27. Payload bytes without `Report`: the payload type is private to the report (E0433).
//!
//! ```compile_fail,E0433
//! fn bytes(text: &[u8]) -> Vec<u8> {
//!     archkeel_report::Payload::decode(text).ok().and_then(|p| p.encode().ok()).unwrap_or_default()
//! }
//! ```
//!
//! 28. The bytes of a recorded report: only a decided report has `encode` (E0599).
//!
//! ```compile_fail,E0599
//! use archkeel_report::{Recorded, Report};
//! fn bytes(report: &Report<Recorded>) -> Option<Vec<u8>> { report.encode().ok() }
//! ```
//!
//! 29. The rules of another contract next to a model: `evaluate` reads only the contract of
//!     the model, so a sibling rule of the caller cannot change a verdict (E0061).
//!
//! ```compile_fail,E0061
//! use archkeel_contract::Contract;
//! use archkeel_model::Model;
//! fn forge(other: &Contract, model: &Model) -> Vec<archkeel_eval::Outcome> {
//!     archkeel_eval::evaluate(other, model)
//! }
//! ```
//!
//! # Closed by a checked identity, not by type
//!
//! A PASS of one model given as the decision of another model, and a PASS of rule A given as
//! the decision of rule B, compile: a value can move. Each PASS names its rule and the serial of
//! its model, and `Decision::passes` checks both; the evaluator and the core turn a PASS that
//! fails the check into a named gap (AD-378).
//!
//! ```
//! use archkeel_contract::{head_of, Rule};
//! use archkeel_model::{Decision, Model};
//! fn moved(a: &Model, b: &Model, rule: &Rule, other: &Rule) -> Option<(bool, bool)> {
//!     let decision: Decision = a.scope(|s| s.complete(rule).ok().map(|proof| s.pass(proof)))?;
//!     let for_b = decision.passes(b, head_of(rule).id().as_text());
//!     let for_other = decision.passes(a, head_of(other).id().as_text());
//!     Some((for_b, for_other))
//! }
//! ```

#![deny(unreachable_pub)]
