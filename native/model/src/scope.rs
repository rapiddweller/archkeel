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

use archkeel_contract::{head_of, kind_of, CycleLevel, Rule};

use crate::causes::{Cause, Held, Part};
use crate::coverage::Incomplete;
use crate::direction;
use crate::model::Model;
use crate::ownership::{in_scope, owner_of};
use crate::proof::State;
use crate::reason::{Reason, Unsupported};
use crate::receipts;
use crate::selection;
use crate::verdict::Decision;

/// An invariant lifetime: two calls of `Model::scope` never have the same one.
pub(crate) type Brand<'id> = PhantomData<fn(&'id ()) -> &'id ()>;

/// The proof that the model of the brand `'id` saw the whole scope of one rule of its run.
#[derive(Debug)]
pub struct ScopeComplete<'id> {
    brand: Brand<'id>,
    rule: String,
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
            State::Incomplete(reason) => return Err(rescued(rule, reason)),
            State::Unread(part) => Some(part.clone()),
            State::Complete => None,
        };
        // Slice S7 (AD-384): a kept pair gap holds only the rules whose reading it can change.
        let gaps = self.gaps(rule).map_err(|reason| rescued(rule, &reason))?;
        // The doubt sources of the rule come before its receipt, so each kind states them.
        if dynamic_import(self.model, rule) {
            return Err(Reason::NotComplete(Cause::DynamicImport));
        }
        match rule {
            Rule::NoComponentCycles(cycle) => receipts::cycle(self.model, cycle, self.scan())?,
            Rule::CompleteRequires(_) => {
                receipt(self.model, rule)?;
                receipts::requires(self.model, self.scan())?;
            }
            _ => receipt(self.model, rule)?,
        }
        gaps.spent();
        match unread {
            Some(part) => Err(part.into()),
            None => Ok(ScopeComplete {
                brand: PhantomData,
                rule: head_of(rule).id().as_text().to_owned(),
            }),
        }
    }

    /// The scope state of the whole run: `Ok` only when the model has no cause and no unread
    /// part. The status of a frame reads it (lead decision L-35b): a run whose scope is not
    /// complete is never PASS, also with zero rules. It reads the one state that
    /// `complete` reads.
    ///
    /// Slice S7 (AD-384): each kept pair gap holds the run, and a gap that the drop rule drops
    /// for one profile is a named part of the run.
    pub fn run(&self) -> Result<(), Reason> {
        let pairs = self.model.pairs();
        let kept = pairs
            .kept
            .iter()
            .map(|gap| (gap.source.as_str(), gap.target.as_str()));
        if let State::Incomplete(reason) = self.model.scope_state() {
            return Err(reason.clone());
        }
        if let Some(held) = Held::of(kept) {
            return Err(Reason::NotComplete(Cause::PairGaps(held)));
        }
        match self.model.scope_state() {
            State::Unread(part) => Err(part.clone().into()),
            _ if pairs.allowed => Err(Part::AllowedPairGap.into()),
            _ => Ok(()),
        }
    }

    /// PASS, with a proof of this scope.
    /// The PASS names the rule of the proof and the serial of the model.
    pub fn pass(&self, proof: ScopeComplete<'id>) -> Decision {
        let ScopeComplete { brand: _, rule } = proof;
        Decision::passed(rule, self.model.serial())
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
        // Slice S5 (AD-380), `_rule_evaluation_facts_for_rule`.
        // An undecided position (`symbol_limits`) withholds the receipt as well.
        Rule::ForbiddenDependency(rule) => {
            let judged = direction::forbidden(model, rule)
                .into_iter()
                .map(|(_, j)| j);
            undecided(direction::undecided(judged))?;
            let [sources, _] = selection::dependency_sides(rule, model.contract().components());
            modules
                .iter()
                .any(|(_, module)| sources.matches(module.name()))
        }
        Rule::SiblingIsolation(rule) => modules.iter().any(|(_, module)| {
            rule.members()
                .iter()
                .any(|member| in_scope(module.name(), member.as_text()))
        }),
        // `_layer_order_evaluation_facts`: the selected components; the receipt cites the
        // contract file (`_layer_order_evidence`). The layer gaps are a cause of the state.
        Rule::LayerOrder(rule) => {
            let digest = model.contract().digest().as_text();
            if model.graph().settings().contract_evidence(digest).is_none() {
                return Err(Part::ContractSource.into());
            }
            !selection::layer_components(model.contract(), rule).is_empty()
        }
        // `scope_receipts_complete` reads the scan roots: `receipts::requires` (slice S7).
        Rule::CompleteRequires(rule) => {
            let judged = direction::crossings(model, rule)
                .into_iter()
                .map(|c| c.judged);
            undecided(direction::undecided(judged))?;
            true
        }
        // Each kind that no slice decides: its slice states its receipt here (AD-378). A
        // permission declaration (`allowed_dependency`) has no verdict, so it has no receipt.
        other @ (Rule::CallOwner(_)
        | Rule::ForbiddenCallArgument(_)
        | Rule::CatalogArgument(_)
        | Rule::CatalogUse(_)
        | Rule::ForbiddenEffectUnderCondition(_)
        | Rule::AllowedDependency(_)
        | Rule::ForbiddenConstruct(_)
        | Rule::SourceOwnership(_)
        | Rule::NoComponentCycles(_)
        | Rule::InterfaceBoundary(_)
        | Rule::SymbolPlacement(_)
        | Rule::BoundaryTypes(_)
        | Rule::BoundedNumericOperand(_)
        | Rule::ProtocolDeclarations(_)) => {
            // `receipts::cycle` gives the receipt of `no_component_cycles` (slice S7).
            return Err(Reason::Unsupported(Unsupported::Rule(kind_of(other))));
        }
    };
    if selected {
        Ok(())
    } else {
        Err(Reason::NoSubjects)
    }
}

