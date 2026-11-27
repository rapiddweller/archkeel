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

use std::borrow::Cow;
use std::collections::{BTreeMap, BTreeSet};

use archkeel_contract::policy::{budget_word, BaselineBudget, BaselineRole, ValidationBaseline};
use archkeel_contract::BudgetName;
use schemars::{JsonSchema, Schema, SchemaGenerator};
use serde::{Serialize, Serializer};

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
    /// The budgets that the contract declares: a file of schema 1.4.0 must hold each one.
    pub(crate) declared: Vec<BudgetName>,
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
    pub(crate) calls_unresolved: Option<u64>,
    pub(crate) typing_positions: Option<u64>,
    pub(crate) untyped_private_accesses: Option<u64>,
}

impl Budgets {
    /// The measured value of a budget, or `None` when the run does not measure it.
    pub(crate) fn of(&self, name: BudgetName) -> Option<u64> {
        match name {
            BudgetName::CycleEdges => self.cycle_edges,
            BudgetName::PrivateCrossings => self.private_crossings,
            BudgetName::CallsUnresolved => self.calls_unresolved,
            BudgetName::TypingPositions => self.typing_positions,
            BudgetName::UntypedPrivateAccesses => self.untyped_private_accesses,
            _ => None,
        }
    }
}

impl Observed {
    /// One gap for each declared budget that the run does not measure: no file can hold it.
    pub(crate) fn unmeasured_declared(&self) -> Vec<Named> {
        let missing = self
            .declared
            .iter()
            .filter(|name| self.budgets.of(**name).is_none());
        missing
            .map(|name| unmeasured(budget_word(*name), "the run does not measure it"))
            .collect()
    }
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

/// How the run stands against the baseline file (AD-731). The state gives the word and the exit
/// code of the frame, so the two cannot disagree.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum BaselineState {
    /// Nothing differs. `open`: the run has an UNKNOWN, so it exits 2 and never 0.
    Current { open: bool },
    /// A thing differs in one direction or the other.
    Drift,
    /// The file cannot be read or checked.
    Invalid,
    /// A part of the run is refused, so nothing is compared.
    NotCompared,
    /// `--write-baseline` alone: the file holds this run. `open` as for `Current`.
    Written { open: bool },
    /// A part of the run is refused, so no file is written. `compared`: the request also
    /// compares with a file. `open`: the run status is UNKNOWN.
    NotWritten { compared: bool, open: bool },
}

impl BaselineState {
    /// The word of the state in the frame.
    pub(crate) fn word(self) -> &'static str {
        match self {
            Self::Current { .. } => "current",
            Self::Drift => "drift",
            Self::Invalid => "invalid",
            Self::NotCompared => "not_compared",
            Self::Written { .. } => "written",
            Self::NotWritten { .. } => "not_written",
        }
    }

    /// The exit code of the command. With a baseline, exit 2 means that every UNKNOWN is
    /// accepted, and CE treats it as green: a state that compares nothing exits 1 (AD-546).
    pub(crate) fn exit_code(self) -> u8 {
        match self {
            Self::Current { open: true } | Self::Written { open: true } => 2,
            Self::Current { open: false } | Self::Written { open: false } => 0,
            Self::Drift | Self::Invalid | Self::NotCompared => 1,
            Self::NotWritten { compared: true, .. } => 1,
            Self::NotWritten {
                compared: false,
                open,
            } => {
                if open {
                    2
                } else {
                    1
                }
            }
        }
    }
}

// The two keys that the state writes into the frame; the keys and their schema stay as they were.
#[derive(Serialize, JsonSchema)]
struct StateKeys {
    state: &'static str,
    exit_code: u8,
}

impl Serialize for BaselineState {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        StateKeys {
            state: self.word(),
            exit_code: self.exit_code(),
        }
        .serialize(serializer)
    }
}

impl JsonSchema for BaselineState {
    fn schema_name() -> Cow<'static, str> {
        StateKeys::schema_name()
    }

    fn inline_schema() -> bool {
        true
    }

    fn json_schema(generator: &mut SchemaGenerator) -> Schema {
        StateKeys::json_schema(generator)
    }
}

