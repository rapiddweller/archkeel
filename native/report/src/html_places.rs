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
    /// A class whose definition lies outside the modules of its placement rule.
    MisplacedClass {
        module: String,
        name: String,
        evidence: Vec<String>,
    },
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
    /// The places beyond the cut: the page draws none of them, but each count reads all places.
    pub(super) hidden: Vec<Kind>,
}

impl Places {
    /// Every place of the frame, shown or not, so that a count never reads the cut list.
    pub(super) fn every(&self) -> impl Iterator<Item = &Kind> {
        self.shown.iter().map(|p| &p.kind).chain(&self.hidden)
    }
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
    /// Add one row. A place lists each rule and cause once, also when several sites of the place
    /// break it (AD-668); the evidence of each site stays.
    fn add(&mut self, violated: Violated, evidence: &[String]) {
        let seen = self
            .rules
            .iter()
            .any(|old| old.rule == violated.rule && old.cause == violated.cause);
        if !seen {
            self.rules.push(violated);
        }
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
        let mut classes: BTreeMap<(String, String), Group> = BTreeMap::new();
        let mut cycles: Vec<(CyclePath, Violated)> = Vec::new();
        for (rule, rows) in &frame.details {
            let listed = frame.explain.cycles.get(rule);
            let placement = frame.rules.get(rule).is_some_and(|(kind, _)| {
                kind == crate::kind::word(archkeel_contract::RuleKind::SymbolPlacement)
            });
            for (index, row) in rows.iter().enumerate() {
                let violated = Violated {
                    rule: rule.clone(),
                    cause: row.cause.clone(),
                };
                // A cycle row has its closed path when the frame lists it; else it is one row.
                let path =
                    listed.and_then(|found| found.items.iter().find(|item| item.index == index));
                match (placement, &row.target, path) {
                    (true, Some(module), _) => classes
                        .entry((module.clone(), row.source.clone()))
                        .or_default()
                        .add(violated, &row.evidence),
                    (_, _, Some(path)) if is_cycle(row) => cycles.push((path.clone(), violated)),
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
        all.extend(classes.into_iter().map(|((module, name), group)| {
            (
                Kind::MisplacedClass {
                    module,
                    name,
                    evidence: group.evidence,
                },
                group.rules,
            )
        }));
        all.extend(
            cycles
                .into_iter()
                .map(|(path, violated)| (Kind::Cycle(Box::new(path)), vec![violated])),
        );
        let total = all.len();
        let hidden = all
            .iter()
            .skip(MAX_PLACES)
            .map(|(kind, _)| kind.clone())
            .collect();
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
        Places {
            shown,
            total,
            hidden,
        }
    }
}
