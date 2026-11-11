// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `Report` frame: a payload that keeps the status rule and the explaining rows (AD-371).
//!
//! A `Report` exists only in two ways, and both run the check of this crate:
//!
//! - `Report<Decided>` from `build`: the outcome of the evaluator and the rows of the model. Its
//!   status, observation and rule verdicts come from a `Decision` of the model, so no other crate
//!   writes a PASS (AD-363 point 4).
//! - `Report<Recorded>` from `Report::read`: canonical bytes that pass the check. Its verdicts are
//!   read bytes; a recorded report never becomes a decided one.
//!
//! The fields are private, so a payload that breaks a rule cannot become a `Report`:
//!
//! ```compile_fail
//! fn forge(payload: archkeel_report::Payload) -> archkeel_report::Report<archkeel_report::Recorded> {
//!     archkeel_report::Report { payload, source: archkeel_report::Recorded(()) }
//! }
//! ```
//!
//! A decoded payload has no way to a decided report:
//!
//! ```compile_fail
//! fn promote(
//!     report: archkeel_report::Report<archkeel_report::Recorded>,
//! ) -> archkeel_report::Report<archkeel_report::Decided> {
//!     report.into()
//! }
//! ```

use std::fmt;

use archkeel_model::Decision;

use crate::check::problems;
use crate::payload::{DecodeError, Payload};
use crate::problem::Problem;

/// The mark of a report read from bytes.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Recorded(());

/// The mark of a report built from the Decision of the evaluator. It keeps that Decision.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Decided {
    pub(crate) status: Decision,
    pub(crate) observation: Decision,
    pub(crate) rules: Vec<(String, Option<Decision>)>,
}

impl Decided {
    /// The status of the run, as the evaluator decided it.
    pub fn status(&self) -> &Decision {
        &self.status
    }

    /// The completeness of the observation, as the evaluator decided it.
    pub fn observation(&self) -> &Decision {
        &self.observation
    }

    /// The Decision of one rule by id; `None` inside for a permission declaration.
    pub fn rule(&self, id: &str) -> Option<Option<&Decision>> {
        self.rules
            .iter()
            .find(|(rule, _)| rule == id)
            .map(|(_, decision)| decision.as_ref())
    }
}

/// A payload that passed the check, with the mark of where it comes from.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Report<S> {
    payload: Payload,
    source: S,
}

/// Why bytes are no `Report`.
#[derive(Debug)]
pub enum ReadError {
    /// The bytes are no canonical payload.
    Decode(DecodeError),
    /// The payload breaks the named rules.
    Check(Vec<Problem>),
}

impl fmt::Display for ReadError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ReadError::Decode(error) => write!(formatter, "{error}"),
            ReadError::Check(found) => {
                let texts: Vec<String> = found.iter().map(ToString::to_string).collect();
                write!(formatter, "the payload breaks: {}", texts.join("; "))
            }
        }
    }
}

impl Report<Recorded> {
    /// Read canonical payload bytes and check them.
    pub fn read(bytes: &[u8]) -> Result<Report<Recorded>, ReadError> {
        let payload = Payload::decode(bytes).map_err(ReadError::Decode)?;
        Report::checked(payload, Recorded(())).map_err(ReadError::Check)
    }
}

impl<S> Report<S> {
    /// Check a payload; the only maker of a `Report`.
    pub(crate) fn checked(payload: Payload, source: S) -> Result<Report<S>, Vec<Problem>> {
        let found = problems(&payload);
        if found.is_empty() {
            Ok(Report { payload, source })
        } else {
            Err(found)
        }
    }

    /// The payload.
    pub fn payload(&self) -> &Payload {
        &self.payload
    }

    /// Where the report comes from.
    pub fn source(&self) -> &S {
        &self.source
    }

    /// The canonical bytes.
    pub fn encode(&self) -> Result<Vec<u8>, serde_json::Error> {
        self.payload.encode()
    }
}
