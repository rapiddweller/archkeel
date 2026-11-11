// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The proof that a rule saw its whole domain (AD-363).
//!
//! `ScopeComplete` has a field that is private to this module, so no other module and no other
//! crate can make one. `Decision::pass` needs one. Slice S4 writes the proof here; until then
//! `Model::scope_complete` answers `Unsupported::ScopeProof`, so no rule can PASS.
//!
//! ```compile_fail
//! // A crate outside the model cannot make the proof.
//! let proof = archkeel_model::ScopeComplete { _proven: () };
//! ```

use crate::model::Model;
use crate::reason::{Reason, Unsupported};

/// The proof that the model saw the whole scope of a run.
#[derive(Debug)]
pub struct ScopeComplete {
    // Slice S4 makes it; the name says why nothing reads it.
    _proven: (),
}

impl Model {
    /// The scope proof of this model. Slice S4 ports it.
    pub fn scope_complete(&self) -> Result<ScopeComplete, Reason> {
        Err(Reason::Unsupported(Unsupported::ScopeProof))
    }
}
