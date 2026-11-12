// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The verdict of one rule and the decision that carries it (AD-363).
//!
//! Another crate cannot write a PASS: `Verdict::Pass` holds a `Proven` mark that only this module
//! makes, and only `Scope::pass` (with the scope proof) gives a `Decision` that holds one.
//!
//! ```compile_fail
//! let pass = archkeel_model::Verdict::Pass(archkeel_model::Proven { _scope: () });
//! ```

use crate::reason::Reason;

/// The mark of a PASS: only the scope proof of the model gives one. It is not `Clone` or `Copy`,
/// so a caller cannot move it from one verdict into a new one (AD-378).
#[derive(Debug, PartialEq, Eq)]
pub struct Proven {
    _scope: (),
}

/// The verdict of one rule. A caller reads it from a `Decision` by reference; it holds no bare
/// `Verdict`.
#[derive(Debug, PartialEq, Eq)]
pub enum Verdict {
    Pass(Proven),
    Fail,
    Unknown,
}

/// A decided rule. The fields are private: a PASS comes only from `Scope::pass`. A PASS names
/// the rule of its proof and the serial of its model: a caller checks both
/// (`Decision::passes`), because a type cannot stop a value of one model or rule from moving
/// to another (AD-378).
#[derive(Debug, PartialEq, Eq)]
pub struct Decision {
    verdict: Verdict,
    reason: Option<Reason>,
    bound: Option<(String, u64)>,
}

impl Clone for Decision {
    fn clone(&self) -> Decision {
        let verdict = match &self.verdict {
            Verdict::Pass(_) => Verdict::Pass(Proven { _scope: () }),
            Verdict::Fail => Verdict::Fail,
            Verdict::Unknown => Verdict::Unknown,
        };
        Decision {
            verdict,
            reason: self.reason.clone(),
            bound: self.bound.clone(),
        }
    }
}

impl Decision {
    /// PASS: only `Scope::pass` calls it, with the scope proof.
    pub(crate) fn passed(rule: String, model: u64) -> Decision {
        Decision {
            verdict: Verdict::Pass(Proven { _scope: () }),
            reason: None,
            bound: Some((rule, model)),
        }
    }

    /// True for a PASS of the rule `rule` of this model; false for any other decision.
    pub fn passes(&self, model: &crate::model::Model, rule: &str) -> bool {
        matches!(self.verdict, Verdict::Pass(_))
            && self
                .bound
                .as_ref()
                .is_some_and(|(id, serial)| id == rule && *serial == model.serial())
    }

    /// FAIL: a found violation is a fact also in an incomplete scope.
    pub fn fail() -> Decision {
        Decision {
            verdict: Verdict::Fail,
            reason: None,
            bound: None,
        }
    }

    /// UNKNOWN, with its reason.
    pub fn unknown(reason: Reason) -> Decision {
        Decision {
            verdict: Verdict::Unknown,
            reason: Some(reason),
            bound: None,
        }
    }

    /// The verdict.
    pub fn verdict(&self) -> &Verdict {
        &self.verdict
    }

    /// The reason of an UNKNOWN.
    pub fn reason(&self) -> Option<&Reason> {
        self.reason.as_ref()
    }
}
