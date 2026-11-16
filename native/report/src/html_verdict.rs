// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The verdict and the next steps (AD-496). The heading `<h1>Verdict: STATUS</h1>` is fixed text
//! that the shell checks; the card shows the same status and the counts of the frame.

use super::atlas_tree::DRAFT_WORD;
use super::causes;
use super::frame::Frame;
use super::markup::{count, escape, status_icon};
use super::places::Places;

/// The class word of a status.
fn word(status: &str) -> &'static str {
    match status {
        "PASS" => "pass",
        "FAIL" => "fail",
        _ => "unknown",
    }
}

fn title(frame: &Frame, places: &Places) -> String {
    let (fail, unknown) = (frame.rules_with("FAIL"), frame.rules_with("UNKNOWN"));
    match frame.status.as_str() {
        "PASS" => format!("All {} hold", count(frame.rules_with("PASS"), "rule")),
        "FAIL" => format!(
            "{} violated in {}, {unknown} unknown",
            count(fail, "rule"),
            count(places.total, "place")
        ),
        _ if unknown > 0 => format!("{} cannot be decided", count(unknown, "rule")),
        _ if !frame.named.is_empty() => format!(
            "The run cannot be decided: {} with no rule of their own hold it open",
            count(frame.named.len(), "gap")
        ),
        _ => "The run cannot be decided".to_owned(),
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

fn note(status: &str) -> &'static str {
    match status {
        "PASS" => "No violation. No unknown.",
        _ => "A violation is a fact of this run. An unknown rule is not a pass.",
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
        escape(&frame.status)
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
    if jobs.is_empty() && frame.status == "UNKNOWN" {
        jobs.push((
            1,
            format!(
                "Remove the cause that keeps the run open: {}",
                escape(&frame.cause)
            ),
        ));
    }
    jobs.sort_by_key(|(size, _)| std::cmp::Reverse(*size));
    jobs
}

fn next(frame: &Frame, places: &Places) -> String {
    let mut steps = Vec::new();
    if frame.status == "PASS" {
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

/// One line for each of the three largest causes of the UNKNOWN rules, without rule ids: the ids
/// are in the card of the cause. A cause is one short sentence and the number of the rules.
fn top_causes(frame: &Frame) -> String {
    let all = causes::grouped(frame);
    if all.is_empty() {
        return String::new();
    }
    // Every number below is a count of the list of causes that the Unknown section shows.
    let (rules, named): (usize, usize) = all.iter().fold((0, 0), |(r, n), cause| {
        (r + cause.rules.len(), n + cause.named)
    });
    let keeping = if all.len() == 1 {
        "1 cause keeps".to_owned()
    } else {
        format!("{} keep", count(all.len(), "cause"))
    };
    let no_rule = format!("{} with no rule", count(named, "gap"));
    let mut lines = format!(
        "<p class=\"body-sm ak-verdict__note\">{keeping} the run open: {} and {no_rule}.</p>",
        count(rules, "unknown rule")
    );
    for cause in all.iter().take(3) {
        let held = if cause.rules.is_empty() {
            format!("{} with no rule", count(cause.named, "gap"))
        } else {
            count(cause.rules.len(), "unknown rule")
        };
        lines.push_str(&format!(
            "<p class=\"body-sm ak-verdict__note\">{held}: {}</p>",
            escape(&causes::title(cause))
        ));
    }
    let more = all.len().saturating_sub(3);
    if more > 0 {
        lines.push_str(&format!(
            "<p class=\"body-sm ak-verdict__note\"><a href=\"#unknown\">{} more</a></p>",
            count(more, "cause")
        ));
    }
    lines
}

/// The verdict card and the next steps: the first block of the page.
pub(super) fn section(frame: &Frame, places: &Places) -> String {
    let status = frame.status.as_str();
    let state = word(status);
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
    format!(
        "<div class=\"rp-head\"><h1>Verdict: {}</h1><section class=\"ak-verdict ak-verdict--{state}\" aria-label=\"Verdict\">\
<span class=\"ak-badge ak-badge--{state} tag\">{}{}</span><h2 class=\"h2 ak-verdict__title\">{}</h2>\
<p class=\"body-sm ak-verdict__note\">{}</p>{}{}{}{}<dl class=\"ak-verdict__stats\">{}{}{}{}</dl></section>{}</div>
",
        escape(status),
        status_icon(status),
        escape(status),
        escape(&title(frame, places)),
        note(status),
        baseline(frame),
        premise(frame),
        calls(frame),
        top_causes(frame),
        stat("Rules PASS", frame.rules_with("PASS")),
        stat("Rules FAIL", frame.rules_with("FAIL")),
        stat("Rules UNKNOWN", frame.rules_with("UNKNOWN")),
        gaps(frame),
        next(frame, places)
    )
}
