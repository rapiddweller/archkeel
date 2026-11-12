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
//!
//! # The barrier of the report (AD-381)
//!
//! A crate outside the report cannot put a PASS into a report input without the evaluator, and
//! cannot write payload bytes without `Report`. Each attempt is a `compile_fail` test with its
//! error code; the twin that compiles:
//!
//! ```
//! use archkeel_eval::Outcome;
//! use archkeel_report::{Decided, Report, RuleOutcome, RuleText};
//! // R1, R2: a rule row from an outcome of the evaluator.
//! fn row(outcome: &Outcome, text: RuleText) -> RuleOutcome { RuleOutcome::evaluated(outcome, text) }
//! // R3, R4: bytes come from a decided report.
//! fn bytes(report: &Report<Decided>) -> Option<Vec<u8>> { report.encode().ok() }
//! ```
//!
//! R1. A report rule row from a bare PASS `Decision`: `evaluated` takes an `Outcome` (E0308).
//!
//! ```compile_fail,E0308
//! use archkeel_model::Decision;
//! use archkeel_report::{RuleOutcome, RuleText};
//! fn row(pass: &Decision, text: RuleText) -> RuleOutcome { RuleOutcome::evaluated(pass, text) }
//! ```
//!
//! R2. A report rule row literal: its id and decision are private (E0451).
//!
//! ```compile_fail,E0451
//! fn row(kind: String, text: archkeel_report::RuleText) -> archkeel_report::RuleOutcome {
//!     archkeel_report::RuleOutcome {
//!         id: "B".into(), kind, title: text.title, decision: todo!(), evaluated: true,
//!         why_unknown: None, undecided: text.undecided, rationale: text.rationale,
//!         decided_by: text.decided_by,
//!     }
//! }
//! ```
//!
//! R3. Payload bytes without `Report`: the payload type is private to the report (E0433).
//!
//! ```compile_fail,E0433
//! fn bytes(text: &[u8]) -> Vec<u8> {
//!     archkeel_report::Payload::decode(text).ok().and_then(|p| p.encode().ok()).unwrap_or_default()
//! }
//! ```
//!
//! R4. The bytes of a recorded report: only a decided report has `encode` (E0599).
//!
//! ```compile_fail,E0599
//! use archkeel_report::{Recorded, Report};
//! fn bytes(report: &Report<Recorded>) -> Option<Vec<u8>> { report.encode().ok() }
//! ```

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
mod beyond_tests;
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
