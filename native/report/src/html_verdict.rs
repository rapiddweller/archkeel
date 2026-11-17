// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The verdict and the next steps (AD-496). The heading `<h1>Verdict: STATUS</h1>` is fixed text
//! that the shell checks; one card shows the status, the counts and the next steps of the frame.

use super::atlas_tree::DRAFT_WORD;
use super::causes;
use super::frame::Frame;
use super::markup::{count, escape, status_icon};
use super::places::Places;
use super::status::{cause, run_word, Shown};
use crate::head::{RuleVerdict, Status};

fn title(frame: &Frame, places: &Places) -> String {
    let (fail, unknown) = (
        frame.rules_with(RuleVerdict::Fail),
        frame.rules_with(RuleVerdict::Unknown),
    );
    let pass = frame.rules_with(RuleVerdict::Pass);
    match frame.status {
        Some(Status::Pass) if !frame.premises.is_empty() => format!(
            "All {} hold; {} hold assuming {}",
            count(pass, "rule"),
            frame.premises.len(),
            frame
                .assuming
                .as_deref()
                .unwrap_or("a premise of the contract")
        ),
        Some(Status::Pass) => format!("All {} hold", count(pass, "rule")),
        // An unported rule or a named gap has no row: it is no UNKNOWN row, and it is not
        // decided either, so the title counts it (#1507).
        Some(Status::Fail) if !frame.named.is_empty() => format!(
            "{} violated in {}, {unknown} unknown, {} with no rule",
            count(fail, "rule"),
            count(places.total, "place"),
            count(frame.named.len(), "gap")
        ),
        Some(Status::Fail) => format!(
            "{} violated in {}, {unknown} unknown",
            count(fail, "rule"),
            count(places.total, "place")
        ),
        Some(Status::Unknown) | None if unknown > 0 => {
            format!("{} cannot be decided", count(unknown, "rule"))
        }
        Some(Status::Unknown) | None if !frame.named.is_empty() => format!(
            "The run cannot be decided: {} with no rule of their own hold it open",
            count(frame.named.len(), "gap")
        ),
        Some(Status::Unknown) => "The run cannot be decided".to_owned(),
        None => "The frame states no status: the run cannot be decided".to_owned(),
    }
}

/// The assumption that the collector states for its proofs, as one line under the verdict note
/// (AD-540). The core states it for the run; this page names no language.
fn premise(frame: &Frame) -> String {
    if frame.premise.is_empty() {
        return String::new();
    }
    format!(
        "<p class=\"body-sm ak-verdict__note\">Stated assumption: {}</p>",
        escape(&frame.premise)
    )
}

/// The premises of the contract (AD-664, #1549): a PASS under one is never a plain PASS.
fn doors(frame: &Frame) -> String {
    let Some(qualifier) = super::rules::qualifier(frame) else {
        return String::new();
    };
    format!(
        "<p class=\"body-sm ak-verdict__note\">{}: {} hold only under these premises of the \
contract; a premise is not a proof.</p>",
        escape(&qualifier),
        count(frame.premises.len(), "rule")
    )
}

/// The word of the badge: `PASS assuming <premises>` for a PASS that rests on a premise of the
/// contract (#1549), else the word of the status.
fn badge(frame: &Frame) -> String {
    match super::rules::qualifier(frame) {
        Some(qualified) if frame.status == Some(Status::Pass) && !frame.premises.is_empty() => {
            escape(&qualified)
        }
        Some(_) | None => run_word(frame.status).to_owned(),
    }
}

/// How many calls the core resolved and what an unresolved call does to a verdict (#1327). The
/// same words as the text summary of the shell.
fn calls(frame: &Frame) -> String {
    let Some(found) = &frame.calls else {
        return String::new();
    };
    let share = if found.calls_total == 0 {
        "n/a".to_owned()
    } else {
        format!(
            "{:.1}%",
            100.0 * found.calls_resolved as f64 / found.calls_total as f64
        )
    };
    format!(
        "<p class=\"body-sm ak-verdict__note\">Calls: {} of {} resolved ({share}); {} partly resolved, {} builtin, {} outside the scan, {} unresolved.</p>\
<p class=\"body-sm ak-verdict__note\">An unresolved call has no proven target and is no edge. A rule that reads calls cannot decide from it and stays UNKNOWN; a rule of imports does not read it.</p>",
        found.calls_resolved,
        found.calls_total,
        found.calls_partial,
        found.calls_builtin,
        found.calls_external,
        found.calls_unresolved
    )
}

fn note(status: Option<Status>) -> &'static str {
    match status {
        Some(Status::Pass) => "No violation. No unknown.",
        Some(Status::Fail | Status::Unknown) | None => {
            "A violation is a fact of this run. An unknown rule is not a pass."
        }
    }
}

/// The line of the baseline (AD-546). An accepted UNKNOWN keeps its word: it is not a pass.
fn baseline(frame: &Frame) -> String {
    let Some((state, accepted)) = &frame.baseline else {
        return String::new();
    };
    format!(
        "<p class=\"body-sm ak-verdict__note\">Baseline: {}. {} UNKNOWN {} accepted by the \
baseline; the status stays {}, and an accepted UNKNOWN is not a pass.</p>",
        escape(state),
        accepted,
        if *accepted == 1 { "entry" } else { "entries" },
        run_word(frame.status)
    )
}

