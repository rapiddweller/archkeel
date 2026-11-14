// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The verdict and the next steps (AD-496). The heading `<h1>Verdict: STATUS</h1>` is fixed text
//! that the shell checks; the card shows the same status and the counts of the frame.

use super::frame::Frame;
use super::places::Places;
use super::text::{count, escape, status_icon};

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
        _ => "The run cannot be decided".to_owned(),
    }
}

fn note(status: &str) -> &'static str {
    match status {
        "PASS" => "No violation. No unknown.",
        _ => "A violation is a fact of this run. An unknown rule is not a pass.",
    }
}

fn next(frame: &Frame, places: &Places) -> String {
    let mut steps = Vec::new();
    match frame.status.as_str() {
        "PASS" => steps
            .push("Nothing to do. Keep the contract and this report with the commit.".to_owned()),
        status => {
            if places.total > 0 {
                let links: Vec<String> = places
                    .shown
                    .iter()
                    .take(5)
                    .map(|place| format!("<a href=\"#x{n}\">{n}</a>", n = place.number))
                    .collect();
                steps.push(format!(
                    "Remove {}. Evidence: {}.",
                    count(places.total, "violated place"),
                    links.join(", ")
                ));
            }
            if frame.rules_with("UNKNOWN") > 0 || status == "UNKNOWN" {
                steps.push(format!(
                    "Close the gaps behind the {} so that the run can decide them.",
                    count(frame.rules_with("UNKNOWN"), "unknown rule")
                ));
            }
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
    let status = frame.status.as_str();
    let state = word(status);
    let stat = |label: &str, value: usize| {
        format!(
            "<div class=\"ak-verdict__stat\"><dt class=\"caption\">{label}</dt><dd class=\"ak-num h2\">{value}</dd></div>"
        )
    };
    format!(
        "<div class=\"rp-head\"><h1>Verdict: {}</h1><section class=\"ak-verdict ak-verdict--{state}\" aria-label=\"Verdict\">\
<span class=\"ak-badge ak-badge--{state} tag\">{}{}</span><h2 class=\"h2 ak-verdict__title\">{}</h2>\
<p class=\"body-sm ak-verdict__note\">{}</p><dl class=\"ak-verdict__stats\">{}{}{}</dl></section>{}</div>\n",
        escape(status),
        status_icon(status),
        escape(status),
        escape(&title(frame, places)),
        note(status),
        stat("PASS", frame.rules_with("PASS")),
        stat("FAIL", frame.rules_with("FAIL")),
        stat("UNKNOWN", frame.rules_with("UNKNOWN")),
        next(frame, places)
    )
}
