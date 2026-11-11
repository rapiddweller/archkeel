// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Why no `Report` can be built (AD-371).

use std::fmt;

use archkeel_model::Unsupported;

use crate::payload::MAX_BYTES;
use crate::problem::Problem;
use crate::status::Unexplained;

/// Why no `Report` can be built.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum BuildError {
    /// A table that the schema requires and cannot mark as not produced has no rows yet.
    NotProduced {
        table: &'static str,
        part: Unsupported,
    },
    /// A rule decides PASS without an evaluator receipt (AD-117).
    PassWithoutReceipt { rule: String },
    /// An UNKNOWN rule without `WhyUnknown`, or another verdict with one.
    ReasonMismatch { rule: String },
    /// The rows give PASS, and the model gives no PASS `Decision` (no scope proof).
    PassWithoutProof,
    /// A status other than PASS has no row that explains it (AD-361 point 5).
    Unexplained(Vec<Unexplained>),
    /// The frame breaks other rules of the check, such as the status rule.
    Invalid(Vec<Problem>),
    /// The canonical bytes are above the budget; the payload is never cut in silence.
    TooLarge { bytes: u64 },
    /// The bytes cannot be written.
    Encode(String),
}

impl fmt::Display for BuildError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            BuildError::NotProduced { table, part } => {
                write!(formatter, "the {table} table is not produced: {part}")
            }
            BuildError::ReasonMismatch { rule } => {
                write!(
                    formatter,
                    "rule {rule} has a reason that its verdict cannot have"
                )
            }
            BuildError::PassWithoutProof => {
                formatter.write_str("the rows give PASS and the model gives no PASS Decision")
            }
            BuildError::PassWithoutReceipt { rule } => {
                write!(formatter, "rule {rule} decides PASS without a receipt")
            }
            BuildError::Unexplained(found) => write!(formatter, "{found:?}"),
            BuildError::Invalid(found) => write!(formatter, "{found:?}"),
            BuildError::TooLarge { bytes } => {
                write!(
                    formatter,
                    "the payload has {bytes} bytes, above {MAX_BYTES}"
                )
            }
            BuildError::Encode(error) => formatter.write_str(error),
        }
    }
}
