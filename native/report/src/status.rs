// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The engine frame status rule and its unexplained outcomes.

use crate::head::Status;
use std::fmt;

/// The status rule of AD-361 point 4 over the four inputs of the engine ruling (AD-388).
pub(crate) fn run_status(target: bool, failed: bool, complete: bool, open: bool) -> Status {
    if !target {
        Status::Unknown
    } else if failed {
        Status::Fail
    } else if !complete || open {
        Status::Unknown
    } else {
        Status::Pass
    }
}

/// A status without the row that explains it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Unexplained {
    /// FAIL without a violation row.
    FailWithoutViolation,
    /// UNKNOWN without an explanation.
    UnknownWithoutRow,
}

impl fmt::Display for Unexplained {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Unexplained::FailWithoutViolation => "status FAIL has no violation row",
            Unexplained::UnknownWithoutRow => "status UNKNOWN has no row that explains it",
        })
    }
}

#[cfg(test)]
mod tests {
    use super::{run_status, Status};

    #[test]
    fn status_needs_a_target_and_a_complete_closed_run_for_pass() {
        assert_eq!(run_status(false, true, true, false), Status::Unknown);
        assert_eq!(run_status(true, true, false, true), Status::Fail);
        assert_eq!(run_status(true, false, false, false), Status::Unknown);
        assert_eq!(run_status(true, false, true, true), Status::Unknown);
        assert_eq!(run_status(true, false, true, false), Status::Pass);
    }
}
