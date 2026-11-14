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
use crate::dropped_gaps;
use crate::model::Model;
use crate::ownership::{in_scope, owner_of};
use crate::pair_gaps::reads;
use crate::proof::State;
use crate::reason::{Reason, Unsupported};
use crate::receipts::{self, GapScope, ScanProof};
use crate::roots::Roots;
use crate::selection;
use crate::verdict::Decision;
use archkeel_facts::envelope::Layout;

use crate::brand::Brand;

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
        if let Rule::InterfaceBoundary(rule) = rule {
            crate::interface::receipt(self.model, rule)?;
        }
        let unread = match self.model.scope_state() {
            State::Incomplete(reason) => return Err(rescued(self.model, rule, reason)),
            State::Unread(part) => Some(part.clone()),
            State::Complete => None,
        };
        // AD-496: a feature that the collector states as unsupported holds each rule that reads it.
        let observed = self.model.graph().observed();
        if let Some(subject) = crate::limits::stated_hold(self.model.contract(), rule, observed) {
            return Err(Reason::NotComplete(Cause::ProfileLimit(subject)));
        }
        // Slice S7 (AD-384): a kept pair gap holds only the rules whose reading it can change;
        // AD-418: so does a gap that the drop rule drops.
        let gaps = self
            .gaps(rule)
            .map_err(|reason| rescued(self.model, rule, &reason))?;
        // The doubt sources of the rule come before its receipt, so each kind states them.
        if dynamic_import(self.model, rule) {
            return Err(Reason::NotComplete(Cause::DynamicImport));
        }
        match rule {
            Rule::NoComponentCycles(cycle) => receipts::cycle(self.model, cycle, self.scan())?,
            Rule::InterfaceBoundary(_) => receipts::interface(self.model, self.scan())?,
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
    /// Slice S7 (AD-384): each kept pair gap holds the run. AD-418: a gap that the drop rule
    /// drops holds the run when it can change a rule of the contract; one that changes no rule
    /// cannot change the run, as in the reference engine, which forgets it.
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
        let rules = self.model.contract().rules();
        let components = self.model.contract().components();
        let dropped = pairs.dropped.iter().filter(|gap| {
            rules
                .iter()
                .any(|rule| dropped_gaps::holds(gap, rule, &reads(rule, components)))
        });
        if let Some(held) = Held::of(dropped.map(|gap| (gap.source.as_str(), gap.target.as_str())))
        {
            return Err(Reason::NotComplete(Cause::AllowedPairGaps(held)));
        }
        match self.model.scope_state() {
            State::Unread(part) => Err(part.clone().into()),
            _ => Ok(()),
        }
    }

    /// The scope proof of the UML target row `id` (AD-494): the scope of the whole run must be
    /// complete, because a target can name each component. The caller passes only a target whose
    /// every assessment passes (`uml::compare`).
    fn uml_complete(&self, id: &str, modules: &[&str]) -> Result<ScopeComplete<'id>, Reason> {
        self.uml_run(modules)?;
        Ok(ScopeComplete {
            brand: PhantomData,
            rule: id.to_owned(),
        })
    }

    /// The scope of the run for the UML target row (AD-494): the run is complete, and no pair
    /// gap that the drop rule drops touches a module that the target names. `run` lets such a
    /// gap hold only the rules of the contract, but the gap can be an import edge between two
    /// modules of the target, so it holds the row for a PASS and for a FAIL.
    fn uml_run(&self, modules: &[&str]) -> Result<(), Reason> {
        self.run()?;
        let touched = self.model.pairs().dropped.iter().filter(|gap| {
            modules.contains(&gap.source.as_str()) || modules.contains(&gap.target.as_str())
        });
        match Held::of(touched.map(|gap| (gap.source.as_str(), gap.target.as_str()))) {
            Some(held) => Err(Reason::NotComplete(Cause::AllowedPairGaps(held))),
            None => Ok(()),
        }
    }

    /// PASS, with a proof of this scope.
    /// The PASS names the rule of the proof and the serial of the model.
    pub fn pass(&self, proof: ScopeComplete<'id>) -> Decision {
        let ScopeComplete { brand: _, rule } = proof;
        Decision::passed(rule, self.model.serial())
    }
}

impl<'id, 'm> Scope<'id, 'm> {
    /// The gap scope of one rule, or the kept gaps that can change what it reads.
    pub fn gaps(&self, rule: &Rule) -> Result<GapScope<'id>, Reason> {
        let model = self.model();
        let reading = reads(rule, model.contract().components());
        let held = model
            .pairs()
            .kept
            .iter()
            .filter(|gap| gap.holds(&reading))
            .map(|gap| (gap.source.as_str(), gap.target.as_str()));
        if let Some(held) = Held::of(held) {
            return Err(Reason::NotComplete(Cause::PairGaps(held)));
        }
        let dropped = model
            .pairs()
            .dropped
            .iter()
            .filter(|gap| dropped_gaps::holds(gap, rule, &reading))
            .map(|gap| (gap.source.as_str(), gap.target.as_str()));
        match Held::of(dropped) {
            Some(held) => Err(Reason::NotComplete(Cause::AllowedPairGaps(held))),
            None => Ok(GapScope::of()),
        }
    }

    /// The scan proof of the model: the bound roots and the module files of the reply.
    pub fn scan(&self) -> Result<ScanProof<'id, 'm>, Reason> {
        let model = self.model();
        let graph = model.graph();
        let roots = graph.settings().roots().ok_or(Part::ScanRoots)?;
        if graph.observed().layout != Layout::ProjectFiles {
            return Err(Part::ScanLayout.into());
        }
        let files = graph
            .modules()
            .iter()
            .map(|(_, module)| (module.name(), module.file()))
            .collect();
        Ok(ScanProof::of(Roots::new(roots, files)))
    }
}

