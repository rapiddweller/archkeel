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
//! 17. A verdict is cloned out of its decision: `Verdict` is not `Clone` (E0599).
//!
//! ```compile_fail,E0599
//! fn copy(decision: &archkeel_model::Decision) -> archkeel_model::Verdict {
//!     decision.verdict().clone()
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