/// The result of the compare. The state gives the exit code of the command.
#[derive(Debug, PartialEq, Eq, Serialize, JsonSchema)]
pub(crate) struct Compared {
    #[serde(flatten)]
    pub(crate) state: BaselineState,
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

impl Compared {
    /// A result in `state` with no entry, no difference and no gap.
    pub(crate) fn of(state: BaselineState) -> Compared {
        Compared {
            state,
            accepted_entries: 0,
            accepted_unknowns: 0,
            new: Vec::new(),
            gone: Vec::new(),
            gaps: Vec::new(),
            accepted_rules: Vec::new(),
        }
    }
}

/// Release 4.0.1 measured these three with its own analyzer; a file of an older schema holds its
/// numbers, and the core does not compare them with its own (the schema is the measure). A file
/// of schema 1.4.0 holds the numbers of this core, and the compare reads them (AD-1090).
const OTHER_ANALYZER: [BudgetName; 3] = [
    BudgetName::CallsUnresolved,
    BudgetName::TypingPositions,
    BudgetName::UntypedPrivateAccesses,
];

/// The run against the file, in both directions.
pub(crate) fn compare(file: &ValidationBaseline, run: &Observed) -> Compared {
    let mut found = Compared::of(BaselineState::NotCompared);
    if !run.gaps.unacceptable.is_empty() {
        for part in &run.gaps.unacceptable {
            found.gaps.push(Named {
                kind: "baseline.not_compared",
                subject: "the run".to_owned(),
                reason: format!("a baseline cannot accept a refused part of the run: {part}"),
            });
        }
        // A refused part cannot be compared: `NotCompared` exits 1 (AD-546).
        return found;
    }
    violations(file, run, &mut found);
    budgets(file, run, &mut found);
    unknowns(file, run, &mut found);
    let drift = !found.new.is_empty() || !found.gone.is_empty();
    let unknown = !run.gaps.keys.is_empty() || !found.gaps.is_empty() || run.unknown_status;
    found.state = if drift {
        BaselineState::Drift
    } else {
        BaselineState::Current { open: unknown }
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
        let word = budget_word(name);
        if !current && OTHER_ANALYZER.contains(&name) {
            found.gaps.push(Named {
                kind: "baseline.budget_of_older_schema",
                subject: word.to_owned(),
                reason: "release 4.0.1 measured it with its own analyzer; write the file again \
                         with --write-baseline"
                    .to_owned(),
            });
            continue;
        }
        match run.budgets.of(name) {
            Some(value) => compare_budget(word, value, ceiling, found),
            None => found
                .gaps
                .push(unmeasured(word, "the run does not measure it")),
        }
    }
    for name in &run.declared {
        let held = file.budgets().iter().any(
            |budget| matches!(budget, BaselineBudget::Scalar { name: held, .. } if held == name),
        );
        if held {
            continue;
        }
        let word = budget_word(*name);
        // A declared budget without a ceiling is red, not a gap: exit 2 is green for CE, so
        // deleting the line from the file would hide a grown measure.
        match run.budgets.of(*name) {
            Some(value) => found.new.push(Difference {
                what: "budget",
                kind: "budget.unknown".to_owned(),
                subject: word.to_owned(),
                reason: "the contract declares this budget and the file holds no value for it"
                    .to_owned(),
                run: value,
                file: 0,
            }),
            None => found
                .gaps
                .push(unmeasured(word, "the run does not measure it")),
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
        let mut above = difference("above the baseline");
        above.kind = "budget.exceeded".to_owned();
        found.new.push(above);
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
    // A file of schema 1.4.0 names the first cause of each rule only: the causes beyond it are not compared,
    // so a file that a build wrote stays current for the same source (AD-1290).
    let held = |key: &Key, count: u64| -> u64 {
        match file.all_causes() {
            true => count,
            false => count.saturating_sub(run.gaps.beyond.get(key).copied().unwrap_or(0)),
        }
    };
    let run_keys: BTreeMap<&Key, u64> = run
        .gaps
        .keys
        .iter()
        .map(|(key, count)| (key, held(key, *count)))
        .filter(|(_, count)| *count > 0)
        .collect();
    found.accepted_rules = run
        .gaps
        .by_rule
        .iter()
        .filter(|(_, keys)| {
            keys.iter().all(|key| {
                file_counts.get(key).copied().unwrap_or(0)
                    >= held(key, run.gaps.keys.get(key).copied().unwrap_or(0))
            })
        })
        .map(|(rule, _)| rule.clone())
        .collect();
    let mut newer: Vec<(Key, u64, u64)> = Vec::new();
    let mut gone: Vec<(Key, u64, u64)> = Vec::new();
    for (key, run_count) in &run_keys {
        let file_count = file_counts.get(*key).copied().unwrap_or(0);
        let shared = (*run_count).min(file_count);
        found.accepted_unknowns += shared;
        found.accepted_entries += u64::from(shared > 0);
        if *run_count > file_count {
            newer.push(((*key).clone(), *run_count, file_count));
        }
    }
    for (key, file_count) in &file_counts {
        let run_count = run_keys.get(key).copied().unwrap_or(0);
        if run_count < *file_count {
            gone.push((key.clone(), run_count, *file_count));
        }
    }
    reworded(&run.gaps.reworded, &mut newer, &mut gone, found);
    found
        .new
        .extend(newer.iter().map(|(key, run, file)| entry(key, *run, *file)));
    found
        .gone
        .extend(gone.iter().map(|(key, run, file)| entry(key, *run, *file)));
}

/// A collector gap whose text changed and whose kind, subject and count did not is no drift (AD-1290).
/// Each surplus of the run is paired with a missing entry of the file of the same kind and subject, one
/// item for one item. What no pair absorbs stays new or gone. Only a key whose reason is the text of
/// a collector is paired; a typed reason is exact.
fn reworded(
    reworded: &BTreeSet<Key>,
    newer: &mut Vec<(Key, u64, u64)>,
    gone: &mut Vec<(Key, u64, u64)>,
    found: &mut Compared,
) {
    for (key, run_count, file_count) in newer.iter_mut() {
        if !reworded.contains(key) {
            continue;
        }
        let before = *file_count;
        for (other, run_other, file_other) in gone.iter_mut() {
            if (&other.kind, &other.subject) != (&key.kind, &key.subject) {
                continue;
            }
            let moved = (*run_count - *file_count).min(*file_other - *run_other);
            if moved == 0 {
                continue;
            }
            *file_count += moved;
            *run_other += moved;
            found.accepted_unknowns += moved;
        }
        // A key that the file did not hold is now one accepted entry; a key that matched exactly already was.
        found.accepted_entries += u64::from(before == 0 && *file_count > 0);
    }
    newer.retain(|(_, run, file)| run > file);
    gone.retain(|(_, run, file)| run < file);
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

#[cfg(test)]
#[path = "baseline_reworded_tests.rs"]
mod reworded_tests;

#[cfg(test)]
#[path = "baseline_causes_tests.rs"]
mod causes_tests;
