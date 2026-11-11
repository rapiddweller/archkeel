// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The status rule of AD-361 point 4 and the rule that each status other than PASS has a row
//! that explains it (point 5). Both read only the rows of the payload, so a reader can recompute
//! them, and the builder and the check use the same two functions.

use std::fmt;

use crate::codes::UnknownSource;
use crate::head::{RuleVerdict, Status};
use crate::payload::Payload;

/// The status that the rows give.
///
/// 1. No Target: UNKNOWN. 2. A violation row: FAIL, unless the observation is incomplete and a
///    diagnostic row revokes the proofs. 3. An incomplete observation: UNKNOWN. 4. A rule with an
///    undecided position or an UNKNOWN verdict: UNKNOWN. 5. Else PASS.
pub fn status_of(payload: &Payload) -> Status {
    let run = &payload.run;
    let complete = run.observation == Status::Pass;
    let unknowns = &payload.unknowns;
    let revoked = !complete
        && unknowns
            .source
            .iter()
            .zip(&unknowns.reason)
            .any(|(source, reason)| {
                source.is(UnknownSource::Diagnostic) && reason.known().is_some_and(|r| r.revokes())
            });
    if !run.target {
        return Status::Unknown;
    }
    if !payload.violations.kind.is_empty() && !revoked {
        return Status::Fail;
    }
    if !complete {
        return Status::Unknown;
    }
    if payload.rules.iter().any(rule_open) {
        return Status::Unknown;
    }
    Status::Pass
}

fn rule_open(rule: &crate::head::RuleResult) -> bool {
    rule.undecided > 0 || rule.verdict == RuleVerdict::Unknown
}

/// A status other than PASS without the row that explains it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Unexplained {
    /// FAIL without a violation row.
    FailWithoutViolation,
    /// A run without Target without an unknowns row of source `run`.
    NoTargetWithoutRunRow,
    /// An incomplete observation without a diagnostic or record row.
    IncompleteWithoutRow,
    /// UNKNOWN without an unknowns row and without an open rule row.
    UnknownWithoutRow,
}

impl fmt::Display for Unexplained {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Unexplained::FailWithoutViolation => "status FAIL has no violation row",
            Unexplained::NoTargetWithoutRunRow => {
                "a run without Target has no unknown row that says so"
            }
            Unexplained::IncompleteWithoutRow => {
                "an incomplete observation has no unknown row that explains it"
            }
            Unexplained::UnknownWithoutRow => "status UNKNOWN has no row that explains it",
        })
    }
}

/// Each break of AD-361 point 5 for the stated status of the payload.
pub fn unexplained(payload: &Payload, status: Status) -> Vec<Unexplained> {
    let sources = &payload.unknowns.source;
    let has = |wanted: UnknownSource| sources.iter().any(|source| source.is(wanted));
    let mut found = Vec::new();
    if status == Status::Fail && payload.violations.kind.is_empty() {
        found.push(Unexplained::FailWithoutViolation);
    }
    if !payload.run.target && !has(UnknownSource::Run) {
        found.push(Unexplained::NoTargetWithoutRunRow);
    }
    if payload.run.observation != Status::Pass
        && !has(UnknownSource::Diagnostic)
        && !has(UnknownSource::Record)
    {
        found.push(Unexplained::IncompleteWithoutRow);
    }
    let any_known_source = sources.iter().any(|source| source.known().is_some());
    if status == Status::Unknown && !any_known_source && !payload.rules.iter().any(rule_open) {
        found.push(Unexplained::UnknownWithoutRow);
    }
    found
}
