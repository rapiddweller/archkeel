// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-report, slice 0d of WP6 (AD-361, AD-371, epic #880).
//!
//! The report v2 payload is the `Report` frame of the Rust core. This crate owns:
//!
//! - the typed payload (`Payload`, the head and the columnar tables) and its code lists;
//! - the canonical bytes of AD-361 point 9 (`Payload::encode`, `Payload::decode`);
//! - the status rule of AD-361 point 4 (`status_of`) and the rule that each status other than
//!   PASS has an explaining row (`unexplained`);
//! - the check (`problems`), with every rule of the Python checker and more;
//! - `Report`: a payload that passed the check. `build` makes a `Report<Decided>` from the
//!   outcome of the evaluator and the rows of the model; `Report::read` a `Report<Recorded>`.
//!
//! The crate is not wired yet: the core binary does not call it. The input types of `build`
//! (`Outcome`, `Records`) are the seam that the eval crate and the model slices fill.

#![deny(unreachable_pub)]

mod build_tables;
mod check;
mod check_order;
mod check_rows;
mod check_structure;
mod codes;
mod frame;
mod head;
mod input;
mod payload;
mod problem;
mod report;
mod status;

pub use check::problems;
pub use codes::{
    Code, CodeList, Disposition, EdgeTarget, FindingKind, Gap, Kind, Level, Measure, MeasureState,
    Permission, Reason, Relation, UnknownReason, UnknownSource, Verdict, Vis, NOT_CARRIED,
};
pub use frame::{build, BuildError};
pub use head::{
    Component, Counts, Coverage, GapRow, NotRanked, PayloadBudget, RuleReason, RuleResult,
    RuleVerdict, Run, RunContract, Source, Status, Summary, TrendPoint,
};
pub use input::{
    ComponentText, CrossingRow, Diagnostic, EdgeRow, FindingRow, Graph, MeasureRow, NodeRow,
    Outcome, PermissionRow, Produced, Records, RuleDecision, RuleOutcome, RunFacts, Target, Tree,
    Undecided, UnitRow, UnknownRecord, ViolationRow,
};
pub use payload::{DecodeError, Payload, MAX_BYTES, SCHEMA_VERSION};
pub use problem::Problem;
pub use report::{Decided, ReadError, Recorded, Report};
pub use status::{status_of, unexplained, Unexplained};
pub use tables::{
    opt_gap, Carriers, Crossings, Edges, Fields, Findings, Flag, Id, Measures, Nodes, OptGap,
    OptId, OptStr, Params, Permissions, StrId, Units, Unknowns, Variants, Violations,
};

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
mod schema_tests;
#[cfg(test)]
mod status_tests;
#[cfg(test)]
mod test_support;
