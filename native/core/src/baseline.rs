// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The two-way compare of a run with a baseline file (AD-546).
//!
//! The file holds what a person accepted: violations, measurement budgets and, from schema 1.4.0,
//! the UNKNOWN entries. Each difference in either direction is red: a thing that the run has and
//! the file lacks is new, and a thing that the file has and the run lacks is stale. A stale file is
//! red so that the accepted set cannot grow wider than the code.
//!
//! The compare never changes a status. A rule with an accepted UNKNOWN stays UNKNOWN, and the exit
//! code stays 2 while the run has any UNKNOWN. Only a run with no UNKNOWN and no difference is 0.
//! A baseline cannot accept a refused part of the run (`Gaps::unacceptable`).

use std::collections::BTreeMap;

use archkeel_contract::policy::{budget_word, BaselineBudget, BaselineRole, ValidationBaseline};
use archkeel_contract::BudgetName;
use schemars::JsonSchema;
use serde::Serialize;

use crate::gap_key::{Gaps, Key};

/// One violation as the baseline names it: the rules and the subjects, sorted, and the roles.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) struct Violation {
    pub(crate) rules: Vec<String>,
    pub(crate) subjects: Vec<String>,
    pub(crate) roles: Vec<(String, String)>,
}

/// What the run has, for the compare and for the writer.
#[derive(Debug, Default)]
pub(crate) struct Observed {
    pub(crate) gaps: Gaps,
    pub(crate) violations: BTreeMap<Violation, u64>,
    pub(crate) budgets: Budgets,
    /// True when the run status is UNKNOWN, whatever the keys say. A status without a key must
    /// still keep the exit code at 2.
    pub(crate) unknown_status: bool,
}

/// The violations of the file by identity: the count and the roles.
type Accepted<'a> = BTreeMap<(&'a [String], &'a [String]), (u64, &'a [BaselineRole])>;

/// The measured budgets of a run. `None` is not measured: never read as 0 (AD-97).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) struct Budgets {
    pub(crate) cycle_edges: Option<u64>,
    pub(crate) private_crossings: Option<u64>,
}

/// One difference between the run and the file.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, JsonSchema)]
pub(crate) struct Difference {
    pub(crate) what: &'static str,
    pub(crate) kind: String,
    pub(crate) subject: String,
    pub(crate) reason: String,
    pub(crate) run: u64,
    pub(crate) file: u64,
}

/// A part of the baseline that the core names and does not decide.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, JsonSchema)]
pub(crate) struct Named {
    pub(crate) kind: &'static str,
    pub(crate) subject: String,
    pub(crate) reason: String,
}

/// The result of the compare. `exit_code` is the exit code of the command.
#[derive(Debug, Default, PartialEq, Eq, Serialize, JsonSchema)]
pub(crate) struct Compared {
    pub(crate) state: &'static str,
    pub(crate) exit_code: u8,
    /// The distinct entries (kind, subject, reason) that the file and the run share.
    pub(crate) accepted_entries: u64,
    /// The items behind them: an entry with a count of 3 is 3 items.
    pub(crate) accepted_unknowns: u64,
    pub(crate) new: Vec<Difference>,
    pub(crate) gone: Vec<Difference>,
    pub(crate) gaps: Vec<Named>,
    /// The rule rows whose every key the file accepts. The row stays UNKNOWN; the report says
    /// "accepted" beside it.
    pub(crate) accepted_rules: Vec<String>,
}

/// Release 4.0.1 measured these three with its own analyzer; a file of an older schema holds its
/// numbers, and the core does not compare them with its own (the schema is the measure).
const OTHER_ANALYZER: [BudgetName; 3] = [
    BudgetName::CallsUnresolved,
    BudgetName::TypingPositions,
    BudgetName::UntypedPrivateAccesses,
];

/// The run against the file, in both directions.
pub(crate) fn compare(file: &ValidationBaseline, run: &Observed) -> Compared {
    let mut found = Compared::default();
    if !run.gaps.unacceptable.is_empty() {
        for part in &run.gaps.unacceptable {
            found.gaps.push(Named {
                kind: "baseline.not_compared",
                subject: "the run".to_owned(),
                reason: format!("a baseline cannot accept a refused part of the run: {part}"),
            });
        }
        found.state = "not_compared";
        // A refused part cannot be compared. Exit 2 with a baseline means that every UNKNOWN is
        // accepted, so a refusal exits 1: CE treats exit 2 as green (AD-546).
        found.exit_code = 1;
        return found;
    }
    violations(file, run, &mut found);
    budgets(file, run, &mut found);
    unknowns(file, run, &mut found);
    let drift = !found.new.is_empty() || !found.gone.is_empty();
    let unknown = !run.gaps.keys.is_empty() || !found.gaps.is_empty() || run.unknown_status;
    found.state = if drift { "drift" } else { "current" };
    found.exit_code = match (drift, unknown) {
        (true, _) => 1,
        (false, true) => 2,
        (false, false) => 0,
    };
    found
}

