// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The causes of the UNKNOWN rules, one card for each cause (AD-498). The frame says which gaps
//! hold which rule (`explain.holds`); the page groups the rules that one cause holds and shows
//! where the gaps are. It decides nothing, and it never shows a gap as a count only.

use std::collections::BTreeMap;

use super::cases::Names;
use super::causes::{grouped, title, Cause};
use super::frame::Frame;
use super::markup::{count, escape, status_icon};

/// The most cards, rows and rule ids that the page shows.
const MAX_CARDS: usize = 12;
const MAX_ROWS: usize = 12;
const MAX_IDS: usize = 5;

/// What to do, for a cause whose meaning is fixed.
fn advice(kind: &str) -> Option<&'static str> {
    match kind {
        "coverage_gaps" => {
            Some("Close the gaps listed below. A rule is decided when no gap holds it.")
        }
        "pair_gaps" => {
            Some("For each pair below, make the call explicit or allow the pair in the contract.")
        }
        "unknown_imports" => {
            Some("Resolve these imports, or let the scan name each of them as a gap.")
        }
        "no_source_files" => Some("Check the scan roots in the configuration of the run."),
        _ => None,
    }
}

fn module(names: &Names<'_>, name: &str) -> String {
    match names.component(name) {
        Some((_, component)) => format!(
            "{} <span class=\"rp-at\">({})</span>",
            escape(name),
            escape(component)
        ),
        None => escape(name),
    }
}

fn pairs_table(names: &Names<'_>, card: &Cause<'_>) -> String {
    let rows: String = card
        .pairs
        .iter()
        .take(MAX_ROWS)
        .map(|(source, target)| {
            format!(
                "<tr><td class=\"code\">{}</td><td class=\"code\">{}</td></tr>",
                module(names, source),
                module(names, target)
            )
        })
        .collect();
    format!(
        "<table class=\"rp-mini\"><caption class=\"caption\">Where: {} of {} between two modules</caption>\
<thead><tr><th class=\"caption\">Source</th><th class=\"caption\">Target</th></tr></thead><tbody>{rows}</tbody></table>",
        card.pairs.len().min(MAX_ROWS),
        card.total.max(card.pairs.len())
    )
}

/// The scan gaps by component: where the collector could not see.
fn gaps_table(frame: &Frame, names: &Names<'_>) -> String {
    let mut by_component: BTreeMap<String, usize> = BTreeMap::new();
    for gap in &frame.collection_gaps {
        let place = gap
            .subjects
            .iter()
            .find_map(|subject| names.component(subject).map(|(_, name)| name.to_owned()))
            .unwrap_or_else(|| "outside the contract".to_owned());
        *by_component.entry(place).or_default() += 1;
    }
    let mut rows: Vec<(String, usize)> = by_component.into_iter().collect();
    rows.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    let total = rows.len();
    let body: String = rows
        .iter()
        .take(MAX_ROWS)
        .map(|(name, gaps)| {
            format!(
                "<tr><td class=\"body-sm\">{}</td><td class=\"code ak-num\">{gaps}</td></tr>",
                escape(name)
            )
        })
        .collect();
    format!(
        "<table class=\"rp-mini\"><caption class=\"caption\">Where: {} of {}, {} in all</caption>\
<thead><tr><th class=\"caption\">Component</th><th class=\"caption ak-num\">Gaps</th></tr></thead><tbody>{body}</tbody></table>",
        total.min(MAX_ROWS),
        count(total, "component"),
        count(frame.collection_gaps.len(), "gap")
    )
}

/// The kinds of the scan gaps, counted: what the collector could not read.
fn kinds_table(frame: &Frame) -> String {
    let mut kinds: BTreeMap<&str, usize> = BTreeMap::new();
    for gap in &frame.collection_gaps {
        *kinds.entry(gap.kind.as_str()).or_default() += 1;
    }
    let body: String = kinds
        .iter()
        .map(|(kind, gaps)| {
            format!(
                "<tr><td class=\"body-sm\">{}</td><td class=\"code ak-num\">{gaps}</td></tr>",
                escape(&kind.replace('_', " "))
            )
        })
        .collect();
    format!(
        "<table class=\"rp-mini\"><caption class=\"caption\">What: the kinds of the gaps</caption>\
<thead><tr><th class=\"caption\">Kind</th><th class=\"caption ak-num\">Gaps</th></tr></thead><tbody>{body}</tbody></table>"
    )
}

