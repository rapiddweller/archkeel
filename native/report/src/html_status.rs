// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The statuses of the page (AD-730): the status that the frame states for the run, and the status
//! that a box, a cell or an edge of the Explorer shows. A box shows PASS only when the run decides
//! every rule: the run-level floor. The page decides no verdict; it only refuses to show PASS where
//! the frame does not decide one.

use std::collections::BTreeMap;

use serde::Serialize;

use super::atlas_tree::Tree;
use super::frame::Frame;
use crate::head::{RuleVerdict, Status};

/// The status that a box, a cell or an edge shows. The order is the order of `max`: FAIL is worse
/// than UNKNOWN, and UNKNOWN is worse than PASS.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize)]
pub(super) enum Shown {
    /// No violated place, no gap, and the run decides every rule.
    #[serde(rename = "PASS")]
    Pass,
    /// A gap holds it, or the run does not decide every rule.
    #[serde(rename = "UNKNOWN")]
    Unknown,
    /// A violated place lies inside.
    #[serde(rename = "FAIL")]
    Fail,
}

impl Shown {
    /// The word of the status, as the frame writes it.
    pub(super) fn word(self) -> &'static str {
        match self {
            Shown::Pass => "PASS",
            Shown::Unknown => "UNKNOWN",
            Shown::Fail => "FAIL",
        }
    }

    /// The class word of the status in the design system.
    pub(super) fn class(self) -> &'static str {
        match self {
            Shown::Pass => "pass",
            Shown::Unknown => "unknown",
            Shown::Fail => "fail",
        }
    }

    /// The status of the run as a badge shows it: a frame without a status is not decided.
    pub(super) fn of_run(status: Option<Status>) -> Shown {
        match status {
            Some(Status::Pass) => Shown::Pass,
            Some(Status::Fail) => Shown::Fail,
            Some(Status::Unknown) | None => Shown::Unknown,
        }
    }
}

/// The word of the run status in the heading and the title: `unavailable` without a status.
pub(super) fn run_word(status: Option<Status>) -> &'static str {
    match status {
        Some(status) => Shown::of_run(Some(status)).word(),
        None => "unavailable",
    }
}

/// The next step of a frame that states no status and no cause.
const NO_STATUS: &str =
    "The frame states no status and no cause. Run archkeel validate --verbose: it names the core and its reply.";

/// Why the run is open: the cause of the frame, or the next step when a frame without a status
/// names no cause either.
pub(super) fn cause(frame: &Frame) -> &str {
    match (frame.status, frame.cause.is_empty()) {
        (None, true) => NO_STATUS,
        (Some(_), _) | (None, false) => &frame.cause,
    }
}

/// The best status that a box, a cell or an edge may show in a run with this status and these
/// rules (AD-730). A PASS run and a FAIL run without an UNKNOWN rule decide every rule; any other
/// run decides no box as PASS, because a rule of the run that is not decided may break inside any
/// box.
fn floor(status: Option<Status>, mut verdicts: impl Iterator<Item = RuleVerdict>) -> Shown {
    match status {
        Some(Status::Pass) => Shown::Pass,
        Some(Status::Fail) if !verdicts.any(|v| v == RuleVerdict::Unknown) => Shown::Pass,
        Some(Status::Fail | Status::Unknown) | None => Shown::Unknown,
    }
}

/// The floor of the run and of each part of a system. A part is its own run with its own status
/// and rules (AD-616), so a box inside a part reads the floor of that part.
pub(super) struct Floors {
    run: Shown,
    parts: BTreeMap<String, Shown>,
}

impl Floors {
    pub(super) fn of(frame: &Frame) -> Floors {
        let verdicts = |rules: &[String]| -> Vec<RuleVerdict> {
            rules
                .iter()
                .map(|r| frame.rules.get(r).map_or(RuleVerdict::Unknown, |row| row.1))
                .collect()
        };
        Floors {
            run: floor(frame.status, frame.rules.values().map(|row| row.1)),
            parts: frame
                .parts
                .iter()
                .map(|p| {
                    let part = floor(p.status, verdicts(&p.rules).into_iter());
                    (format!("PART:{}", p.id), part)
                })
                .collect(),
        }
    }

