// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The proof that a whole run passes (lead decision L-35b, AD-378, AD-381).
//!
//! A run passes only when the scope of its model is complete (`Scope::run`) and each rule of the
//! contract of the model has a PASS of this model. A contract without rules passes with a
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

use std::marker::PhantomData;

use archkeel_contract::head_of;

use crate::model::Model;
use crate::reason::Reason;
use crate::scope::Scope;
use crate::verdict::Decision;

/// An invariant lifetime: the brand of one `Model::scope` call.
type Brand<'id> = PhantomData<fn(&'id ()) -> &'id ()>;

/// The proof that the run of the model of the brand `'id` passes. It is not `Clone`.
#[derive(Debug)]
pub struct RunComplete<'id> {
    brand: Brand<'id>,
}

/// A PASS of a whole run. It names the serial of its model; `RunPass::of` checks it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RunPass {
    serial: u64,
}

impl RunPass {
    /// True when this PASS comes from the run proof of `model`.
    pub fn of(&self, model: &Model) -> bool {
        self.serial == model.serial()
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
    /// of this model, and each rule of the contract has one. The decisions name their rules.
    pub fn run_complete<'d>(
        &self,
        decisions: impl IntoIterator<Item = &'d Decision>,
    ) -> Result<RunComplete<'id>, RunGap> {
        self.run().map_err(RunGap::Scope)?;
        let model = self.model();
        let rules = model.contract().rules();
        let ids: Vec<&str> = rules.iter().map(|r| head_of(r).id().as_text()).collect();
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
            serial: self.model().serial(),
        }
    }
}
