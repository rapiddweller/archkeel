// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The verdict of one rule and the decision that carries it.

use crate::reason::Reason;
use crate::scope::ScopeComplete;

/// The verdict of one rule.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Verdict {
    Pass,
    Fail,
    Unknown,
}

/// A decided rule. The fields are private: a PASS comes only from `pass`, which needs the proof.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Decision {
    verdict: Verdict,
    reason: Option<Reason>,
}

impl Decision {
    /// PASS: only with the scope proof of the model.
    pub fn pass(_proof: &ScopeComplete) -> Decision {
        Decision {
            verdict: Verdict::Pass,
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