/// The components whose responsibility `init` drafted and nobody wrote yet.
fn unwritten(frame: &Frame) -> usize {
    frame.topology.as_ref().map_or(0, |topology| {
        topology
            .components
            .iter()
            .filter(|c| {
                c.responsibilities
                    .iter()
                    .any(|t| t.trim().starts_with(DRAFT_WORD))
            })
            .count()
    })
}

/// The jobs of a run that is not PASS, each with its count, the largest first (at most three).
fn jobs(frame: &Frame, places: &Places) -> Vec<(usize, String)> {
    let mut jobs: Vec<(usize, String)> = Vec::new();
    if places.total > 0 {
        // All the places up to nine; else the first five and a link to the whole section.
        let shown = if places.shown.len() <= 9 {
            places.shown.len()
        } else {
            5
        };
        let mut links: Vec<String> = places
            .shown
            .iter()
            .take(shown)
            .map(|place| format!("<a href=\"#x{n}\">{n}</a>", n = place.number))
            .collect();
        if places.total > shown {
            links.push(format!(
                "<a href=\"#violations\">+{} more</a>",
                places.total - shown
            ));
        }
        jobs.push((
            places.total,
            format!(
                "Remove {}. Evidence: {}.",
                count(places.total, "violated place"),
                links.join(", ")
            ),
        ));
    }
    let todo = unwritten(frame);
    if todo > 0 {
        jobs.push((
            todo,
            format!(
                "Write the responsibility of {} (the contract still says TODO).",
                count(todo, "component")
            ),
        ));
    }
    for cause in causes::grouped(frame) {
        if cause.rules.is_empty() {
            jobs.push((
                cause.named,
                format!(
                    "Remove the cause that keeps the run open ({}): {}.",
                    count(cause.named, "gap"),
                    escape(&causes::title(&cause))
                ),
            ));
        } else {
            jobs.push((
                cause.rules.len(),
                format!(
                    "Close the gaps behind {}: {}. <a href=\"#unknown\">Causes</a>.",
                    count(cause.rules.len(), "unknown rule"),
                    escape(&causes::title(&cause))
                ),
            ));
        }
    }
    // An open run and a frame without a status name their cause (AD-730).
    let open = matches!(frame.status, Some(Status::Unknown) | None);
    if jobs.is_empty() && open {
        jobs.push((
            1,
            format!(
                "Remove the cause that keeps the run open: {}",
                escape(cause(frame))
            ),
        ));
    }
    jobs.sort_by_key(|(size, _)| std::cmp::Reverse(*size));
    jobs
}

fn next(frame: &Frame, places: &Places) -> String {
    let mut steps = Vec::new();
    if frame.status == Some(Status::Pass) {
        steps.push("Nothing to do. Keep the contract and this report with the commit.".to_owned());
    } else {
        let all = jobs(frame, places);
        steps.extend(all.iter().take(3).map(|(_, text)| text.clone()));
        if all.len() > 3 {
            steps.push(format!(
                "{} more: <a href=\"#unknown\">see the causes</a>.",
                count(all.len() - 3, "job")
            ));
        }
    }
    steps.push(
        "Every row behind this page: <span class=\"rp-code\">archkeel report --topology --output report.json --format json</span>"
            .to_owned(),
    );
    let items: String = steps
        .iter()
        .map(|step| format!("<li class=\"body-sm\">{step}</li>"))
        .collect();
    format!(
        "<section class=\"rp-next\" aria-labelledby=\"next\"><h2 class=\"caption\" id=\"next\">NEXT</h2><ol>{items}</ol></section>"
    )
}

/// The verdict card and the next steps: the first block of the page.
pub(super) fn section(frame: &Frame, places: &Places) -> String {
    let status = Shown::of_run(frame.status);
    let state = status.class();
    let stat = |label: &str, value: usize| {
        format!(
            "<div class=\"ak-verdict__stat\"><dt class=\"caption\">{label}</dt><dd class=\"ak-num h2\">{value}</dd></div>"
        )
    };
    let gaps = |frame: &Frame| {
        if frame.named.is_empty() {
            String::new()
        } else {
            stat("Gaps with no rule", frame.named.len())
        }
    };
    // One block: the status, one plain sentence, the counts and the next steps. A cause is named
    // once, in the first step that closes it; the Unknown section holds its detail.
    format!(
        "<div class=\"rp-head\"><h1>Verdict: {}</h1><section class=\"ak-verdict ak-verdict--{state}\" aria-label=\"Verdict\">\
<div class=\"ak-verdict__main\"><span class=\"ak-badge ak-badge--{state} tag\">{}{}</span><h2 class=\"h2 ak-verdict__title\">{}</h2>\
<p class=\"body-sm ak-verdict__note\">{}</p><dl class=\"ak-verdict__stats\">{}{}{}{}</dl>{}{}{}{}</div>{}</section></div>
",
        run_word(frame.status),
        status_icon(status),
        badge(frame),
        escape(&title(frame, places)),
        note(frame.status),
        stat("Rules PASS", frame.rules_with(RuleVerdict::Pass)),
        stat("Rules FAIL", frame.rules_with(RuleVerdict::Fail)),
        stat("Rules UNKNOWN", frame.rules_with(RuleVerdict::Unknown)),
        gaps(frame),
        baseline(frame),
        premise(frame),
        doors(frame),
        calls(frame),
        next(frame, places)
    )
}