/// An undecided position is a fact: the reference engine gives UNKNOWN (`_rule_status`).
fn undecided(count: usize) -> Result<(), Reason> {
    if count > 0 {
        Err(Reason::NotComplete(Cause::Undecided(count)))
    } else {
        Ok(())
    }
}

/// True when an unresolved dynamic import reaches the rule (`dynamic_dependency_limits`): the
/// reference engine leaves the rule without its receipt. A limit without a source module stops
/// the reference engine, so it reaches each rule.
fn dynamic_import(model: &Model, rule: &Rule) -> bool {
    let reaches = |source: Source<'_>| match rule {
        Rule::ExternalDependencyScope(rule) => {
            !(rule
                .exact_sources()
                .iter()
                .any(|exact| exact.as_text() == source.module)
                || rule
                    .allowed_sources()
                    .iter()
                    .any(|allowed| in_scope(source.module, allowed.as_text())))
        }
        Rule::CompleteExternalScope(rule) => in_scope(source.module, rule.source().as_text()),
        // Slice S5 (AD-380): a rule that leaves out type-only imports does not see a type-only
        // limit (`rule_support.py:200`).
        Rule::ForbiddenDependency(rule) => {
            let [sources, _] = selection::dependency_sides(rule, model.contract().components());
            sources.matches(source.module)
                && !rule
                    .allowed_sources()
                    .iter()
                    .any(|allowed| allowed.as_text() == source.module)
                && !(source.type_only && !rule.include_type_checking())
        }
        Rule::SiblingIsolation(rule) => {
            rule.members()
                .iter()
                .any(|member| in_scope(source.module, member.as_text()))
                && !(source.type_only && !rule.include_type_checking())
        }
        Rule::CompleteRequires(rule) => {
            owner_of(model.components(), source.module).is_some()
                && !(source.type_only && !rule.include_type_checking())
        }
        // Slice S7: a module cycle can close through any module; a component cycle through an
        // owned module. The type-only flag does not narrow a cycle rule.
        Rule::NoComponentCycles(rule) => {
            *rule.level() == CycleLevel::Module
                || owner_of(model.components(), source.module).is_some()
        }
        // `dynamic_dependency_limits` does not read these kinds.
        Rule::CompleteAssignment(_)
        | Rule::RootLayout(_)
        | Rule::LayerOrder(_)
        | Rule::AllowedDependency(_) => false,
        // A kind that no slice decides has no receipt; its slice states its limits here. Until
        // then a dynamic import reaches it (fail closed).
        Rule::CallOwner(_)
        | Rule::ForbiddenCallArgument(_)
        | Rule::CatalogArgument(_)
        | Rule::CatalogUse(_)
        | Rule::ForbiddenEffectUnderCondition(_)
        | Rule::ForbiddenConstruct(_)
        | Rule::SourceOwnership(_)
        | Rule::InterfaceBoundary(_)
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
        .any(|limit| {
            limit.source.as_deref().is_none_or(|module| {
                reaches(Source {
                    module,
                    type_only: limit.type_only(),
                })
            })
        })
}

/// The source module of a dynamic import limit and its type-only flag.
#[derive(Clone, Copy)]
struct Source<'a> {
    module: &'a str,
    type_only: bool,
}

/// The reason of an incomplete state for one rule. The host can accept a coverage gap for a
/// `complete_requires` rule with its dependency scope proof (`_scoped_dependency_receipt`), so
/// for that kind such a gap is a part that the core cannot read, not a fact.
fn rescued(rule: &Rule, reason: &Reason) -> Reason {
    let accepted = matches!(
        reason,
        Reason::Incomplete(Incomplete::CoverageGaps(_) | Incomplete::UnknownImports(_))
            | Reason::NotComplete(Cause::PairGaps(_))
    );
    if accepted && matches!(rule, Rule::CompleteRequires(_)) {
        Part::ScopedRequires.into()
    } else {
        reason.clone()
    }
}
