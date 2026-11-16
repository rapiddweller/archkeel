// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The list of the Diff view (AD-594): each violated place, each pair of modules that a gap holds
//! and each declared requirement without an observed import, one line each. The list cuts
//! nothing that the frame names, and it states what the frame does not name.

use super::cases::{one_line, Names};
use super::frame::Frame;
use super::markup::{count, escape};
use super::places::Places;
use super::unknown::module;
use super::views::{held_pairs, Link, Mark, View};

/// Above this number of rules, a line counts the rules; the block of the line names each.
const MAX_RULE_IDS: usize = 3;

fn rules(ids: &[&str]) -> String {
    if ids.len() > MAX_RULE_IDS {
        return count(ids.len(), "rule");
    }
    ids.iter()
        .map(|id| format!("<b class=\"rp-code\">{}</b>", escape(id)))
        .collect::<Vec<_>>()
        .join(", ")
}

/// One group of the list: a head with the number, each line, and a note on what is not named.
fn group(head: &str, total: usize, lines: &[String], note: &str) -> String {
    if total == 0 {
        return String::new();
    }
    let lines: String = lines
        .iter()
        .map(|line| format!("<li class=\"body-sm\">{line}</li>"))
        .collect();
    format!(
        "<p class=\"caption rp-note\">{head}: {total}</p><ul class=\"rp-ev\">{lines}</ul>{note}"
    )
}

fn violated(places: &Places, names: &Names<'_>) -> String {
    let lines: Vec<String> = places
        .shown
        .iter()
        .map(|place| {
            let mut ids: Vec<&str> = Vec::new();
            for violated in &place.rules {
                if !ids.contains(&violated.rule.as_str()) {
                    ids.push(&violated.rule);
                }
            }
            format!(
                "<a href=\"#x{n}\"><span class=\"rp-no\">{n}</span> {}</a> &#183; {}",
                escape(&one_line(names, place)),
                rules(&ids),
                n = place.number
            )
        })
        .collect();
    let note = if places.total > places.shown.len() {
        format!(
            "<p class=\"caption rp-note\">The page shows {} of {} violated places.</p>",
            places.shown.len(),
            places.total
        )
    } else {
        String::new()
    };
    group("Violated places", places.total, &lines, &note)
}

fn held(frame: &Frame, names: &Names<'_>) -> String {
    let pairs = held_pairs(frame);
    let lines: Vec<String> = pairs
        .iter()
        .map(|((source, target), ids)| {
            format!(
                "<a href=\"#unknown\">{} to {}</a> &#183; {}",
                module(names, source),
                module(names, target),
                rules(ids)
            )
        })
        .collect();
    let holds = frame
        .rules
        .iter()
        .filter(|(_, row)| row.1 == "UNKNOWN")
        .filter_map(|(rule, _)| frame.explain.holds.rules.get(rule));
    let (named, total) = holds.fold((0, 0), |sum, hold| {
        (
            sum.0 + hold.pairs.len(),
            sum.1 + hold.total.max(hold.pairs.len()),
        )
    });
    let note = if total > named {
        format!("<p class=\"caption rp-note\">The frame names {named} of {total} pairs that a gap holds for a rule. The list shows each named pair.</p>")
    } else {
        String::new()
    };
    group("Held by a gap, not decided", pairs.len(), &lines, &note)
}

/// The list of the Diff view.
pub(super) fn differences(
    frame: &Frame,
    links: &[Link<'_>],
    places: &Places,
    names: &Names<'_>,
) -> String {
    let unused: Vec<String> = links
        .iter()
        .filter(|link| link.mark(View::Diff) == Some(Mark::Unused))
        .map(|link| link.pair(names))
        .collect();
    let body = [
        violated(places, names),
        held(frame, names),
        group(
            "Declared and without an observed import, for information",
            unused.len(),
            &unused,
            "",
        ),
    ]
    .concat();
    let body = if body.is_empty() {
        "<p class=\"caption rp-note\">No difference.</p>".to_owned()
    } else {
        body
    };
    format!("<div class=\"rp-in rp-d rp-diff\">{body}</div>")
}
