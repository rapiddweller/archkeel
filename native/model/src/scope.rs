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
//! ```compile_fail,E0521
//! fn decide(a: &archkeel_model::Model, b: &archkeel_model::Model, rule: &archkeel_contract::Rule) {
//!     a.scope(|a| b.scope(|b| a.complete(rule).ok().map(|proof| b.pass(proof))));
//! }
//! ```
//!
//! A proof cannot leave its scope:
//!
//! ```compile_fail,E0521
//! fn keep(model: &archkeel_model::Model, rule: &archkeel_contract::Rule) {
//!     let mut proof = None;
//!     model.scope(|scope| proof = scope.complete(rule).ok());
//!     drop(proof);
//! }
//! ```
//!
//! A crate outside the model cannot make the proof:
//!
//! ```compile_fail,E0603
//! fn forge<'id>() -> archkeel_model::scope::ScopeComplete<'id> {
//!     archkeel_model::scope::ScopeComplete { brand: std::marker::PhantomData, rule: String::new() }
//! }
//! ```

use std::marker::PhantomData;

use archkeel_contract::{head_of, Rule};

use crate::causes::{Cause, Held};
use crate::model::Model;
use crate::reason::Reason;
use crate::receipts::{GapScope, ScanProof};
use crate::verdict::Decision;

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
    pub(crate) model: &'m Model,
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
    /// none. The causes are read in the one order of `scope_order.rs`: a fact that makes the scope
    /// incomplete comes before a part that the core cannot read (with a fact, the reference
    /// engine gives UNKNOWN too).
    pub fn complete(&self, rule: &Rule) -> Result<ScopeComplete<'id>, Reason> {
        crate::scope_order::rule(self.model, rule)?;
        Ok(ScopeComplete {
            brand: PhantomData,
            rule: head_of(rule).id().as_text().to_owned(),
        })
    }

    /// Every cause that holds `rule`, the first one first (AD-1290). Empty when the scope of the rule is complete.
    pub fn causes(&self, rule: &Rule) -> Vec<Reason> {
        crate::scope_order::rule_causes(self.model, rule)
    }

    /// The scope state of the whole run: `Ok` only when the model has no cause and no unread
    /// part. The status of a frame reads it (lead decision L-35b): a run whose scope is not
    /// complete is never PASS, also with zero rules. It reads the same sources as `complete`, in
    /// the run order of `scope_order.rs`.
    ///
    /// Slice S7 (AD-384): each kept pair gap holds the run. AD-418: a gap that the drop rule
    /// drops holds the run when it can change a rule of the contract; one that changes no rule
    /// cannot change the run, as in the reference engine, which forgets it.
    pub fn run(&self) -> Result<(), Reason> {
        crate::scope_order::run(self.model)
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
        crate::scope_receipt::gap_scope(self.model(), rule)
    }

    /// The scan proof of the model: the bound roots and the module files of the reply.
    pub fn scan(&self) -> Result<ScanProof<'id, 'm>, Reason> {
        crate::scope_receipt::scan_proof(self.model())
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
