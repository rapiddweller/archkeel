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
use super::frame::{Frame, Unsupported};
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

/// Whether the frame proves that every rule of the contract has a decided row, and that each of
/// these rules does (AD-730, #1507). The core writes each rule of the contract either as a row or
/// as an entry of `unsupported.rules`, so the proof is: the scope is `complete`, the list of the
/// rules without a row is present and empty, each rule that `explain` names has a row, and each of
/// these rules has a row that is not UNKNOWN. The absence of an UNKNOWN row alone proves nothing:
/// an unported rule or an open scope has no row at all.
fn every_rule_decided<'a>(frame: &Frame, mut rules: impl Iterator<Item = &'a String>) -> bool {
    let none_without_row = match &frame.unsupported {
        Unsupported::Each(rules) => rules.is_empty(),
        Unsupported::Absent | Unsupported::Whole => false,
    };
    let shaped = frame
        .explain
        .rules
        .keys()
        .all(|r| frame.rules.contains_key(r));
    frame.scope_complete
        && none_without_row
        && shaped
        && rules.all(|r| {
            frame
                .rules
                .get(r)
                .is_some_and(|row| row.1 != RuleVerdict::Unknown)
        })
}

/// The best status that a box, a cell or an edge may show in a run with this status (AD-730). A
/// PASS run decides every rule by the status rule of the core; a FAIL run may PASS a box only when
/// the frame proves that every rule is decided. Any other run decides no box as PASS, because a
/// rule of the run that is not decided may break inside any box.
fn floor(status: Option<Status>, decided: bool) -> Shown {
    match status {
        Some(Status::Pass) => Shown::Pass,
        Some(Status::Fail) if decided => Shown::Pass,
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
        // A rule of a system without a row names no part, so it holds each FAIL part.
        Floors {
            run: floor(frame.status, every_rule_decided(frame, frame.rules.keys())),
            parts: frame
                .parts
                .iter()
                .map(|p| {
                    let part = floor(p.status, every_rule_decided(frame, p.rules.iter()));
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

    use crate::head::RuleVerdict::{Fail, Pass, Unknown};

    /// A frame that proves each rule of the contract has a row (complete scope, an empty list of
    /// rules without a row), with rules `R0`, `R1`, ... of these verdicts.
    fn proven(status: Option<Status>, verdicts: &[RuleVerdict]) -> Frame {
        Frame {
            status,
            rules: verdicts
                .iter()
                .enumerate()
                .map(|(i, v)| (format!("R{i}"), (String::new(), *v)))
                .collect(),
            unsupported: Unsupported::Each(BTreeMap::new()),
            scope_complete: true,
            ..Frame::default()
        }
    }

    fn part(id: &str, status: Status, rules: &[&str]) -> super::super::frame::Part {
        super::super::frame::Part {
            id: id.to_owned(),
            status: Some(status),
            rules: rules.iter().map(|r| (*r).to_owned()).collect(),
        }
    }

    #[test]
    fn the_floor_is_pass_only_for_a_run_that_decides_every_rule() {
        let run = |status, verdicts: &[RuleVerdict]| Floors::of(&proven(status, verdicts)).run;
        assert_eq!(run(Some(Status::Pass), &[Pass]), Shown::Pass);
        assert_eq!(run(Some(Status::Fail), &[Fail, Pass]), Shown::Pass);
        assert_eq!(run(Some(Status::Fail), &[Fail, Unknown]), Shown::Unknown);
        assert_eq!(run(Some(Status::Unknown), &[Pass]), Shown::Unknown);
        assert_eq!(run(None, &[Pass]), Shown::Unknown);
        assert_eq!(run_word(None), "unavailable");
        assert_eq!(run_word(Some(Status::Unknown)), "UNKNOWN");
    }

    // #1507: a FAIL run without an UNKNOWN row is not proven decided when a rule has no row
    // (unported), the scope is open, the frame states no list, one reason holds the whole
    // contract, or `explain` names a rule without a row.
    #[test]
    fn a_fail_run_with_a_rule_without_a_row_has_no_pass_floor() {
        let fail = || proven(Some(Status::Fail), &[Fail, Pass]);
        let unported = BTreeMap::from([("PLACE".to_owned(), "unsupported: rule kind".to_owned())]);
        let mut unshaped = fail();
        unshaped
            .explain
            .rules
            .insert("PLACE".to_owned(), Default::default());
        let cases: [(&str, Frame); 5] = [
            (
                "unported",
                Frame {
                    unsupported: Unsupported::Each(unported),
                    ..fail()
                },
            ),
            (
                "open scope",
                Frame {
                    scope_complete: false,
                    ..fail()
                },
            ),
            (
                "no list",
                Frame {
                    unsupported: Unsupported::Absent,
                    ..fail()
                },
            ),
            (
                "whole",
                Frame {
                    unsupported: Unsupported::Whole,
                    ..fail()
                },
            ),
            ("unshaped", unshaped),
        ];
        for (name, case) in cases {
            assert_eq!(Floors::of(&case).run, Shown::Unknown, "{name}");
        }
    }

    // A part reads its own status and rules; a rule that the frame does not state is open. A rule
    // of the system without a row names no part, so it holds each FAIL part (#1507).
    #[test]
    fn a_part_reads_the_same_predicate_over_its_own_rules() {
        let mut system = proven(Some(Status::Unknown), &[Pass, Unknown]);
        system.parts = vec![
            part("a", Status::Pass, &["R0"]),
            part("b", Status::Unknown, &["R1"]),
            part("c", Status::Fail, &["R0", "MISSING"]),
            part("d", Status::Fail, &["R0"]),
        ];
        let floors = Floors::of(&system);
        assert_eq!(floors.parts["PART:a"], Shown::Pass);
        assert_eq!(floors.parts["PART:b"], Shown::Unknown);
        assert_eq!(floors.parts["PART:c"], Shown::Unknown);
        assert_eq!(floors.parts["PART:d"], Shown::Pass);
        assert_eq!(floors.run, Shown::Unknown);
        system.unsupported = Unsupported::Each(BTreeMap::from([("X".to_owned(), "x".to_owned())]));
        let floors = Floors::of(&system);
        assert_eq!(floors.parts["PART:d"], Shown::Unknown);
        assert_eq!(floors.parts["PART:a"], Shown::Pass);
    }
}
