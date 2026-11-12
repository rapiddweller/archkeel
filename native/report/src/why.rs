// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reason code of an UNKNOWN rule row from the reason of the model (#1073 item 7, AD-381).
//!
//! Each match lists every variant and has no wildcard: a new reason of the model does not
//! compile here until its row reason is decided.
//!
//! - `undecided`: a dynamic import reaches the rule, an undecided position of AD-92.
//! - `no_receipt`: the evaluator has no receipt for the rule: its kind is not ported, it selects
//!   no module, or a cited child has no module record.
//! - `scope_incomplete`: each other reason. The scope of the run is not complete or not read.
//! - `ownership_blocker`: no reason of the model maps to it yet.

use archkeel_model::{Cause, Reason, Unsupported};

use crate::input::WhyUnknown;

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
        Cause::DynamicImport => WhyUnknown::Undecided,
        Cause::PairGaps(_)
        | Cause::WorkTree
        | Cause::Runtime
        | Cause::Producer
        | Cause::ProfileLimit(_)
        | Cause::LayerMetadata(_)
        | Cause::NoRuleSubjects(_) => WhyUnknown::ScopeIncomplete,
    }
}
