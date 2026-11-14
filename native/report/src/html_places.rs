// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The violated places of the frame (AD-496): one place for each import that breaks a rule, however
//! many rules it breaks, and one place for each cycle. The page copies the rows of `details` and
//! the paths of `explain.cycles`. It groups them and decides nothing.

use std::collections::BTreeMap;

use super::frame::{CyclePath, Detail, Frame};

/// The most places that the page shows.
pub(super) const MAX_PLACES: usize = 100;

/// A rule that fails at a place, with its cause.
#[derive(Clone, Debug)]
pub(super) struct Violated {
    pub(super) rule: String,
    pub(super) cause: String,
}

#[derive(Clone, Debug)]
pub(super) enum Kind {
    /// An import, or a module with a finding of its own (`target` is `None`).
    Import {
        source: String,
        target: Option<String>,
        evidence: Vec<String>,
    },
    /// One cycle with its closed path.
    Cycle(Box<CyclePath>),
}

#[derive(Clone, Debug)]
pub(super) struct Place {
    pub(super) number: usize,
    pub(super) kind: Kind,
    pub(super) rules: Vec<Violated>,
}

/// The places of a frame and their exact total.
#[derive(Debug, Default)]
pub(super) struct Places {
    pub(super) shown: Vec<Place>,
    pub(super) total: usize,
}

fn is_cycle(detail: &Detail) -> bool {
    detail.cause == "dependency cycle"
}

/// The rules and the evidence that meet at one import.
#[derive(Default)]
struct Group {
    rules: Vec<Violated>,
    evidence: Vec<String>,
}

type Grouped = BTreeMap<(String, Option<String>), Group>;

impl Group {
    fn add(&mut self, violated: Violated, evidence: &[String]) {
        self.rules.push(violated);
        let new: Vec<&String> = evidence
            .iter()
            .filter(|id| !self.evidence.contains(id))
            .collect();
        self.evidence.extend(new.into_iter().cloned());
    }
}

impl Places {
    pub(super) fn of(frame: &Frame) -> Places {
        let mut imports = Grouped::new();
        let mut cycles: Vec<(CyclePath, Violated)> = Vec::new();
        for (rule, rows) in &frame.details {
            let listed = frame.explain.cycles.get(rule);
            for (index, row) in rows.iter().enumerate() {
                let violated = Violated {
                    rule: rule.clone(),
                    cause: row.cause.clone(),
                };
                // A cycle row has its closed path when the frame lists it; else it is one row.
                let path =
                    listed.and_then(|found| found.items.iter().find(|item| item.index == index));
                match path {
                    Some(path) if is_cycle(row) => cycles.push((path.clone(), violated)),
                    _ => imports
                        .entry((row.source.clone(), row.target.clone()))
                        .or_default()
                        .add(violated, &row.evidence),
                }
            }
        }
        let mut all: Vec<(Kind, Vec<Violated>)> = imports
            .into_iter()
            .map(|((source, target), group)| {
                let kind = Kind::Import {
                    source,
                    target,
                    evidence: group.evidence,
                };
                (kind, group.rules)
            })
            .collect();
        all.extend(
            cycles
                .into_iter()
                .map(|(path, violated)| (Kind::Cycle(Box::new(path)), vec![violated])),
        );
        let total = all.len();
        let shown = all
            .into_iter()
            .take(MAX_PLACES)
            .enumerate()
            .map(|(index, (kind, rules))| Place {
                number: index + 1,
                kind,
                rules,
            })
            .collect();
        Places { shown, total }
    }
}
