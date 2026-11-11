// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The proof that a rule saw the whole domain of its model (AD-363).
//!
//! `Model::scope` gives a `Scope` with a brand: a lifetime that only this call has. The proof
//! `ScopeComplete` carries the brand of its model, and `Scope::pass` takes only a proof of the
//! same brand. So a proof cannot be used with another model, cannot outlive its scope, and no
//! other module or crate can make one. Slice S4 writes the proof in `Scope::complete`; until
//! then it answers `Unsupported::ScopeProof`, so no rule can PASS.
//!
//! The use that compiles:
//!
//! ```
//! fn decide(model: &archkeel_model::Model) -> Option<archkeel_model::Decision> {
//!     model.scope(|scope| scope.complete().ok().map(|proof| scope.pass(proof)))
//! }
//! ```
//!
//! A proof of one model cannot decide a rule of another model:
//!
//! ```compile_fail
//! fn decide(a: &archkeel_model::Model, b: &archkeel_model::Model) {
//!     a.scope(|a| b.scope(|b| a.complete().ok().map(|proof| b.pass(proof))));
//! }
//! ```
//!
//! A proof cannot leave its scope:
//!
//! ```compile_fail
//! fn keep(model: &archkeel_model::Model) {
//!     let _proof = model.scope(|scope| scope.complete().ok());
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

use crate::model::Model;
use crate::reason::{Reason, Unsupported};
use crate::verdict::Decision;

/// An invariant lifetime: two calls of `Model::scope` never have the same one.
type Brand<'id> = PhantomData<fn(&'id ()) -> &'id ()>;

/// The proof that the model of the brand `'id` saw the whole scope of its run.
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

    /// The scope proof of this model. Slice S4 ports it.
    pub fn complete(&self) -> Result<ScopeComplete<'id>, Reason> {
        Err(Reason::Unsupported(Unsupported::ScopeProof))
    }

    /// PASS, with a proof of this scope.
    pub fn pass(&self, proof: ScopeComplete<'id>) -> Decision {
        let ScopeComplete { brand: _ } = proof;
        Decision::passed()
    }
}
