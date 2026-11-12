// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The status rule of AD-361 point 4 and the rule that each status other than PASS has a row
//! that explains it (point 5), and that a PASS carries the parts that it depends on (AD-371). Both read only the rows of the payload, so a reader can recompute
//! them, and the builder and the check use the same two functions.

use std::fmt;

use crate::codes::{Relation, UnknownSource};
use crate::head::{RuleVerdict, Status};
use crate::payload::Payload;

/// The status that the rows give.
///
/// 1. No Target: UNKNOWN. 2. A violation row: FAIL, unless the observation is incomplete and a
///    diagnostic row revokes the proofs. 3. An incomplete observation: UNKNOWN. 4. A rule with an
///    undecided position or an UNKNOWN verdict: UNKNOWN. 5. Else PASS.
pub(crate) fn status_of(payload: &Payload) -> Status {
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
    let failed = !payload.violations.kind.is_empty() && !revoked;
    let open = payload.rules.iter().any(rule_open);
    run_status(run.target, failed, complete, open)
}

/// The status rule of AD-361 point 4 over its four inputs. `status_of` and the engine frame
/// (`ruling::rule`) both use it, so the report has one status rule (#1073 item 4, AD-388).
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
    /// A PASS status or a PASS observation in a payload that does not carry a part that a PASS
    /// depends on (`PASS_NEEDS`): the rows of that part were not seen.
    PassWithoutPart,
}

/// The relations that a PASS depends on. Without `imports` and `reexports` the payload has no
/// edges and no crossings, so no edge rule, permission or cycle was seen; without `variants`
/// the units are not complete. The other relations of `run.not_carried` (calls, references,
/// implements, uses_type, fields, signatures, code_lines, contract_lines) are display parts:
/// every 2.0 payload leaves them out, and the evaluator decides its rules without them.
pub const PASS_NEEDS: [Relation; 3] = [Relation::Imports, Relation::Reexports, Relation::Variants];

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
            Unexplained::PassWithoutPart => {
                "a PASS status or observation does not carry imports, reexports and variants"
            }
        })
    }
}

/// Each break of AD-361 point 5 for the stated status of the payload.
pub(crate) fn unexplained(payload: &Payload, status: Status) -> Vec<Unexplained> {
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
    let pass = status == Status::Pass || payload.run.observation == Status::Pass;
    let missing = payload
        .run
        .not_carried
        .iter()
        .any(|code| code.known().is_some_and(|r| PASS_NEEDS.contains(&r)));
    if pass && missing {
        found.push(Unexplained::PassWithoutPart);
    }
    found
}
