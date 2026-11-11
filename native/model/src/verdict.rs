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

/// The mark of a PASS: only the scope proof of the model gives one.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Proven {
    _scope: (),
}

/// The verdict of one rule. A caller reads it from a `Decision`; it holds no bare `Verdict`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Verdict {
    Pass(Proven),
    Fail,
    Unknown,
}

/// A decided rule. The fields are private: a PASS comes only from `Scope::pass`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Decision {
    verdict: Verdict,
    reason: Option<Reason>,
}

impl Decision {
    /// PASS: only `Scope::pass` calls it, with the scope proof.
    pub(crate) fn passed() -> Decision {
        Decision {
            verdict: Verdict::Pass(Proven { _scope: () }),
            reason: None,
        }
    }

    /// FAIL: a found violation is a fact also in an incomplete scope.
    pub fn fail() -> Decision {
        Decision {
            verdict: Verdict::Fail,
            reason: None,
        }
    }

    /// UNKNOWN, with its reason.
    pub fn unknown(reason: Reason) -> Decision {
        Decision {
            verdict: Verdict::Unknown,
            reason: Some(reason),
        }
    }

    /// The verdict.
    pub fn verdict(&self) -> Verdict {
        self.verdict
    }

    /// The reason of an UNKNOWN.
    pub fn reason(&self) -> Option<&Reason> {
        self.reason.as_ref()
    }
}
