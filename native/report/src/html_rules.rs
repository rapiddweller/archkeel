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
    for (id, row) in frame.rules.iter().filter(|(_, row)| row.1 == verdict) {
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
    if held > 0 {
        html.push_str(&fold("RULES THAT HOLD", &pass));
    }
    if declared > 0 {
        html.push_str(&fold("PERMISSION DECLARATIONS: NO VERDICT", &declarations));
    }
    html.push_str("</details></section>\n");
    html
}
