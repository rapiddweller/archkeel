// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reason code of an UNKNOWN rule row from the reason of the model (#1073 item 7, AD-381).
//!
//! Each match lists every variant and has no wildcard: a new reason of the model does not
//! compile here until its row reason is decided.
//!
//! - `undecided`: the rule left imports undecided, an undecided position of AD-92.
//! - `no_receipt`: the evaluator has no receipt for the rule: its kind is not ported, it selects
//!   no module, a dynamic import reaches it, or a cited child has no module record.
//! - `scope_incomplete`: each other reason. The scope of the run is not complete or not read.
//! - `ownership_blocker`: no reason of the model maps to it yet.
//!
//! The reference engine checks an incomplete observation before the receipt
//! (`ir/decisions.py:770-779`). So `Cause::NoRuleSubjects` (a rule side without subjects is a
//! coverage failure of the run) is `scope_incomplete`, and `Reason::NoSubjects` (this rule has
//! no receipt in a complete scope) is `no_receipt`. A dynamic import leaves the rule without its
//! receipt (AD-378), so it is `no_receipt`; `Cause::Undecided` is an undecided position. A receipt
//! that is not complete (`Cause::Receipt`, AD-384) is `no_receipt`; a pair gap that holds the rule
//! is `scope_incomplete`.

#![deny(
    clippy::wildcard_enum_match_arm,
    clippy::match_wildcard_for_single_variants
)]

use archkeel_model::{Cause, Reason, Unsupported};

/// Why the evaluator left a rule UNKNOWN. The builder derives the reason of every other verdict
/// from the `Decision`: PASS is `evaluated`, FAIL `violations`, a declaration `declaration`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WhyUnknown {
    ScopeIncomplete,
    NoReceipt,
    Undecided,
    OwnershipBlocker,
}

impl WhyUnknown {
    /// The reason code of an UNKNOWN rule with this reason of the model.
    pub fn of(reason: &Reason) -> WhyUnknown {
        match reason {
            Reason::Unsupported(part) => unsupported(part),
            Reason::NotComplete(cause) => not_complete(cause),
            Reason::NoSubjects | Reason::UncitedChild(_) => WhyUnknown::NoReceipt,
            Reason::TooManyRows(_)
            | Reason::MissingInput(_)
            | Reason::Incomplete(_)
            | Reason::Refused(_) => WhyUnknown::ScopeIncomplete,
        }
    }
}

fn unsupported(part: &Unsupported) -> WhyUnknown {
    match part {
        Unsupported::Rule(_) | Unsupported::InsideRule => WhyUnknown::NoReceipt,
        Unsupported::ScopeProof(_)
        | Unsupported::Section(_)
        | Unsupported::Report
        | Unsupported::InsideTree
        | Unsupported::UmlTarget
        | Unsupported::Baseline
        | Unsupported::TreeScope => WhyUnknown::ScopeIncomplete,
    }
}

fn not_complete(cause: &Cause) -> WhyUnknown {
    match cause {
        Cause::Undecided(_) => WhyUnknown::Undecided,
        Cause::DynamicImport | Cause::Receipt(_) => WhyUnknown::NoReceipt,
        Cause::PairGaps(_)
        | Cause::WorkTree
        | Cause::Runtime
        | Cause::Producer
        | Cause::ProfileLimit(_)
        | Cause::LayerMetadata(_)
        | Cause::NoRuleSubjects(_)
        // A claim of a mount outside its parent is a coverage failure of the run (AD-385).
        | Cause::InsideSourceDomain(_) => WhyUnknown::ScopeIncomplete,
    }
}
