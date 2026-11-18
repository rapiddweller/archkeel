// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The causes of the UNKNOWN rules, one card for each cause (AD-498). The frame says which gaps
//! hold which rule (`explain.holds`); the page groups the rules that one cause holds and shows
//! where the gaps are. It decides nothing, and it never shows a gap as a count only.

use std::collections::BTreeMap;

use super::cases::Names;
use super::causes::{anchor, grouped, hygiene, title, Cause};
use super::frame::Frame;
use super::markup::{count, escape, status_icon};
use super::status::{cause, Shown};
use crate::head::{RuleVerdict, Status};

/// The most cards, rows and rule ids that the page shows.
const MAX_CARDS: usize = 12;
const MAX_ROWS: usize = 12;
const MAX_IDS: usize = 5;
const MAX_LISTED_IDS: usize = 40;
const MAX_SITES: usize = 100;

/// What to do, for a cause whose meaning is fixed.
fn advice(kind: &str) -> Option<&'static str> {
    match kind {
        "coverage_gaps" => {
            Some("Close the gaps listed below. A rule is decided when no gap holds it.")
        }
        "pair_gaps" => {
            Some("For each pair below, make the call explicit or allow the pair in the contract.")
        }
        "scoped_gaps" => Some(
            "Close the gaps that the core names. Each of them leaves facts unknown that the rule reads.",
        ),
        "unknown_imports" => {
            Some("Resolve these imports, or let the scan name each of them as a gap.")
        }
        "no_source_files" => Some("Check the scan roots in the configuration of the run."),
        _ => None,
    }
}

