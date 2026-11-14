// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Static presentation of the frame assembled from one typed ruling. No verdict is inferred here.

use std::collections::BTreeSet;

use serde_json::{json, Map, Value};

const START: &str = "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">\
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\
<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">\
<title>Archkeel report</title><style>\
body{font:1rem system-ui,sans-serif;max-width:80rem;margin:2rem auto;padding:0 1rem;color:#172331;background:#fff}\
table{border-collapse:collapse;width:100%}th,td{border:1px solid #8994a0;padding:.5rem;text-align:left;vertical-align:top}\
pre{white-space:pre-wrap}td,pre{overflow-wrap:anywhere}h1{border-bottom:3px solid;padding-bottom:.5rem}\
</style></head><body>\n";

fn escape(text: &str) -> String {
    let mut safe = String::new();
    for character in text.chars() {
        safe.push_str(match character {
            '&' => "&amp;",
            '<' => "&lt;",
            '>' => "&gt;",
            '"' => "&quot;",
            '\'' => "&#39;",
            _ => {
                safe.push(character);
                continue;
            }
        });
    }
    safe
}

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

fn compact(value: &Value) -> Result<String, serde_json::Error> {
    match value.as_str() {
        Some(text) => Ok(text.to_owned()),
        None => serde_json::to_string(value),
    }
}

fn citations<'a>(value: &'a Value, evidence: &mut BTreeSet<&'a str>) {
    evidence.extend(
        value["evidence"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(Value::as_str),
    );
}

fn detail<'a>(
    page: &mut String,
    value: &'a Value,
    evidence: &mut BTreeSet<&'a str>,
) -> Result<(), serde_json::Error> {
    citations(value, evidence);
    if let Some(fields) = value.as_object() {
        page.push_str("<dl>");
        for (key, value) in fields {
            page.push_str(&format!(
                "<dt>{}</dt><dd>{}</dd>",
                escape(key),
                escape(&compact(value)?)
            ));
        }
        page.push_str("</dl>\n");
    } else {
        page.push_str(&format!("<p>{}</p>\n", escape(&compact(value)?)));
    }
    Ok(())
}

fn violations(page: &mut String, value: &Value) -> Result<(), serde_json::Error> {
    page.push_str("<h2>Violations</h2>\n");
    let mut evidence = BTreeSet::new();
    for (id, rows) in value["details"].as_object().into_iter().flatten() {
        page.push_str(&format!("<h3>{}</h3>\n", escape(id)));
        match rows.as_array() {
            Some(rows) => {
                for row in rows {
                    detail(page, row, &mut evidence)?;
                }
            }
            None => detail(page, rows, &mut evidence)?,
        }
    }
    for gap in value["collection_gaps"].as_array().into_iter().flatten() {
        citations(gap, &mut evidence);
    }
    page.push_str("<h3>Evidence locations</h3><table><thead><tr><th>Evidence</th><th>File</th><th>Line</th></tr></thead><tbody>\n");
    for id in evidence {
        let location = &value["locations"][id];
        let line = location["line"]
            .as_i64()
            .map_or_else(|| "unavailable".to_owned(), |line| line.to_string());
        page.push_str(&format!(
            "<tr><td>{}</td><td>{}</td><td>{}</td></tr>\n",
            escape(id),
            escape(text(&location["path"])),
            escape(&line)
        ));
    }
    page.push_str("</tbody></table>\n");
    Ok(())
}

pub(super) fn render(frame: &Map<String, Value>) -> Result<Value, serde_json::Error> {
    let value = Value::Object(frame.clone());
    let status = &value["status"];
    let mut page = format!("{START}<h1>Verdict: {}</h1>\n", escape(text(status)));
    page.push_str("<p>This is a static report of one run. No graph is available.</p>\n");
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
    violations(&mut page, &value)?;
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
            "contract_digest": value["contract_digest"]
        }),
    )?;
    let digest = text(&value["engine"])
        .strip_prefix("archkeel-core ")
        .unwrap_or("unavailable");
    page.push_str(&format!(
        "<h2>Tool</h2><dl><dt>Core code digest</dt><dd>{}</dd></dl>\n",
        escape(digest)
    ));
    page.push_str("</body></html>\n");
    Ok(json!({"protocol": "archkeel-core-html-1", "status": status, "document": page}))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_text_is_escaped_without_truncation() {
        let plant = format!("<script>\"'&\u{fffd}{}", "x".repeat(100_000));
        let safe = escape(&plant);
        assert!(safe.starts_with("&lt;script&gt;&quot;&#39;&amp;\u{fffd}"));
        assert!(safe.ends_with(&"x".repeat(100_000)));
        let frame = json!({"status": "UNKNOWN", "rules": {plant.clone(): [plant.clone(), "UNKNOWN"]},
            "explained": {plant.clone(): plant.clone()}, "locations": {"e": {"path": plant.clone()}},
            "unsupported": {"rules": plant.clone()}, "self_test": {"collect": {"refused": plant.clone()}}});
        let rendered = render(frame.as_object().unwrap()).unwrap();
        let document = rendered["document"].as_str().unwrap();
        assert!(document.contains(&safe));
        assert!(!document.contains("<script>"));
        assert!(document.contains("<h1>Verdict: UNKNOWN</h1>"));
    }

    #[test]
    fn compact_details_keep_cited_locations_and_unknown_shapes_without_injection() {
        let frame = json!({"status": "FAIL", "rules": {}, "details": {"R<script>": [
            {"source": "<script>\"&", "target": null, "cause": "bad", "evidence": ["e"]},
            ["unknown<script>", 42]]}, "locations": {
                "e": {"path": "<script>\"&.rs", "line": 7},
                "unused": {"path": "not-cited.rs", "line": 8}},
            "collection_gaps": [{"evidence": ["missing"]}]});
        let rendered = render(frame.as_object().unwrap()).unwrap();
        let document = rendered["document"].as_str().unwrap();
        let details = document
            .split("<h2>Violations</h2>")
            .nth(1)
            .unwrap()
            .split("<h2>Gaps</h2>")
            .next()
            .unwrap();
        assert!(!details.contains("<pre>"));
        assert!(details.contains("<dt>source</dt><dd>&lt;script&gt;&quot;&amp;</dd>"));
        assert!(details.contains("&lt;script&gt;&quot;&amp;.rs"));
        assert!(details.contains("unknown&lt;script&gt;"));
        assert!(details.contains("missing") && details.contains("unavailable"));
        assert!(!details.contains("not-cited.rs"));
        assert!(!document.contains("<script>"));
    }
}
