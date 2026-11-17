// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rules that hold, one line for each, folded by rule kind (AD-498). A rule that fails or is
//! UNKNOWN has its own block above; here a reader finds each other rule by name.

use std::collections::BTreeMap;

use super::frame::Frame;
use super::markup::{count, escape};
use crate::head::RuleVerdict;

fn group(frame: &Frame, verdict: RuleVerdict) -> BTreeMap<String, Vec<String>> {
    let mut kinds: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let rows = frame.rules.iter().filter(|(_, row)| row.1 == verdict);
    for (id, row) in rows.filter(|(id, _)| !frame.premises.contains_key(*id)) {
        kinds
            .entry(row.0.replace('_', " "))
            .or_default()
            .push(id.clone());
    }
    kinds
}

fn fold(heading: &str, kinds: &BTreeMap<String, Vec<String>>) -> String {
    let mut html = format!("<h3 class=\"caption rp-group\">{heading}</h3>");
    for (kind, ids) in kinds {
        let lines: String = ids
            .iter()
            .map(|id| {
                format!(
                    "<li class=\"body-sm\"><span class=\"rp-code\">{}</span></li>",
                    escape(id)
                )
            })
            .collect();
        html.push_str(&format!(
            "<details class=\"rp-fold rp-grp\"><summary class=\"caption\">{} &#183; {}</summary>\
<ul class=\"rp-ev\">{lines}</ul></details>",
            escape(kind),
            count(ids.len(), "rule")
        ));
    }
    html
}

/// `PASS assuming <the premises of the run>`, in the words of the core (#1549), or `None` for a
/// run with no stated premise.
pub(super) fn qualifier(frame: &Frame) -> Option<String> {
    frame
        .assuming
        .as_ref()
        .map(|words| format!("PASS assuming {words}"))
}

/// The rules that hold only under a premise of the contract (AD-664, #1549), each with its
/// premises: the door sites and the stated external users.
fn assumed(frame: &Frame) -> String {
    let Some(heading) = qualifier(frame).filter(|_| !frame.premises.is_empty()) else {
        return String::new();
    };
    let heading = heading.to_uppercase();
    let lines: String = frame
        .premises
        .iter()
        .map(|(id, premises)| {
            let subjects: Vec<&str> = premises.iter().map(|p| p.subject.as_str()).collect();
            format!(
                "<li class=\"body-sm\"><span class=\"rp-code\">{}</span> {}</li>",
                escape(id),
                escape(&subjects.join(", "))
            )
        })
        .collect();
    format!("<h3 class=\"caption rp-group\">{heading}</h3><ul class=\"rp-ev\">{lines}</ul>")
}

/// The section of the rules that hold, or nothing when there are none.
pub(super) fn section(frame: &Frame) -> String {
    let (pass, declarations) = (
        group(frame, RuleVerdict::Pass),
        group(frame, RuleVerdict::Declaration),
    );
    let (held, declared) = (
        frame.rules_with(RuleVerdict::Pass),
        frame.rules_with(RuleVerdict::Declaration),
    );
    if held + declared == 0 {
        return String::new();
    }
    let mut html = format!(
        "<section class=\"rp-sec\" aria-labelledby=\"rules\"><h2 class=\"h2\" id=\"rules\">Rules</h2>\
<p class=\"body-sm rp-lede\">{} hold, {} declare a permission, {} fail, {} are unknown.</p>\
<details class=\"rp-fold\"><summary class=\"caption\">The rules that hold, by kind: one line each</summary>",
        count(held, "rule"),
        count(declared, "rule"),
        frame.rules_with(RuleVerdict::Fail),
        frame.rules_with(RuleVerdict::Unknown)
    );
    if !pass.is_empty() {
        html.push_str(&fold("RULES THAT HOLD", &pass));
    }
    html.push_str(&assumed(frame));
    if declared > 0 {
        html.push_str(&fold("PERMISSION DECLARATIONS: NO VERDICT", &declarations));
    }
    html.push_str("</details></section>\n");
    html
}
