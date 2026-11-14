// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The footer of the page (AD-498): one line that names the run and the command for its rows. The
//! identity of the run is folded below it. A frame has no date, so the page has none: equal runs
//! give equal pages.

use super::frame::Frame;
use super::markup::escape;

fn short(text: &str) -> String {
    text.chars().take(12).collect()
}

/// The footer line and the folded identity.
pub(super) fn section(frame: &Frame) -> String {
    let id = &frame.identity;
    let commit = if id.git_head.is_empty() {
        "no commit".to_owned()
    } else {
        format!("commit {}", escape(&short(&id.git_head)))
    };
    let files: String = id
        .contract_files
        .iter()
        .map(|(name, digest)| format!("<dt>{}</dt><dd>{}</dd>", escape(name), escape(digest)))
        .collect();
    let line = |name: &str, value: &str| {
        if value.is_empty() {
            String::new()
        } else {
            format!("<dt>{name}</dt><dd>{}</dd>", escape(value))
        }
    };
    format!(
        "<footer class=\"rp-foot\"><p class=\"caption\">Core {} &#183; {commit}{} &#183; \
rows: <span class=\"rp-code\">archkeel report --topology --output report.json --format json</span></p>\
<details class=\"rp-fold\"><summary class=\"caption\">Request identity</summary><dl class=\"rp-kv\">{}{}{}{files}</dl></details></footer>\n",
        escape(&short(&id.engine)),
        if id.contract_digest.is_empty() {
            String::new()
        } else {
            format!(" &#183; contract {}", escape(&short(&id.contract_digest)))
        },
        line("Commit", &id.git_head),
        line("Core code digest", &id.engine),
        line("Contract digest", &id.contract_digest),
    )
}
