// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rules that hold, one line for each, folded by rule kind (AD-498). A rule that fails or is
//! UNKNOWN has its own block above; here a reader finds each other rule by name.

use std::collections::BTreeMap;

use super::frame::Frame;
use super::markup::{count, escape};

fn group(frame: &Frame, verdict: &str) -> BTreeMap<String, Vec<String>> {
    let mut kinds: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let rows = frame.rules.iter().filter(|(_, row)| row.1 == verdict);
    for (id, row) in rows.filter(|(id, _)| !frame.assumed.contains_key(*id)) {
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

/// `PASS assuming the declared reach of N doors`, or of one door.
pub(super) fn qualifier(doors: usize) -> String {
    match doors {
        1 => "PASS assuming the declared reach of 1 door".to_owned(),
        many => format!("PASS assuming the declared reach of {many} doors"),
    }
}

/// The rules that hold only under the declared reach of door sites (AD-664), each with its sites.
fn assumed(frame: &Frame) -> String {
    if frame.assumed.is_empty() {
        return String::new();
    }
    let heading = qualifier(frame.doors).to_uppercase();
    let lines: String = frame
        .assumed
        .iter()
        .map(|(id, sites)| {
            format!(
                "<li class=\"body-sm\"><span class=\"rp-code\">{}</span> {}</li>",
                escape(id),
                escape(&sites.join(", "))
            )
        })
        .collect();
    format!("<h3 class=\"caption rp-group\">{heading}</h3><ul class=\"rp-ev\">{lines}</ul>")
}

/// The section of the rules that hold, or nothing when there are none.
pub(super) fn section(frame: &Frame) -> String {
    let (pass, declarations) = (group(frame, "PASS"), group(frame, "DECLARATION"));
    let (held, declared) = (frame.rules_with("PASS"), frame.rules_with("DECLARATION"));
    if held + declared == 0 {
        return String::new();
    }
    let mut html = format!(
        "<section class=\"rp-sec\" aria-labelledby=\"rules\"><h2 class=\"h2\" id=\"rules\">Rules</h2>\
<p class=\"body-sm rp-lede\">{} hold, {} declare a permission, {} fail, {} are unknown.</p>\
<details class=\"rp-fold\"><summary class=\"caption\">The rules that hold, by kind: one line each</summary>",
        count(held, "rule"),
        count(declared, "rule"),
        frame.rules_with("FAIL"),
        frame.rules_with("UNKNOWN")
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
