// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The baseline part of the frame (AD-546): what the run has, the compare with the file, and the
//! bytes that `--write-baseline` writes.
//!
//! The core reads no file. `scan.rs` reads the baseline bytes through the same safe reader as
//! the inside contracts, and this module gets the checked value or the reason that it is not one.
//! A baseline that cannot be read or checked is red (exit 1) and names the entry: it is never a
//! silent "nothing accepted". CE treats exit 2 as green, so a damaged file must not give 2.

use std::collections::BTreeMap;

use archkeel_contract::policy::{
    baseline_bytes, AcceptedUnknown, BaselineBudget, BaselineRole, BaselineViolation,
    ValidationBaseline,
};
use archkeel_contract::BudgetName;
use archkeel_model::Graph;
use archkeel_report::{RuleReasons, Ruling, Status};
use archkeel_store::Ingested;
use serde::Serialize;

use crate::baseline::{self, Budgets, Compared, Observed, Violation};
use crate::gap_key;

/// What a request asks of the baseline: the file that it reads and whether it writes one.
pub(crate) struct Input {
    /// The path as the request named it, for the messages.
    pub(crate) path: Option<String>,
    /// The checked file, or why it is not one. `None` when the request names no file.
    pub(crate) file: Option<Result<ValidationBaseline, String>>,
    /// Write the baseline of this run (`--write-baseline`).
    pub(crate) write: bool,
}

/// The part of the frame. `file` holds the bytes to write, as text.
#[derive(Debug, Serialize, schemars::JsonSchema)]
pub(crate) struct Part {
    #[serde(flatten)]
    compared: Compared,
    #[serde(skip_serializing_if = "Option::is_none")]
    file: Option<String>,
}

/// One gap of the result, with the word that the shell reads (AD-546).
#[derive(Debug, Serialize, schemars::JsonSchema)]
pub(crate) struct GapRow {
    kind: &'static str,
    subject: String,
    reason: String,
}

/// The gaps of the rules without a decision, each with its kind from the typed reason.
pub(crate) fn gap_rows(ruling: &Ruling) -> Vec<GapRow> {
    match ruling.unsupported() {
        RuleReasons::All(text) => vec![GapRow {
            kind: ruling.contract_kind().unwrap_or("other"),
            subject: "the whole contract".to_owned(),
            reason: text.clone(),
        }],
        RuleReasons::Each(rules) => rules
            .iter()
            .map(|(rule, text)| GapRow {
                kind: ruling
                    .causes()
                    .get(rule)
                    .map_or("other", archkeel_model::gap_kind),
                subject: rule.clone(),
                reason: text.clone(),
            })
            .collect(),
    }
}

/// The measured budgets. A run measures them only when each selected file was read and parsed.
/// A hidden edge (a dynamic import, an unresolved name) is not a number here: it is an entry of
/// the UNKNOWN list, and a new one is red, so a ceiling over the proven edges hides nothing.
pub(crate) fn budgets(graph: &Graph, reply: &Ingested) -> Budgets {
    let coverage = &reply.reply().facts.coverage;
    let selected = u64::try_from(coverage.selected_files.len()).unwrap_or(u64::MAX);
    if selected == 0 || coverage.files_read != selected || coverage.files_parsed != selected {
        return Budgets::default();
    }
    let cycle_edges = graph
        .cycles()
        .iter()
        .map(|cycle| u64::try_from(cycle.internal_edges().len()).unwrap_or(u64::MAX))
        .sum();
    let private_crossings = graph
        .imports()
        .iter()
        .filter(|import| {
            import
                .symbol()
                .is_some_and(|symbol| symbol.starts_with('_'))
                && import.source_package() != import.target_package()
        })
        .count();
    Budgets {
        cycle_edges: Some(cycle_edges),
        private_crossings: u64::try_from(private_crossings).ok(),
    }
}

/// The rule and the sorted subjects of one violation.
type Identity = (String, Vec<String>);

/// The count of equal violations and the directions that they name.
#[derive(Default)]
struct Tally {
    count: u64,
    roles: Vec<(String, String)>,
}

/// The violations of the ruling as the baseline names them: one entry for each identity, with the
/// count of equal ones and the directions that they name.
fn violations(ruling: &Ruling) -> BTreeMap<Violation, u64> {
    let mut found: BTreeMap<Identity, Tally> = BTreeMap::new();
    for (rule, source, target) in ruling.violation_rows() {
        let mut subjects = vec![source.to_owned()];
        let mut role = None;
        if let Some(target) = target {
            subjects.push(target.to_owned());
            role = Some((source.to_owned(), target.to_owned()));
        }
        subjects.sort();
        let entry = found.entry((rule.to_owned(), subjects)).or_default();
        entry.count += 1;
        entry.roles.extend(role);
    }
    found
        .into_iter()
        .map(|((rule, subjects), mut tally)| {
            tally.roles.sort();
            tally.roles.dedup();
            let item = Violation {
                rules: vec![rule],
                subjects,
                roles: tally.roles,
            };
            (item, tally.count)
        })
        .collect()
}

