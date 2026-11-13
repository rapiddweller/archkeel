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
//! The core binary writes the status of its engine frame and the verdict of each rule only
//! through `rule`, which gives a `Ruling` with the same `Decided` mark (AD-388). The input types
//! of `build` (`RunOutcome`, `Records`) are the seam that the evaluator and the model slices fill.
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
//!
//! # The barrier of the engine frame (AD-388)
//!
//! The core cannot write a status or a rule verdict without a `Ruling`, and only `rule` makes
//! one, from the model. The twin that compiles:
//!
//! ```
//! use archkeel_model::{ModelTree, Reason};
//! use archkeel_report::{rule, Named, Ruling};
//! fn ruling(models: Result<&ModelTree, &Reason>) -> Option<Ruling> {
//!     rule(models, Named::default()).ok()
//! }
//! ```
//!
//! R5. A ruling from a bare verdict: `rule` takes the model, not a `Verdict` (E0308).
//!
//! ```compile_fail,E0308
//! use archkeel_model::Verdict;
//! use archkeel_report::{rule, Named, Ruling};
//! fn ruling(pass: Verdict) -> Option<Ruling> { rule(pass, Named::default()).ok() }
//! ```
//!
//! R6. A ruling from the outcomes of another model: `rule` evaluates its models itself and takes
//! no outcome (E0061).
//!
//! ```compile_fail,E0061
//! use archkeel_eval::Outcome;
//! use archkeel_model::{ModelTree, Reason};
//! use archkeel_report::{rule, Named, Ruling};
//! fn ruling(other: Vec<Outcome>, models: &ModelTree) -> Option<Ruling> {
//!     rule(other, Ok(models), Named::default()).ok()
//! }
//! ```
//!
//! R7. A hand-made status: the fields of a ruling are private (E0451).
//!
//! ```compile_fail,E0451
//! use archkeel_report::{Decided, RuleReasons, Ruling, Status};
//! fn ruling(decided: Decided) -> Ruling {
//!     Ruling { decided, protocol: "archkeel-core-frame-1", status: Status::Pass,
//!         rules: Default::default(), details: Default::default(), unknown_kinds: Default::default(),
//!         explained: Default::default(), violations: Default::default(),
//!         beyond: Default::default(), scope: "complete".into(),
//!         unsupported: RuleReasons::All(String::new()) }
//! }
//! ```
//!
//! R8. A decided mark without the run proof: its fields are private to the report (E0451).
//!
//! ```compile_fail,E0451
//! use archkeel_report::{Decided, Status};
//! fn decided() -> Decided {
//!     Decided { status: Status::Pass, pass: None, observation: Status::Pass, rules: Vec::new() }
//! }
//! ```
//!
//! R9. A gap of the core that holds a verdict: `Named` has no verdict field (E0560).
//!
//! ```compile_fail,E0560
//! use archkeel_report::{Named, Status};
//! fn named() -> Named { Named { status: Status::Pass, ..Named::default() } }
//! ```
//!
//! R10. A status changed after `rule`: a ruling has no setter (E0599).
//!
//! ```compile_fail,E0599
//! use archkeel_report::{Ruling, Status};
//! fn pass(ruling: Ruling) -> Ruling { ruling.with_status(Status::Pass) }
//! ```
//!
//! R12. A ruling from one model of a tree: `rule` takes the whole `ModelTree`, so the run proof
//! of a tree has one maker, `ModelTree::pass_run` (AD-385) (E0308).
//!
//! ```compile_fail,E0308
//! use archkeel_model::{Model, Reason};
//! use archkeel_report::{rule, Named, Ruling};
//! fn ruling(mount: &Model) -> Option<Ruling> { rule(Ok(mount), Named::default()).ok() }
//! ```
//!
//! R11. Frame bytes with a hand-made status: only `Ruling::frame` makes an `EngineFrame`, and
//! a part with a key of the ruling is refused when it runs (E0451).
//!
//! ```compile_fail,E0451
//! fn frame() -> archkeel_report::EngineFrame {
//!     archkeel_report::EngineFrame { bytes: br#"{"status": "PASS"}"#.to_vec() }
//! }
//! ```

#![deny(unreachable_pub)]

mod construct;
pub use construct::construct_row;

#[cfg(test)]
mod construct_replay_tests;

mod build_error;
mod build_tables;
mod check;
mod check_order;
mod check_rows;
mod check_structure;
mod codes;
mod engine_frame;
mod frame;
mod frame_rules;
mod head;
mod input;
mod kind;
mod payload;
mod problem;
mod report;
mod ruling;
mod status;
mod violation_detail;
mod why;

pub use build_error::BuildError;
pub use codes::{
    BudgetVerdict, Code, CodeList, Disposition, EdgeTarget, FindingKind, FindingReason, Gap, Kind,
    MeasureDef, MeasureState, NodeLevel, Permission, Relation, UnknownReason, UnknownSource, Vis,
    NOT_CARRIED,
};
pub use engine_frame::{EngineFrame, FrameError};
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
pub use ruling::{rule, Named, RuleReasons, Ruling};
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
#[cfg(test)]
mod tree_run_tests;