/// The PASS of the UML target row `id` of the root model, with the scope proof of the run
/// (AD-494).
pub(crate) fn uml_pass(model: &Model, id: &str, modules: &[&str]) -> Result<Decision, Reason> {
    model.scope(|scope| {
        scope
            .uml_complete(id, modules)
            .map(|proof| scope.pass(proof))
    })
}

/// True when the scope of the run is complete for the UML target row that names `modules`
/// (AD-494).
pub(crate) fn uml_run(model: &Model, modules: &[&str]) -> bool {
    model.scope(|scope| scope.uml_run(modules)).is_ok()
}

/// The receipt of a rule (`rules.py` `_rule_evaluation_facts_for_rule`): the rule selects a
/// module of the reply. Only the kinds that the evaluator decides have one here.
fn receipt(model: &Model, rule: &Rule) -> Result<(), Reason> {
    // `_observed_rule_modules`: the modules of the source domain of the model (AD-385).
    let observed = || {
        model
            .graph()
            .modules()
            .iter()
            .filter(|(id, _)| model.holds(*id))
    };
    let selected = match rule {
        Rule::CompleteAssignment(rule) | Rule::CompleteExternalScope(rule) => {
            !model.source_modules(rule.source().as_text()).is_empty()
        }
        Rule::RootLayout(rule) => {
            observed().any(|(_, module)| in_scope(module.name(), rule.root().as_text()))
        }
        Rule::ExternalDependencyScope(_) => observed().next().is_some(),
        Rule::InterfaceBoundary(_) => observed().next().is_some(),
        Rule::ForbiddenConstruct(rule) => {
            crate::construct_match::receipt(model, rule)?;
            true
        }
        // Slice S5 (AD-380), `_rule_evaluation_facts_for_rule`.
        // An undecided position (`symbol_limits`) withholds the receipt as well.
        Rule::ForbiddenDependency(rule) => {
            let judged = direction::forbidden(model, rule)
                .into_iter()
                .map(|(_, j)| j);
            undecided(direction::undecided(judged))?;
            let [sources, _] = selection::dependency_sides(rule, model.contract().components());
            observed().any(|(_, module)| sources.matches(module.name()))
        }
        Rule::SiblingIsolation(rule) => observed().any(|(_, module)| {
            rule.members()
                .iter()
                .any(|member| in_scope(module.name(), member.as_text()))
        }),
        // `_layer_order_evaluation_facts`: the selected components; the receipt cites the
        // contract file (`_layer_order_evidence`). The layer gaps are a cause of the state.
        Rule::LayerOrder(rule) => {
            // AD-385: the receipt of an inside rule cites the file of the inside contract.
            if model.is_mount() {
                return Err(Part::MountedLayerOrder.into());
            }
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
        | Rule::SourceOwnership(_)
        | Rule::NoComponentCycles(_)
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
        Rule::InterfaceBoundary(rule) => {
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
        Rule::ForbiddenConstruct(_) => false,
        // A kind that no slice decides has no receipt; its slice states its limits here. Until
        // then a dynamic import reaches it (fail closed).
        Rule::CallOwner(_)
        | Rule::ForbiddenCallArgument(_)
        | Rule::CatalogArgument(_)
        | Rule::CatalogUse(_)
        | Rule::ForbiddenEffectUnderCondition(_)
        | Rule::SourceOwnership(_)
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
            // `dynamic_dependency_limits(source_modules=...)`: a mount reads only the limits of
            // its domain. A limit without a source module stops the reference engine.
            limit.source.as_deref().is_none_or(|module| {
                model.selects(module)
                    && reaches(Source {
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
/// for that kind such a gap is a part that the core cannot read, not a fact. AD-418: the host
/// accepts the proof only from a runtime that can carry it (`_native_scope_runtime_valid`); for
/// any other runtime the gap is a fact, and the reference engine gives UNKNOWN too.
fn rescued(model: &Model, rule: &Rule, reason: &Reason) -> Reason {
    let accepted = matches!(
        reason,
        Reason::Incomplete(Incomplete::CoverageGaps(_) | Incomplete::UnknownImports(_))
            | Reason::NotComplete(Cause::PairGaps(_))
    );
    let carried = model.graph().observed().scope_receipt;
    if accepted && carried && matches!(rule, Rule::CompleteRequires(_)) {
        Part::ScopedRequires.into()
    } else {
        reason.clone()
    }
}
