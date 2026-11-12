// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The proof that a whole run passes (lead decision L-35b, AD-378, AD-381).
//!
//! A run passes only when the scope of its model is complete (`Scope::run`) and each rule of the
//! contract of the model has a PASS of this model. A permission declaration has no verdict and
//! needs none. A contract without rules passes with a
//! complete scope, as the reference engine does (`check/run.py:76-95`, `inspect_observation`).
//!
//! `Scope::run_complete` is the only maker of the proof `RunComplete<'id>`. The proof has the
//! brand of its scope, so it cannot leave the scope and cannot pass the run of another model.
//! `Scope::pass_run` uses it up and gives `RunPass`, which names the serial of its model.
//!
//! A crate outside the model cannot make the proof:
//!
//! ```compile_fail,E0451
//! fn forge<'id>() -> archkeel_model::RunComplete<'id> {
//!     archkeel_model::RunComplete { brand: std::marker::PhantomData }
//! }
//! ```

#![deny(
    clippy::wildcard_enum_match_arm,
    clippy::match_wildcard_for_single_variants
)]

use std::marker::PhantomData;

use archkeel_contract::{head_of, kind_of, Rule, RuleKind};

use crate::model::Model;
use crate::reason::Reason;
use crate::scope::Scope;
use crate::tree::ModelTree;
use crate::verdict::Decision;

/// An invariant lifetime: the brand of one `Model::scope` call.
type Brand<'id> = PhantomData<fn(&'id ()) -> &'id ()>;

/// The proof that the run of the model of the brand `'id` passes. It is not `Clone`.
#[derive(Debug)]
pub struct RunComplete<'id> {
    brand: Brand<'id>,
}

/// A PASS of a whole run. It names the serial of each model whose run proof it holds: one model,
/// or each model of a tree in the order of the tree (AD-385). `RunPass::of` checks the run PASS
/// of one model; the run PASS of a tree comes only from `ModelTree::pass_run`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RunPass {
    serials: Vec<u64>,
}

impl RunPass {
    /// True when this PASS comes from the run proof of `model` alone.
    pub fn of(&self, model: &Model) -> bool {
        self.serials == [model.serial()]
    }
}

/// Why a run has no run proof.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RunGap {
    /// The scope of the model is not complete (`Scope::run`).
    Scope(Reason),
    /// A rule of the contract has no PASS of this model: the rule id.
    Rule(String),
    /// The decision at this index is not a PASS of a rule of this contract and model.
    NotPass(usize),
}

impl<'id> Scope<'id, '_> {
    /// The run proof: the scope is complete, each decision is a PASS of a rule of the contract
    /// of this model, and each rule of the contract that is not a permission declaration has
    /// one. The decisions name their rules.
    pub fn run_complete<'d>(
        &self,
        decisions: impl IntoIterator<Item = &'d Decision>,
    ) -> Result<RunComplete<'id>, RunGap> {
        self.run().map_err(RunGap::Scope)?;
        let model = self.model();
        // A permission declaration (`allowed_dependency`) has no verdict, so it needs no PASS
        // (`ir/decisions.py:763`). The kind comes from the contract of the model, never from a
        // row of the caller.
        let rules = model.contract().rules();
        let ids: Vec<&str> = rules
            .iter()
            .filter(|rule| !declaration(rule))
            .map(|r| head_of(r).id().as_text())
            .collect();
        let decisions: Vec<&Decision> = decisions.into_iter().collect();
        let passes_one = |d: &Decision| ids.iter().any(|id| d.passes(model, id));
        if let Some(index) = decisions.iter().position(|d| !passes_one(d)) {
            return Err(RunGap::NotPass(index));
        }
        let missing = ids
            .iter()
            .find(|id| !decisions.iter().any(|d| d.passes(model, id)));
        match missing {
            Some(id) => Err(RunGap::Rule((*id).to_owned())),
            None => Ok(RunComplete { brand: PhantomData }),
        }
    }

    /// A PASS of the run, with a run proof of this scope.
    pub fn pass_run(&self, proof: RunComplete<'id>) -> RunPass {
        let RunComplete { brand: _ } = proof;
        RunPass {
            serials: vec![self.model().serial()],
        }
    }
}

impl ModelTree {
    /// The PASS of the run of a tree (AD-385): each decision is a PASS of a rule of one model of
    /// the tree, and each model gives its own run proof over its own decisions in its own scope
    /// (`Scope::run_complete`). So each rule of each mount needs a PASS of the model of that
    /// mount, and one named, refused or failing rule of any mount holds back the run.
    pub fn pass_run<'d>(
        &self,
        decisions: impl IntoIterator<Item = &'d Decision>,
    ) -> Result<RunPass, RunGap> {
        let models: Vec<&Model> = self.models().collect();
        let mut shares: Vec<Vec<&Decision>> = vec![Vec::new(); models.len()];
        for (index, decision) in decisions.into_iter().enumerate() {
            let owner = models.iter().position(|model| {
                model
                    .contract()
                    .rules()
                    .iter()
                    .any(|rule| decision.passes(model, head_of(rule).id().as_text()))
            });
            match owner.and_then(|owner| shares.get_mut(owner)) {
                Some(share) => share.push(decision),
                None => return Err(RunGap::NotPass(index)),
            }
        }
        let mut serials = Vec::with_capacity(models.len());
        for (model, share) in models.into_iter().zip(shares) {
            let pass = model.scope(|scope| {
                let proof = scope.run_complete(share)?;
                Ok::<RunPass, RunGap>(scope.pass_run(proof))
            })?;
            serials.extend(pass.serials);
        }
        Ok(RunPass { serials })
    }

    /// The model whose contract holds the rule `id`: the root or one mount. The scoped ids of a
    /// tree are unique (AD-366), so at most one model holds it.
    pub fn model_of(&self, id: &str) -> Option<&Model> {
        self.models().find(|model| {
            model
                .contract()
                .rules()
                .iter()
                .any(|rule| head_of(rule).id().as_text() == id)
        })
    }
}

/// True for a permission declaration: a rule without a verdict (`ir/decisions.py:763`).
pub(crate) fn declaration(rule: &Rule) -> bool {
    kind_of(rule) == RuleKind::AllowedDependency
}

impl Model {
    /// True when `rule` is a permission declaration of the contract of this model: the report
    /// shows it as DECLARATION only then (AD-381).
    pub fn declares(&self, rule: &str) -> bool {
        self.contract()
            .rules()
            .iter()
            .any(|r| declaration(r) && head_of(r).id().as_text() == rule)
    }
}
