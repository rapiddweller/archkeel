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
use archkeel_model::{Graph, Hygiene, Measures, Reason};
use archkeel_report::{RuleReasons, Ruling, Status};
use archkeel_store::Ingested;
use serde::Serialize;

use crate::baseline::{self, BaselineState, Budgets, Compared, Observed, Violation};
use crate::gap_key;

/// What a request asks of the baseline (AD-731). `path` is the path of the file to compare with,
/// as the request named it, and `file` is the checked file or why it is not one.
pub(crate) enum Input {
    /// `--baseline FILE`: compare the run with the file.
    Compare {
        path: String,
        file: Result<ValidationBaseline, String>,
    },
    /// `--write-baseline FILE` alone: write the baseline of this run.
    Write,
    /// Both: compare with one file and write the baseline of this run to another.
    CompareAndWrite {
        path: String,
        file: Result<ValidationBaseline, String>,
    },
}

/// True when the request holds the budgets of the run against a baseline: it compares with a
/// file that passed the check, or it writes the file from this run (AD-1090). A run with neither
/// has no baseline value for a declared budget.
pub(crate) fn holds_budgets(input: &Input) -> bool {
    !matches!(
        input,
        Input::Compare { file: Err(_), .. } | Input::CompareAndWrite { file: Err(_), .. }
    )
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
    /// What the user can do about the gap, when its kind has more than one answer (#1963).
    #[serde(skip_serializing_if = "Option::is_none")]
    action: Option<&'static str>,
}

/// The gaps of the rules without a decision, each with its kind from the typed reason.
pub(crate) fn gap_rows(ruling: &Ruling) -> Vec<GapRow> {
    match ruling.unsupported() {
        RuleReasons::All(text) => vec![GapRow {
            kind: ruling.contract_kind().unwrap_or("other"),
            subject: "the whole contract".to_owned(),
            reason: text.clone(),
            action: None,
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
                action: action_of(ruling.causes().get(rule)),
            })
            .collect(),
    }
}

/// The action word that the hygiene reason of a gap asks for, if it has one.
fn action_of(cause: Option<&Reason>) -> Option<&'static str> {
    match cause {
        Some(Reason::Hygiene(found)) => {
            let found: &Hygiene = found;
            found.action()
        }
        _ => None,
    }
}

/// The measured budgets. A run measures them only when each selected file was read and parsed.
/// The three counts of calls and types come from the same sum as the `measures` part, which is
/// absent when a row is missing or inconsistent: then they are not measured, never 0.
/// A hidden edge (a dynamic import, an unresolved name) is not a number here: it is an entry of
/// the UNKNOWN list, and a new one is red, so a ceiling over the proven edges hides nothing.
pub(crate) fn budgets(graph: &Graph, reply: &Ingested, counts: Option<&Measures>) -> Budgets {
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
        calls_unresolved: counts.map(|found| found.calls_unresolved),
        typing_positions: counts.map(|found| found.typing_positions),
        untyped_private_accesses: counts.map(|found| found.untyped_private_accesses),
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
    (declared, counts): (&[BudgetName], Option<&Measures>),
) -> Observed {
    let mut gaps = gap_key::of_run(ruling, reply);
    gaps.unacceptable.extend(refusals);
    Observed {
        gaps,
        violations: violations(ruling),
        declared: declared.to_vec(),
        budgets: graph
            .zip(reply)
            .map_or_else(Budgets::default, |(graph, reply)| {
                budgets(graph, reply, counts)
            }),
        unknown_status: ruling.decided().status() == Status::Unknown,
    }
}

/// A file of schema 1.0.0 to 1.3.0 is from release 4.0.1: say so once, with the one command that
/// migrates it, and name each section that this core does not read from it (AD-546, #1326). The
/// named gap holds the exit code at 2, so the old file is never a silent green.
fn with_migration(mut compared: Compared, file: &ValidationBaseline, path: &str) -> Compared {
    if file.unknowns().is_some() {
        return compared;
    }
    compared.gaps.insert(
        0,
        baseline::Named {
            kind: "baseline.older_schema",
            subject: path.to_owned(),
            reason: format!(
                "this file is from release 4.0.1 (schema before 1.4.0). It lists no accepted \
                 UNKNOWN, so none is accepted. Its budgets calls_unresolved, typing_positions and \
                 untyped_private_accesses are not compared, and the amendment file of the project \
                 is not read. Write it again once: archkeel validate --write-baseline {}",
                if path.is_empty() { "<file>" } else { path }
            ),
        },
    );
    if let BaselineState::Current { open } = &mut compared.state {
        *open = true;
    }
    compared
}

/// The part of the frame for the request.
pub(crate) fn build(input: Input, run: &Observed) -> Part {
    match input {
        Input::Compare { path, file } => Part {
            compared: compared(&path, &file, run),
            file: None,
        },
        Input::Write => write(run, None),
        Input::CompareAndWrite { path, file } => write(run, Some(compared(&path, &file, run))),
    }
}

fn compared(path: &str, file: &Result<ValidationBaseline, String>, run: &Observed) -> Compared {
    match file {
        Ok(file) => with_migration(baseline::compare(file, run), file, path),
        Err(why) => invalid(path, why),
    }
}

/// The part of a request that writes: the bytes of this run, or `NotWritten` for a refused part.
fn write(run: &Observed, compared: Option<Compared>) -> Part {
    if !run.gaps.unacceptable.is_empty() {
        let mut refused = baseline::compare(&empty(), run);
        // A write alone keeps the exit code of the run status; a write that also compares has
        // compared nothing and exits 1, because exit 2 with a baseline means all accepted.
        refused.state = BaselineState::NotWritten {
            compared: compared.is_some(),
            open: run.unknown_status,
        };
        return Part {
            compared: refused,
            file: None,
        };
    }
    // A write without a file compares the run with its own output: no difference, and the exit
    // code is the one that `--baseline` gives for the same tree.
    // A declared budget that the run cannot measure is not in the file: the run stays open, so a
    // write cannot exit 0 for a budget that nothing checks.
    let unmeasured = run.unmeasured_declared();
    let compared = compared.unwrap_or_else(|| Compared {
        // The file that this run writes holds these entries and items.
        accepted_entries: u64::try_from(run.gaps.keys.len()).unwrap_or(u64::MAX),
        accepted_unknowns: run.gaps.keys.values().sum(),
        gaps: unmeasured.clone(),
        ..Compared::of(BaselineState::Written {
            open: !run.gaps.keys.is_empty() || run.unknown_status || !unmeasured.is_empty(),
        })
    });
    Part {
        compared,
        file: Some(written(run)),
    }
}

fn empty() -> ValidationBaseline {
    ValidationBaseline::of_run(Vec::new(), Vec::new(), Vec::new())
}

/// A file that cannot be read or checked is red and names why: exit 1, never 2 and never 0.
fn invalid(path: &str, why: &str) -> Compared {
    Compared {
        gaps: vec![baseline::Named {
            kind: "baseline.invalid",
            subject: path.to_owned(),
            reason: why.to_owned(),
        }],
        ..Compared::of(BaselineState::Invalid)
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
        (BudgetName::CallsUnresolved, run.budgets.calls_unresolved),
        (BudgetName::TypingPositions, run.budgets.typing_positions),
        (
            BudgetName::UntypedPrivateAccesses,
            run.budgets.untyped_private_accesses,
        ),
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