fn violations(file: &ValidationBaseline, run: &Observed, found: &mut Compared) {
    let accepted: Accepted<'_> = file
        .violations()
        .iter()
        .map(|item| {
            let print = item.fingerprint();
            (
                (print.rules().as_slice(), print.subjects().as_slice()),
                (*item.count(), item.roles().as_slice()),
            )
        })
        .collect();
    let mut seen = Vec::new();
    for (item, count) in &run.violations {
        let print = (item.rules.as_slice(), item.subjects.as_slice());
        seen.push(print);
        let (file_count, roles) = accepted.get(&print).copied().unwrap_or((0, &[]));
        let moved = !roles.is_empty()
            && file_count == *count
            && roles
                .iter()
                .map(|role| (role.source().clone(), role.target().clone()))
                .collect::<Vec<_>>()
                != item.roles;
        if *count > file_count || moved {
            found.new.push(violation(item, *count, file_count, moved));
        } else if *count < file_count {
            found.gone.push(violation(item, *count, file_count, false));
        }
    }
    for (print, (count, _)) in &accepted {
        if !seen.contains(print) {
            let item = Violation {
                rules: print.0.to_vec(),
                subjects: print.1.to_vec(),
                roles: Vec::new(),
            };
            found.gone.push(violation(&item, 0, *count, false));
        }
    }
}

fn violation(item: &Violation, run: u64, file: u64, moved: bool) -> Difference {
    Difference {
        what: "violation",
        kind: "violation".to_owned(),
        subject: format!("{} | {}", item.rules.join(" "), item.subjects.join(" ")),
        reason: if moved { "direction differs" } else { "" }.to_owned(),
        run,
        file,
    }
}

fn budgets(file: &ValidationBaseline, run: &Observed, found: &mut Compared) {
    let current = file.unknowns().is_some();
    for budget in file.budgets() {
        let (name, ceiling) = match budget {
            BaselineBudget::Scalar { name, value } => (*name, *value),
            BaselineBudget::Names { key, .. } => {
                found.gaps.push(unmeasured("name budget", key));
                continue;
            }
        };
        let measured = match name {
            BudgetName::CycleEdges => Some(run.budgets.cycle_edges),
            BudgetName::PrivateCrossings => Some(run.budgets.private_crossings),
            _ => None,
        };
        let word = budget_word(name);
        match measured {
            Some(Some(value)) => compare_budget(word, value, ceiling, found),
            Some(None) => found
                .gaps
                .push(unmeasured(word, "the run does not measure it")),
            None if !current && OTHER_ANALYZER.contains(&name) => found.gaps.push(Named {
                kind: "baseline.budget_of_older_schema",
                subject: word.to_owned(),
                reason: "release 4.0.1 measured it with its own analyzer; write the file again \
                         with --write-baseline"
                    .to_owned(),
            }),
            None => found
                .gaps
                .push(unmeasured(word, "this core does not measure it")),
        }
    }
}

fn unmeasured(subject: &str, why: &str) -> Named {
    Named {
        kind: "budget.unmeasured",
        subject: subject.to_owned(),
        reason: why.to_owned(),
    }
}

fn compare_budget(name: &str, run: u64, file: u64, found: &mut Compared) {
    let difference = |reason: &str| Difference {
        what: "budget",
        kind: "budget".to_owned(),
        subject: name.to_owned(),
        reason: reason.to_owned(),
        run,
        file,
    };
    if run > file {
        found.new.push(difference("above the baseline"));
    } else if run < file {
        found.gone.push(difference("below the baseline"));
    }
}

fn unknowns(file: &ValidationBaseline, run: &Observed, found: &mut Compared) {
    // A file of schema 1.0.0 to 1.3.0 has no list: the compare is off, as in release 4.0.1.
    let Some(accepted) = file.unknowns().as_ref() else {
        return;
    };
    let file_counts: BTreeMap<Key, u64> = accepted
        .iter()
        .map(|item| {
            let key = Key {
                kind: item.kind().clone(),
                subject: item.subject().clone(),
                reason: item.reason().clone(),
            };
            (key, *item.count())
        })
        .collect();
    found.accepted_rules = run
        .gaps
        .by_rule
        .iter()
        .filter(|(_, keys)| {
            keys.iter().all(|key| {
                file_counts.get(key).copied().unwrap_or(0)
                    >= run.gaps.keys.get(key).copied().unwrap_or(0)
            })
        })
        .map(|(rule, _)| rule.clone())
        .collect();
    for (key, run_count) in &run.gaps.keys {
        let file_count = file_counts.get(key).copied().unwrap_or(0);
        let shared = (*run_count).min(file_count);
        found.accepted_unknowns += shared;
        found.accepted_entries += u64::from(shared > 0);
        if *run_count > file_count {
            found.new.push(entry(key, *run_count, file_count));
        }
    }
    for (key, file_count) in &file_counts {
        let run_count = run.gaps.keys.get(key).copied().unwrap_or(0);
        if run_count < *file_count {
            found.gone.push(entry(key, run_count, *file_count));
        }
    }
}

fn entry(key: &Key, run: u64, file: u64) -> Difference {
    Difference {
        what: "unknown",
        kind: key.kind.clone(),
        subject: key.subject.clone(),
        reason: key.reason.clone(),
        run,
        file,
    }
}

#[cfg(test)]
#[path = "baseline_tests.rs"]
mod tests;
