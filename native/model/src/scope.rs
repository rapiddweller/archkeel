// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The proof that a rule saw the whole domain of its model (AD-363, AD-378).
//!
//! `Model::scope` gives a `Scope` with a brand: a lifetime that only this call has. The proof
//! `ScopeComplete` carries the brand of its model, and `Scope::pass` takes only a proof of the
//! same brand. So a proof cannot be used with another model, cannot outlive its scope, and no
//! other module or crate can make one. A proof is not `Clone`: `pass` uses it up, so one proof
//! gives one PASS.
//!
//! `Scope::complete` makes the proof for one rule of the contract of the model (slice S4). It
//! reads the state of the scope that the model made one time (`proof.rs`), then what only the
//! rule has: its receipt (the rule selects a module of the reply) and its undecided positions (a
//! dynamic import that reaches it). A rule kind whose receipt the model does not know gives no
//! proof (`Unsupported::Rule`): the slice of that kind adds its receipt here.
//!
//! The use that compiles:
//!
//! ```
//! fn decide(model: &archkeel_model::Model, rule: &archkeel_contract::Rule)
//!     -> Option<archkeel_model::Decision> {
//!     model.scope(|scope| scope.complete(rule).ok().map(|proof| scope.pass(proof)))
//! }
//! ```
//!
//! A proof of one model cannot decide a rule of another model:
//!
//! ```compile_fail
//! fn decide(a: &archkeel_model::Model, b: &archkeel_model::Model, rule: &archkeel_contract::Rule) {
//!     a.scope(|a| b.scope(|b| a.complete(rule).ok().map(|proof| b.pass(proof))));
//! }
//! ```
//!
//! A proof cannot leave its scope:
//!
//! ```compile_fail
//! fn keep(model: &archkeel_model::Model, rule: &archkeel_contract::Rule) {
//!     let _proof = model.scope(|scope| scope.complete(rule).ok());
//! }
//! ```
//!
//! A crate outside the model cannot make the proof:
//!
//! ```compile_fail
//! fn forge<'id>() -> archkeel_model::ScopeComplete<'id> {
//!     archkeel_model::ScopeComplete { brand: std::marker::PhantomData }
//! }
//! ```

use std::marker::PhantomData;

use archkeel_contract::{kind_of, Rule};

use crate::causes::{Cause, Part};
use crate::model::Model;
use crate::ownership::in_scope;
use crate::proof::State;
use crate::reason::{Reason, Unsupported};
use crate::verdict::Decision;

/// An invariant lifetime: two calls of `Model::scope` never have the same one.
type Brand<'id> = PhantomData<fn(&'id ()) -> &'id ()>;

/// The proof that the model of the brand `'id` saw the whole scope of one rule of its run.
#[derive(Debug)]
pub struct ScopeComplete<'id> {
    brand: Brand<'id>,
}

/// The model of one `Model::scope` call, with its brand.
#[derive(Debug)]
pub struct Scope<'id, 'm> {
    model: &'m Model,
    _brand: Brand<'id>,
}

impl Model {
    /// Run `check` with the branded scope of this model.
    pub fn scope<R>(&self, check: impl for<'id> FnOnce(Scope<'id, '_>) -> R) -> R {
        check(Scope {
            model: self,
            _brand: PhantomData,
        })
    }
}

impl<'id, 'm> Scope<'id, 'm> {
    /// The model of this scope.
    pub fn model(&self) -> &'m Model {
        self.model
    }

    /// The scope proof of one rule of the contract of this model, or the reason that it has
    /// none. A fact that makes the scope incomplete comes before a part that the core cannot
    /// read: with a fact, the reference engine gives UNKNOWN too.
    pub fn complete(&self, rule: &Rule) -> Result<ScopeComplete<'id>, Reason> {
        if !self.model.contract().rules().contains(rule) {
            return Err(Part::ForeignRule.into());
        }
        let unread = match self.model.scope_state() {
            State::Incomplete(reason) => return Err(reason.clone()),
            State::Unread(part) => Some(part.clone()),
            State::Complete => None,
        };
        receipt(self.model, rule)?;
        if dynamic_import(self.model, rule) {
            return Err(Reason::NotComplete(Cause::DynamicImport));
        }
        match unread {
            Some(part) => Err(part.into()),
            None => Ok(ScopeComplete { brand: PhantomData }),
        }
    }

    /// The scope state of the whole run: `Ok` only when the model has no cause and no unread
    /// part. The status of a frame reads it (lead decision L-35b): a run whose scope is not
    /// complete is never PASS, also with zero rules. It reads the one state that
    /// `complete` reads.
    pub fn run(&self) -> Result<(), Reason> {
        match self.model.scope_state() {
            State::Complete => Ok(()),
            State::Incomplete(reason) => Err(reason.clone()),
            State::Unread(part) => Err(part.clone().into()),
        }
    }

    /// PASS, with a proof of this scope.
    pub fn pass(&self, proof: ScopeComplete<'id>) -> Decision {
        let ScopeComplete { brand: _ } = proof;
        Decision::passed()
    }
}

