// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The engine ruling and frame of ArchKeel (AD-388).
//!
//! The ruling evaluates the model, carries each decision and builds the engine frame.
//! A PASS needs the model and the run proof. The HTML page presents the same frame.
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
//! use archkeel_report::{Ruling, Status};
//! fn ruling(previous: Ruling) -> Ruling {
//!     Ruling { status: Status::Pass, ..previous }
//! }
//! ```
//!
//! R8. A decided mark without the run proof: its module is private to the report (E0603).
//!
//! ```compile_fail,E0603
//! use archkeel_report::Status;
//! fn decided() -> archkeel_report::report::Decided {
//!     archkeel_report::report::Decided {
//!         status: Status::Pass, pass: None, observation: Status::Pass, rules: Vec::new()
//!     }
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
//! a part with a key of the ruling is refused when it runs (E0603).
//!
//! ```compile_fail,E0603
//! fn frame() -> archkeel_report::engine_frame::EngineFrame {
//!     archkeel_report::engine_frame::EngineFrame { bytes: br#"{"status": "PASS"}"#.to_vec() }
//! }
//! ```

#![deny(unreachable_pub)]

mod construct;
pub use construct::construct_row;

#[cfg(test)]
mod construct_replay_tests;

mod beyond;
mod build_error;
mod edge_links;
mod engine_frame;
mod head;
mod kind;
mod report;
mod ruling;
mod status;
mod violation_detail;
mod why;

#[cfg(test)]
pub(crate) use build_error::BuildError;
pub use engine_frame::page;
#[cfg(test)]
pub(crate) use engine_frame::FrameError;
#[cfg(test)]
pub(crate) use head::RuleVerdict;
pub use head::Status;
pub use ruling::{rule, rule_with_edge_links, Explain, Named, RuleReasons, Ruling};
pub use status::system_status;
#[cfg(test)]
pub(crate) use status::Unexplained;

#[cfg(test)]
mod run_tests;