    /// The floor at a box: the floor of the part that holds it, else the floor of the run.
    pub(super) fn at(&self, tree: &Tree, node: Option<usize>) -> Shown {
        node.and_then(|n| {
            tree.chain(n)
                .find_map(|i| self.parts.get(&tree.nodes[i].id))
        })
        .copied()
        .unwrap_or(self.run)
    }
}

/// The status of a box from its violated places and its gaps, under the floor of the run, and
/// the reason in one sentence.
pub(super) fn node_status(floor: Shown, fail: usize, unknown: usize) -> (Shown, String) {
    match (fail, unknown, floor) {
        (0, 0, Shown::Pass) => (Shown::Pass, "No violated place and no gap inside.".to_owned()),
        (0, 0, Shown::Unknown | Shown::Fail) => (
            Shown::Unknown,
            "No violated place and no gap inside, but the run is not decided: no rule is proven here. See Unknown.".to_owned(),
        ),
        (0, gaps, _) => (
            Shown::Unknown,
            format!("{gaps} gaps name a module inside: a rule cannot decide here."),
        ),
        (places, _, _) => (Shown::Fail, format!("{places} violated places inside.")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_transition_of_the_box_status() {
        let word = |floor, fail, unknown| node_status(floor, fail, unknown).0;
        assert_eq!(word(Shown::Pass, 0, 0), Shown::Pass);
        assert_eq!(word(Shown::Unknown, 0, 0), Shown::Unknown);
        assert_eq!(word(Shown::Pass, 0, 2), Shown::Unknown);
        assert_eq!(word(Shown::Unknown, 0, 2), Shown::Unknown);
        assert_eq!(word(Shown::Pass, 1, 2), Shown::Fail);
        assert_eq!(word(Shown::Unknown, 1, 0), Shown::Fail);
        assert!(Shown::Pass < Shown::Unknown && Shown::Unknown < Shown::Fail);
    }

    #[test]
    fn the_floor_is_pass_only_for_a_run_that_decides_every_rule() {
        let rules = |verdicts: &[RuleVerdict]| {
            let kind = String::new();
            verdicts
                .iter()
                .enumerate()
                .map(|(i, v)| (format!("R{i}"), (kind.clone(), *v)))
                .collect()
        };
        let frame = |status, verdicts: &[RuleVerdict]| Frame {
            status,
            rules: rules(verdicts),
            ..Frame::default()
        };
        use crate::head::RuleVerdict::{Fail, Pass, Unknown};
        let run = |status, verdicts: &[RuleVerdict]| Floors::of(&frame(status, verdicts)).run;
        assert_eq!(run(Some(Status::Pass), &[Pass]), Shown::Pass);
        assert_eq!(run(Some(Status::Fail), &[Fail, Pass]), Shown::Pass);
        assert_eq!(run(Some(Status::Fail), &[Fail, Unknown]), Shown::Unknown);
        assert_eq!(run(Some(Status::Unknown), &[Pass]), Shown::Unknown);
        assert_eq!(run(None, &[Pass]), Shown::Unknown);
        // A part reads its own status and rules; a rule that the frame does not state is open.
        let mut system = frame(Some(Status::Unknown), &[Pass, Unknown]);
        let part = |id: &str, status, rules: &[&str]| super::super::frame::Part {
            id: id.to_owned(),
            status: Some(status),
            rules: rules.iter().map(|r| (*r).to_owned()).collect(),
        };
        system.parts = vec![
            part("a", Status::Pass, &["R0"]),
            part("b", Status::Unknown, &["R1"]),
            part("c", Status::Fail, &["R0", "MISSING"]),
        ];
        let floors = Floors::of(&system);
        assert_eq!(floors.parts["PART:a"], Shown::Pass);
        assert_eq!(floors.parts["PART:b"], Shown::Unknown);
        assert_eq!(floors.parts["PART:c"], Shown::Unknown);
        assert_eq!(floors.run, Shown::Unknown);
        assert_eq!(run_word(None), "unavailable");
        assert_eq!(run_word(Some(Status::Unknown)), "UNKNOWN");
    }
}