/// What the run has: the keys, the violations and the measured budgets.
pub(crate) fn observed(
    ruling: &Ruling,
    reply: Option<&Ingested>,
    graph: Option<&Graph>,
    refusals: Vec<String>,
) -> Observed {
    let mut gaps = gap_key::of_run(ruling, reply);
    gaps.unacceptable.extend(refusals);
    Observed {
        gaps,
        violations: violations(ruling),
        budgets: graph
            .zip(reply)
            .map_or_else(Budgets::default, |(graph, reply)| budgets(graph, reply)),
        unknown_status: ruling.decided().status() == Status::Unknown,
    }
}

/// A file of schema 1.0.0 to 1.3.0 is from release 4.0.1: say so once, with the one command that
/// migrates it, and name each section that this core does not read from it (AD-546, #1326). The
/// named gap holds the exit code at 2, so the old file is never a silent green.
fn with_migration(
    mut compared: Compared,
    file: &ValidationBaseline,
    path: Option<&str>,
) -> Compared {
    if file.unknowns().is_some() {
        return compared;
    }
    compared.gaps.insert(
        0,
        baseline::Named {
            kind: "baseline.older_schema",
            subject: path.unwrap_or("").to_owned(),
            reason: format!(
                "this file is from release 4.0.1 (schema before 1.4.0). It lists no accepted \
                 UNKNOWN, so none is accepted. Its budgets calls_unresolved, typing_positions and \
                 untyped_private_accesses are not compared, and the amendment file of the project \
                 is not read. Write it again once: archkeel validate --write-baseline {}",
                path.unwrap_or("<file>")
            ),
        },
    );
    if compared.exit_code == 0 {
        compared.exit_code = 2;
    }
    compared
}

/// The part of the frame for the request.
pub(crate) fn build(input: Input, run: &Observed) -> Part {
    let compared = match &input.file {
        Some(Ok(file)) => with_migration(baseline::compare(file, run), file, input.path.as_deref()),
        Some(Err(why)) => invalid(input.path.as_deref(), why),
        None => Compared {
            state: "written",
            ..Compared::default()
        },
    };
    if !input.write {
        return Part {
            compared,
            file: None,
        };
    }
    if !run.gaps.unacceptable.is_empty() {
        let mut refused = baseline::compare(&empty(), run);
        refused.state = "not_written";
        // A write alone has no file to fail: the refused run keeps the exit code of its status.
        refused.exit_code = if run.unknown_status { 2 } else { 1 };
        return Part {
            compared: refused,
            file: None,
        };
    }
    // A write without a file compares the run with its own output: no difference, and the exit
    // code is the one that `--baseline` gives for the same tree.
    let compared = match input.file {
        None => Compared {
            exit_code: own_exit(run),
            // The file that this run writes holds these entries and items.
            accepted_entries: u64::try_from(run.gaps.keys.len()).unwrap_or(u64::MAX),
            accepted_unknowns: run.gaps.keys.values().sum(),
            ..compared
        },
        Some(_) => compared,
    };
    Part {
        compared,
        file: Some(written(run)),
    }
}

fn own_exit(run: &Observed) -> u8 {
    if run.gaps.keys.is_empty() && !run.unknown_status {
        0
    } else {
        2
    }
}

fn empty() -> ValidationBaseline {
    ValidationBaseline::of_run(Vec::new(), Vec::new(), Vec::new())
}

/// A file that cannot be read or checked is red and names why: exit 1, never 2 and never 0.
fn invalid(path: Option<&str>, why: &str) -> Compared {
    Compared {
        state: "invalid",
        exit_code: 1,
        gaps: vec![baseline::Named {
            kind: "baseline.invalid",
            subject: path.unwrap_or("").to_owned(),
            reason: why.to_owned(),
        }],
        ..Compared::default()
    }
}

/// The bytes of the baseline of this run: schema 1.4.0 in the canonical form of the writer.
fn written(run: &Observed) -> String {
    let violations = run
        .violations
        .iter()
        .map(|(item, count)| {
            let roles = item
                .roles
                .iter()
                .map(|(source, target)| BaselineRole::new(source.clone(), target.clone()))
                .collect();
            BaselineViolation::new(item.rules.clone(), item.subjects.clone(), *count, roles)
        })
        .collect();
    let budgets = [
        (BudgetName::CycleEdges, run.budgets.cycle_edges),
        (BudgetName::PrivateCrossings, run.budgets.private_crossings),
    ]
    .into_iter()
    .filter_map(|(name, value)| {
        Some(BaselineBudget::Scalar {
            name,
            value: value?,
        })
    })
    .collect();
    let unknowns = run
        .gaps
        .keys
        .iter()
        .filter_map(|(key, count)| {
            AcceptedUnknown::new(
                key.kind.clone(),
                key.subject.clone(),
                key.reason.clone(),
                *count,
            )
            .ok()
        })
        .collect();
    let baseline = ValidationBaseline::of_run(violations, budgets, unknowns);
    String::from_utf8_lossy(&baseline_bytes(&baseline)).into_owned()
}

#[cfg(test)]
#[path = "baseline_frame_tests.rs"]
mod tests;
