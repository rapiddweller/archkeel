// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Static presentation of the frame assembled from one typed ruling. No verdict is inferred here.

use serde_json::{json, Map, Value};

#[path = "html_arch.rs"]
mod arch;
#[path = "html_cases.rs"]
mod cases;
#[path = "html_frame.rs"]
mod frame;
#[path = "html_places.rs"]
mod places;
#[path = "html_shell.rs"]
mod shell;
#[path = "html_text.rs"]
mod text;
#[path = "html_verdict.rs"]
mod verdict;

use text::escape;

fn text(value: &Value) -> &str {
    value.as_str().unwrap_or("unavailable")
}

fn block(page: &mut String, heading: &str, value: &Value) -> Result<(), serde_json::Error> {
    let encoded = serde_json::to_string_pretty(value)?;
    page.push_str(&format!(
        "<h2>{heading}</h2><pre>{}</pre>\n",
        escape(&encoded)
    ));
    Ok(())
}

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
    let rules = value["rules"].as_object();
    let mut counts = Map::new();
    for word in ["PASS", "FAIL", "UNKNOWN", "DECLARATION"] {
        let count = rules
            .into_iter()
            .flat_map(|rows| rows.values())
            .filter(|row| row.get(1).and_then(Value::as_str) == Some(word))
            .count();
        counts.insert(word.to_owned(), json!(count));
    }
    counts.insert("violations".to_owned(), json!(value["violations"]));
    counts.insert("rules".to_owned(), json!(rules.map_or(0, Map::len)));
    block(&mut page, "Counts", &Value::Object(counts))?;
    page.push_str("<h2>Rules</h2><table><thead><tr><th>Id</th><th>Kind</th><th>Status</th><th>Explanation</th></tr></thead><tbody>\n");
    for (id, row) in rules.into_iter().flatten() {
        let explanation = match text(&row[1]) {
            "FAIL" => format!("{} violations; see details below", value["violations"][id]),
            "UNKNOWN" => text(&value["explained"][id]).to_owned(),
            "DECLARATION" => "Permission declaration; no verdict".to_owned(),
            _ => "Proved by the core".to_owned(),
        };
        page.push_str(&format!(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>\n",
            escape(id),
            escape(text(&row[0])),
            escape(text(&row[1])),
            escape(&explanation)
        ));
    }
    page.push_str("</tbody></table>\n");
    block(
        &mut page,
        "Gaps",
        &json!({"scope": value["scope"], "reasons": value["explained"],
        "kinds": value["unknown_kinds"], "collection": value["collection_gaps"], "input": value["self_test"]}),
    )?;
    block(&mut page, "Unsupported", &value["unsupported"])?;
    block(
        &mut page,
        "Request identity",
        &json!({
            "snapshot": value["self_test"]["collect"]["request"]["snapshot"],
            "contract_digest": value["contract_digest"],
            "contract_files": value["self_test"]["collect"]["contract_files"]
        }),
    )?;
    let digest = text(&value["engine"])
        .strip_prefix("archkeel-core ")
        .unwrap_or("unavailable");
    page.push_str(&format!(
        "<h2>Tool</h2><dl><dt>Core code digest</dt><dd>{}</dd></dl>\n",
        escape(digest)
    ));
    page.push_str(shell::END);
    Ok(json!({"protocol": "archkeel-core-html-1", "status": status, "document": page}))
}

#[cfg(test)]
#[path = "html_tests.rs"]
mod tests;