/// The receipt of a rule (`rules.py` `_rule_evaluation_facts_for_rule`): the rule selects a
/// module of the reply. Only the kinds that the evaluator decides have one here.
fn receipt(model: &Model, rule: &Rule) -> Result<(), Reason> {
    let modules = model.graph().modules();
    let selected = match rule {
        Rule::CompleteAssignment(rule) | Rule::CompleteExternalScope(rule) => {
            !model.source_modules(rule.source().as_text()).is_empty()
        }
        Rule::RootLayout(rule) => modules
            .iter()
            .any(|(_, module)| in_scope(module.name(), rule.root().as_text())),
        Rule::ExternalDependencyScope(_) => !modules.is_empty(),
        // Each kind that no slice decides: its slice states its receipt here (AD-378).
        other @ (Rule::CallOwner(_)
        | Rule::ForbiddenCallArgument(_)
        | Rule::CatalogArgument(_)
        | Rule::CatalogUse(_)
        | Rule::ForbiddenEffectUnderCondition(_)
        | Rule::ForbiddenDependency(_)
        | Rule::AllowedDependency(_)
        | Rule::ForbiddenConstruct(_)
        | Rule::SourceOwnership(_)
        | Rule::CompleteRequires(_)
        | Rule::LayerOrder(_)
        | Rule::NoComponentCycles(_)
        | Rule::InterfaceBoundary(_)
        | Rule::SiblingIsolation(_)
        | Rule::SymbolPlacement(_)
        | Rule::BoundaryTypes(_)
        | Rule::BoundedNumericOperand(_)
        | Rule::ProtocolDeclarations(_)) => {
            return Err(Reason::Unsupported(Unsupported::Rule(kind_of(other))))
        }
    };
    if selected {
        Ok(())
    } else {
        Err(Reason::NoSubjects)
    }
}

/// True when an unresolved dynamic import reaches the rule (`dynamic_dependency_limits`): the
/// reference engine leaves the rule without its receipt. A limit without a source module stops
/// the reference engine, so it reaches each rule.
fn dynamic_import(model: &Model, rule: &Rule) -> bool {
    let reaches = |source: &str| match rule {
        Rule::ExternalDependencyScope(rule) => {
            !(rule
                .exact_sources()
                .iter()
                .any(|exact| exact.as_text() == source)
                || rule
                    .allowed_sources()
                    .iter()
                    .any(|allowed| in_scope(source, allowed.as_text())))
        }
        Rule::CompleteExternalScope(rule) => in_scope(source, rule.source().as_text()),
        // `dynamic_dependency_limits` does not read these kinds.
        Rule::CompleteAssignment(_) | Rule::RootLayout(_) => false,
        // A kind that no slice decides has no receipt; its slice states its limits here. Until
        // then a dynamic import reaches it (fail closed).
        Rule::CallOwner(_)
        | Rule::ForbiddenCallArgument(_)
        | Rule::CatalogArgument(_)
        | Rule::CatalogUse(_)
        | Rule::ForbiddenEffectUnderCondition(_)
        | Rule::ForbiddenDependency(_)
        | Rule::AllowedDependency(_)
        | Rule::ForbiddenConstruct(_)
        | Rule::SourceOwnership(_)
        | Rule::CompleteRequires(_)
        | Rule::LayerOrder(_)
        | Rule::NoComponentCycles(_)
        | Rule::InterfaceBoundary(_)
        | Rule::SiblingIsolation(_)
        | Rule::SymbolPlacement(_)
        | Rule::BoundaryTypes(_)
        | Rule::BoundedNumericOperand(_)
        | Rule::ProtocolDeclarations(_) => true,
    };
    model
        .graph()
        .observed()
        .dynamic_imports
        .iter()
        .any(|source| source.as_deref().is_none_or(reaches))
}
