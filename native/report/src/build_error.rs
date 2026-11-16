// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Why the engine ruling cannot be built.

use std::fmt;

use crate::status::Unexplained;
use archkeel_model::RunGap;

/// Why the engine ruling cannot be built.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum BuildError {
    /// An UNKNOWN rule has no reason, or another verdict has one.
    ReasonMismatch {
        /// The rule id.
        rule: String,
    },
    /// A PASS has no run proof.
    PassWithoutProof(Option<RunGap>),
    /// A PASS belongs to another rule or model.
    ForeignPass {
        /// The rule id.
        rule: String,
    },
    /// A declaration does not belong to the model.
    ForeignDeclaration {
        /// The rule id.
        rule: String,
    },
    /// The status has no row that explains it.
    Unexplained(Vec<Unexplained>),
    /// Two outcomes have the same rule id.
    DuplicateRule {
        /// The rule id.
        rule: String,
    },
}

impl fmt::Display for BuildError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ReasonMismatch { rule } => write!(
                formatter,
                "rule {rule} has a reason that its verdict cannot have"
            ),
            Self::PassWithoutProof(gap) => write!(
                formatter,
                "the rows give PASS and the model gives no run proof: {gap:?}"
            ),
            Self::ForeignDeclaration { rule } => write!(
                formatter,
                "rule {rule} is no permission declaration of the model"
            ),
            Self::ForeignPass { rule } => write!(
                formatter,
                "rule {rule} holds a PASS of another rule or model"
            ),
            Self::Unexplained(found) => write!(formatter, "{found:?}"),
            Self::DuplicateRule { rule } => write!(formatter, "rule {rule} occurs twice"),
        }
    }
}