/// A module name with its component, escaped.
pub(super) fn module(names: &Names<'_>, name: &str) -> String {
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

/// The gaps that the collector states once for many uses (AD-540): where the first evidence is,
/// the reason and the count that the collector wrote beside it. The page names no language.
fn stated_once(frame: &Frame) -> String {
    let items: String = frame
        .collection_gaps
        .iter()
        .filter_map(|gap| Some((gap, gap.detail.as_ref()?)))
        .map(|(gap, detail)| {
            let place = gap.evidence.first().and_then(|id| frame.place(id));
            format!(
                "<li class=\"body-sm\"><span class=\"rp-code\">{}</span> {} &#8212; {}</li>",
                escape(&place.unwrap_or_default()),
                escape(&gap.reason),
                escape(detail)
            )
        })
        .collect();
    if items.is_empty() {
        return String::new();
    }
    format!("<p class=\"caption\">Stated once</p><ul>{items}</ul>")
}

fn scan_sites(frame: &Frame) -> String {
    let mut total = 0;
    let mut sites = String::new();
    for gap in &frame.collection_gaps {
        if let Some(place) = gap.evidence.first().and_then(|id| frame.place(id)) {
            total += 1;
            if total <= MAX_SITES {
                sites.push_str(&format!(
                    "<li class=\"body-sm\"><span class=\"rp-code\">{}</span> &#8212; {}</li>",
                    escape(&place),
                    escape(&gap.reason)
                ));
            }
        }
    }
    if total == 0 {
        return String::new();
    }
    format!(
        "<details class=\"rp-fold\"><summary class=\"caption\">Scan gap sites: {} of {}</summary>\
<p class=\"body-sm\">These are scan gaps; not every gap holds every rule. Review each site. \
For eligible doors, a declared reach is an assumption, not a proof; a resulting \
PASS assuming the declared reach is conditional. Not every gap can be declared.</p><ul>{}</ul></details>",
        total.min(MAX_SITES),
        total,
        sites
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

/// A rule id and its kind. A row that the baseline accepts says so (AD-546).
fn rule_id(frame: &Frame, id: &str) -> String {
    let mark = if frame.accepted.contains(id) {
        " <span class=\"caption rp-acc\">(accepted by the baseline, still UNKNOWN)</span>"
    } else {
        ""
    };
    let kind = frame.rules.get(id).map_or_else(String::new, |(kind, _)| {
        format!(" ({})", escape(&kind.replace('_', " ")))
    });
    let rationale = frame
        .rule_rationales
        .get(id)
        .filter(|text| !text.trim().is_empty())
        .map_or_else(String::new, |text| format!(" &#8212; {}", escape(text)));
    format!(
        "<span class=\"rp-code\">{}</span>{kind}{rationale}{mark}",
        escape(id)
    )
}

/// The members of a family of hygiene gaps: what each points at, and the one message they share.
fn member_list(found: &Cause<'_>) -> String {
    let items: String = found
        .members
        .iter()
        .take(MAX_LISTED_IDS)
        .map(|member| {
            format!(
                "<li class=\"body-sm\"><span class=\"rp-code\">{}</span></li>",
                escape(member)
            )
        })
        .collect();
    let rest = found.members.len().saturating_sub(MAX_LISTED_IDS);
    let tail = if rest > 0 {
        format!("<p class=\"caption\">and {rest} more in the JSON</p>")
    } else {
        String::new()
    };
    format!(
        "<details class=\"rp-fold\"><summary class=\"caption\">Which: {}</summary><ul>{items}</ul>{tail}</details>",
        found.members.len()
    )
}

/// What the core says for a cause: the message that a family of hygiene gaps shares, or the reason.
fn says<'a>(found: &Cause<'a>) -> &'a str {
    match hygiene(found.reason) {
        Some((_, _, message)) if found.members.len() > 1 => message,
        _ => found.reason,
    }
}

fn card(frame: &Frame, names: &Names<'_>, found: &Cause<'_>) -> String {
    let held = found.rules.len();
    let badge = if held > 0 {
        count(held, "rule")
    } else {
        count(found.named, "named gap")
    };
    let mut html = format!(
        "<article class=\"rp-cause\" id=\"{}\"><div class=\"rp-cause__head\"><h3 class=\"h3\">{}</h3>\
<span class=\"ak-badge ak-badge--unknown tag\">{}{}</span></div>",
        anchor(found),
        escape(&title(found)),
        status_icon(Shown::Unknown),
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
            .map(|id| rule_id(frame, id))
            .collect();
        html.push_str(&format!(
            "<p class=\"body-sm rp-at\">Holds {}</p>",
            ids.join("<br>")
        ));
        let more = held.saturating_sub(MAX_IDS);
        if more > 0 {
            // The other ids are behind a fold, up to a bound; the rest is stated.
            let rest: Vec<String> = found
                .rules
                .iter()
                .skip(MAX_IDS)
                .take(MAX_LISTED_IDS - MAX_IDS)
                .map(|id| rule_id(frame, id))
                .collect();
            let tail = match held.saturating_sub(MAX_LISTED_IDS) {
                0 => String::new(),
                n => format!("<br>and {n} more in the JSON"),
            };
            html.push_str(&format!(
                "<details class=\"rp-fold\"><summary class=\"caption rp-at\">+{more} more</summary>\
<p class=\"rp-fold__body body-sm\">{}{tail}</p></details>",
                rest.join("<br>")
            ));
        }
    }
    // The fold is offered only when it adds something: a reason that the title already says whole
    // is not repeated.
    if ["other", "named", "scoped_gaps"].contains(&found.kind) && found.reason != title(found) {
        html.push_str(&format!(
            "<details class=\"rp-fold\"><summary class=\"caption\">What the core says</summary><p class=\"rp-fold__body\">{}</p></details>",
            escape(says(found))
        ));
    }
    if found.kind == "coverage_gaps" {
        html.push_str(&stated_once(frame));
    }
    if found.kind == "named" && found.members.len() > 1 {
        html.push_str(&member_list(found));
    }
    let tables = match found.kind {
        "coverage_gaps" if !frame.collection_gaps.is_empty() => format!(
            "<details class=\"rp-fold\"><summary class=\"caption\">Where and what</summary><div class=\"rp-cols\"><div>{}</div><div>{}</div></div></details>",
            gaps_table(frame, names),
            kinds_table(frame)
        ),
        "pair_gaps" | "allowed_pair_gaps" if !found.pairs.is_empty() => {
            format!(
                "<details class=\"rp-fold\"><summary class=\"caption\">Which pairs: {}</summary><div class=\"rp-cols\"><div>{}</div></div></details>",
                escape(&title(found)),
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
    let unknown = frame.rules_with(RuleVerdict::Unknown);
    // A decided run without a cause has no section; an open run and a frame without a status
    // name their cause (AD-730).
    let decided = matches!(frame.status, Some(Status::Pass | Status::Fail));
    if cards.is_empty() && decided {
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
    if cards.iter().any(|card| card.kind == "scoped_gaps") {
        html.push_str(&scan_sites(frame));
    }
    if total > cards.len() {
        html.push_str(&format!(
            "<p class=\"caption rp-note\">The page shows {} of {} causes, the largest first.</p>",
            cards.len(),
            total
        ));
    }
    if unknown == 0 {
        // The word `complete` is the scope, not a reason. When the cards above are the reason,
        // no card says it twice; with no card at all the page says what it knows (#1622).
        let said = cause(frame);
        let reason = if said == "complete" {
            (cards.is_empty()).then_some(
                "No rule is UNKNOWN and the scope is complete, but the core does not call the run decided. \
The JSON frame lists each gap.",
            )
        } else {
            Some(said)
        };
        if let Some(reason) = reason {
            html.push_str(&format!(
                "<article class=\"rp-cause\"><div class=\"rp-cause__head\"><h3 class=\"h3\">The run itself is open</h3></div>\
<p class=\"body-sm\">{}</p></article>",
                escape(reason)
            ));
        }
    }
    html.push_str("</section>\n");
    html
}

#[cfg(test)]
mod tests {
    use serde_json::{json, Value};

    fn page(frame: &Value) -> String {
        super::super::render(frame.as_object().unwrap()).unwrap()["document"]
            .as_str()
            .unwrap()
            .to_owned()
    }

    #[test]
    fn a_cause_names_the_kind_of_each_rule_it_holds() {
        let frame = json!({
            "status": "UNKNOWN",
            "rules": {"RULE-A": ["external_dependency_scope", "UNKNOWN"]},
            "explained": {"RULE-A": "proof is open"}
        });
        let rendered = page(&frame);
        assert!(rendered
            .contains("Holds <span class=\"rp-code\">RULE-A</span> (external dependency scope)"));
    }

    #[test]
    fn a_cause_shows_the_contract_rationale_without_interpreting_html() {
        let frame = json!({
            "status": "UNKNOWN",
            "rules": {"RULE-A": ["complete_requires", "UNKNOWN"]},
            "rule_rationales": {"RULE-A": "Keep <untrusted> dependencies explicit."},
            "explained": {"RULE-A": "proof is open"}
        });
        let rendered = page(&frame);
        assert!(rendered.contains("Keep &lt;untrusted&gt; dependencies explicit."));
        assert!(!rendered.contains("Keep <untrusted>"));
    }

    #[test]
    fn unknown_scope_shows_gap_sites_and_conditional_reach_advice() {
        let mut frame = json!({"status": "UNKNOWN", "rules": {"A": ["complete_requires", "UNKNOWN"]},
            "explain": {"holds": {"rules": {"A": {"cause": "scope_incomplete", "kind": "scoped_gaps", "total": 2}}}},
            "collection_gaps": [
                {"kind": "source_resolution_gap", "reason": "dynamic_import: import_module", "evidence": ["E1"]},
                {"kind": "source_resolution_gap", "reason": "dynamic_import: pickle.loads", "evidence": ["E2"]}],
            "locations": {"E1": {"path": "src/a.py", "line": 12}, "E2": {"path": "src/b.py", "line": 42}}});
        let rendered = page(&frame);
        assert!(rendered.contains("src/a.py:12") && rendered.contains("src/b.py:42"));
        assert!(rendered.contains("not every gap holds every rule"));
        assert!(rendered.contains("PASS assuming the declared reach"));
        frame["collection_gaps"][0]["reason"] = json!("<script>");
        assert!(page(&frame).contains("&lt;script&gt;"));
        frame["collection_gaps"] = json!([]);
        assert!(!page(&frame).contains("Scan gap sites"));
    }
}