fn card(frame: &Frame, names: &Names<'_>, found: &Cause<'_>) -> String {
    let held = found.rules.len();
    let badge = if held > 0 {
        count(held, "rule")
    } else {
        count(found.named, "named gap")
    };
    let mut html = format!(
        "<article class=\"rp-cause\"><div class=\"rp-cause__head\"><h3 class=\"h3\">{}</h3>\
<span class=\"ak-badge ak-badge--unknown tag\">{}{}</span></div>",
        escape(&title(found)),
        status_icon("UNKNOWN"),
        badge
    );
    if let Some(line) = advice(found.kind) {
        html.push_str(&format!("<p class=\"body-sm\">{line}</p>"));
    }
    if held > 0 {
        let ids: Vec<String> = found
            .rules
            .iter()
            .take(MAX_IDS)
            .map(|id| format!("<span class=\"rp-code\">{}</span>", escape(id)))
            .collect();
        let more = held.saturating_sub(MAX_IDS);
        let tail = if more > 0 {
            format!(" <span class=\"rp-at\">+{more} more</span>")
        } else {
            String::new()
        };
        html.push_str(&format!(
            "<p class=\"body-sm rp-at\">Holds {}{tail}</p>",
            ids.join(", ")
        ));
    }
    if found.kind == "other" || found.kind == "named" {
        html.push_str(&format!(
            "<details class=\"rp-fold\"><summary class=\"caption\">What the core says</summary><p class=\"rp-fold__body\">{}</p></details>",
            escape(found.reason)
        ));
    }
    let tables = match found.kind {
        "coverage_gaps" if !frame.collection_gaps.is_empty() => format!(
            "<details class=\"rp-fold\"><summary class=\"caption\">Where and what</summary><div class=\"rp-cols\"><div>{}</div><div>{}</div></div></details>",
            gaps_table(frame, names),
            kinds_table(frame)
        ),
        "pair_gaps" | "allowed_pair_gaps" if !found.pairs.is_empty() => {
            format!(
                "<details class=\"rp-fold\"><summary class=\"caption\">Which pairs</summary><div class=\"rp-cols\"><div>{}</div></div></details>",
                pairs_table(names, found)
            )
        }
        _ => String::new(),
    };
    html.push_str(&tables);
    html.push_str("</article>");
    html
}

/// The section of the causes, or nothing when no rule is UNKNOWN and the run is decided.
pub(super) fn section(frame: &Frame, names: &Names<'_>) -> String {
    let mut cards = grouped(frame);
    let unknown = frame.rules_with("UNKNOWN");
    if cards.is_empty() && frame.status != "UNKNOWN" {
        return String::new();
    }
    let total = cards.len();
    let lede = if unknown > 0 {
        format!(
            "{} cannot be decided, from {}. An UNKNOWN rule is not a pass.",
            count(unknown, "rule"),
            count(total, "cause")
        )
    } else {
        "The run is not decided, and a run that is not decided is not a pass.".to_owned()
    };
    let mut html = format!(
        "<section class=\"rp-sec\" aria-labelledby=\"unknown\"><h2 class=\"h2\" id=\"unknown\">Unknown</h2>\
<p class=\"body-sm rp-lede\">{lede}</p>"
    );
    cards.truncate(MAX_CARDS);
    for found in &cards {
        html.push_str(&card(frame, names, found));
    }
    if total > cards.len() {
        html.push_str(&format!(
            "<p class=\"caption rp-note\">The page shows {} of {} causes, the largest first.</p>",
            cards.len(),
            total
        ));
    }
    if unknown == 0 {
        html.push_str(&format!(
            "<article class=\"rp-cause\"><div class=\"rp-cause__head\"><h3 class=\"h3\">The run itself is open</h3></div>\
<p class=\"body-sm\">{}</p></article>",
            escape(&frame.cause)
        ));
    }
    html.push_str("</section>\n");
    html
}
