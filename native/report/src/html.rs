// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Static presentation of the frame assembled from one typed ruling. No verdict is inferred here.

use serde_json::{json, Map, Value};

#[path = "html_arch.rs"]
mod arch;
#[path = "html_cases.rs"]
mod cases;
#[path = "html_causes.rs"]
mod causes;
#[path = "html_components.rs"]
mod components;
#[path = "html_footer.rs"]
mod footer;
#[path = "html_frame.rs"]
mod frame;
#[path = "html_text.rs"]
mod markup;
#[path = "html_places.rs"]
mod places;
#[path = "html_rules.rs"]
mod rules;
#[path = "html_shell.rs"]
mod shell;
#[path = "html_unknown.rs"]
mod unknown;
#[path = "html_verdict.rs"]
mod verdict;

pub(super) fn render(frame: &Map<String, Value>) -> Result<Value, serde_json::Error> {
    let value = Value::Object(frame.clone());
    let status = &value["status"];
    let view = frame::Frame::of(&value);
    let places = places::Places::of(&view);
    let names = cases::Names::of(&view);
    let subject = if view.head.is_empty() {
        format!("Report \u{b7} {}", view.status)
    } else {
        format!("Report \u{b7} {} \u{b7} commit {}", view.status, view.head)
    };
    let mut page = shell::start(&subject);
    page.push_str(&verdict::section(&view, &places));
    page.push_str(&arch::section(&view, &places, &names));
    page.push_str(&cases::section(&view, &places, &names));
    page.push_str(&unknown::section(&view, &names));
    page.push_str(&components::section(&view, &places, &names));
    page.push_str(&rules::section(&view));
    page.push_str(&footer::section(&view));
    page.push_str(shell::END);
    Ok(json!({"protocol": "archkeel-core-html-1", "status": status, "document": page}))
}

#[cfg(test)]
#[path = "html_blocks_tests.rs"]
mod blocks_tests;
#[cfg(test)]
#[path = "html_tests.rs"]
mod tests;
