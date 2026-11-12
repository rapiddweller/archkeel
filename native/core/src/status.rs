// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The status of an engine frame and its explaining rows (AD-361 points 4 and 5, AD-378).
//!
//! The status follows from the rows of the frame only: a rule with violations gives FAIL; else a
//! rule that is UNKNOWN, a rule with a named reason or a named part of the run gives UNKNOWN;
//! else PASS. Each status other than PASS has a row that explains it: a FAIL rule has its
//! violations (L-23), and an UNKNOWN rule has its reason. A frame that breaks this is not
//! written: the core exits 2.

use std::collections::BTreeMap;

use crate::rules::RuleAnswer;

/// The words of the three statuses, as the frame writes them.
pub(crate) const PASS: &str = "PASS";
pub(crate) const FAIL: &str = "FAIL";
pub(crate) const UNKNOWN: &str = "UNKNOWN";

/// The status of a frame: its decided rules, and whether it names a reason or a part.
pub(crate) fn status(decided: &BTreeMap<String, [String; 2]>, named: bool) -> &'static str {
    let statuses = || decided.values().map(|[_, status]| status.as_str());
    if statuses().any(|status| status == FAIL) {
        FAIL
    } else if named || statuses().any(|status| status != PASS) {
        UNKNOWN
    } else {
        PASS
    }
}

/// The first rule whose status has no explaining row, or whose row does not fit its status.
pub(crate) fn unexplained(answer: &RuleAnswer) -> Option<String> {
    for (rule, [_, status]) in &answer.decided {
        let violations = answer.violations.get(rule).copied().unwrap_or(0);
        let reason = answer
            .explained
            .get(rule)
            .is_some_and(|why| !why.is_empty());
        let fits = match status.as_str() {
            FAIL => violations > 0 && !reason,
            UNKNOWN => violations == 0 && reason,
            PASS => violations == 0 && !reason,
            _ => false,
        };
        if !fits {
            return Some(format!(
                "the rule {rule} is {status} with {violations} violations and {} reason",
                if reason { "a" } else { "no" }
            ));
        }
    }
    let extra = answer
        .explained
        .keys()
        .chain(answer.violations.keys())
        .find(|rule| !answer.decided.contains_key(*rule));
    extra.map(|rule| format!("the rule {rule} has an explaining row but no status"))
}

#[cfg(test)]
#[path = "status_tests.rs"]
mod tests;
