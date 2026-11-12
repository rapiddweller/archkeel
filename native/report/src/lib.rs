// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-report, slice 0d of WP6 (AD-361, AD-371, epic #880).
//!
//! The report v2 payload is the `Report` frame of the core. This crate owns:
//!
//! - the typed payload (the head and the columnar tables) and its code lists; the payload type
//!   and its bytes are private to the crate, so bytes leave only through `Report` (AD-381);
//! - the canonical bytes of AD-361 point 9 (`Report::encode`, `Report::read`);
//! - the status rule of AD-361 point 4 (`status_of`) and the rule that each status other than
//!   PASS has an explaining row (`unexplained`);
//! - the check (`problems`), with every rule of the oracle checker and more;
//! - `Report`: a payload that passed the check. `build` makes a `Report<Decided>` from the
//!   outcomes of the evaluator, the rows and the model; `Report::read` a `Report<Recorded>`;
//! - the reason code of an UNKNOWN rule from the reason of the model (`WhyUnknown::of`).
//!
//! A PASS needs the model (AD-381): a rule row only with a PASS of its own rule of the model, the
//! observation only with a complete scope, the status only with the run proof (L-35b).
//!
//! The crate is not wired yet: the core binary does not call it. The input types of `build`
//! (`RunOutcome`, `Records`) are the seam that the evaluator and the model slices fill.

#![deny(unreachable_pub)]

mod build_error;
mod build_tables;
mod check;
mod check_order;
mod check_rows;
mod check_structure;
mod codes;
mod frame;
mod frame_rules;
mod head;
mod input;
mod kind;
mod payload;
mod problem;
mod report;
mod status;
mod why;

pub use build_error::BuildError;
pub use codes::{
    BudgetVerdict, Code, CodeList, Disposition, EdgeTarget, FindingKind, FindingReason, Gap, Kind,
    MeasureDef, MeasureState, NodeLevel, Permission, Relation, UnknownReason, UnknownSource, Vis,
    NOT_CARRIED,
};
pub use frame::build;
pub use head::{
    Component, Counts, Coverage, GapRow, NotRanked, PayloadBudget, RuleReason, RuleResult,
    RuleVerdict, Run, RunContract, Source, Status, Summary, TrendPoint,
};
#[cfg(test)]
pub(crate) use input::RuleDecision;
pub use input::{
    ComponentText, CrossingRow, Diagnostic, EdgeRow, FindingRow, GraphRows, MeasureRow, NodeRow,
    PermissionRow, Produced, Records, RuleOutcome, RuleText, RunFacts, RunOutcome, Target, Tree,
    Undecided, UnitRow, UnknownRecord, ViolationRow,
};
#[cfg(test)]
pub(crate) use payload::Payload;
pub use payload::{DecodeError, MAX_BYTES, SCHEMA_VERSION};
pub use problem::Problem;
pub use report::{Decided, ReadError, Recorded, Report};
#[cfg(test)]
pub(crate) use status::{status_of, unexplained};
pub use status::{Unexplained, PASS_NEEDS};
pub use tables::{
    opt_gap, Carriers, Crossings, Edges, Fields, Findings, Flag, Id, Measures, Nodes, OptGap,
    OptId, OptStr, Params, Permissions, StrId, Units, Unknowns, Variants, Violations,
};
pub use why::WhyUnknown;

mod tables;

#[cfg(test)]
mod build_tests;
#[cfg(test)]
mod codec_tests;
#[cfg(test)]
mod corpus_tests;
#[cfg(test)]
mod fault_tests;
#[cfg(test)]
mod review_tests;
#[cfg(test)]
mod run_tests;
#[cfg(test)]
mod schema_tests;
#[cfg(test)]
mod status_tests;
#[cfg(test)]
mod test_support;
