// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Static presentation of the frame assembled from one typed ruling. No verdict is inferred here.

use serde_json::{json, Map, Value};
use std::collections::BTreeMap;

#[path = "html_arch.rs"]
mod arch;
#[path = "html_atlas.rs"]
mod atlas;
#[path = "html_atlas_dirs.rs"]
mod atlas_dirs;
#[path = "html_atlas_groups.rs"]
mod atlas_groups;
#[path = "html_atlas_levels.rs"]
mod atlas_levels;
#[path = "html_atlas_members.rs"]
mod atlas_members;
#[path = "html_atlas_node.rs"]
mod atlas_node;
#[path = "html_atlas_tree.rs"]
mod atlas_tree;
#[path = "html_cases.rs"]
mod cases;
#[path = "html_causes.rs"]
mod causes;
#[path = "html_components.rs"]
mod components;
#[path = "html_explorer.rs"]
mod explorer;
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
#[path = "html_status.rs"]
mod status;
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
        format!("Report \u{b7} {}", status::run_word(view.status))
    } else {
        format!(
            "Report \u{b7} {} \u{b7} commit {}",
            status::run_word(view.status),
            view.head
        )
    };
    let mut page = shell::start(&subject);
    page.push_str(&verdict::section(&view, &places));
    if view.topology.is_some() {
        let packed = pack_frame(frame)?;
        page.push_str(&format!(
            "<script type=\"application/json\" id=\"run-frame-data\">{}</script>",
            serde_json::to_string(&packed)?.replace('<', "\\u003c")
        ));
    }
    page.push_str(&arch::section(&view, &places, &names));
    page.push_str(&cases::section(&view, &places, &names));
    page.push_str(&unknown::section(&view, &names));
    page.push_str(&components::section(&view, &places, &names));
    page.push_str(&rules::section(&view));
    page.push_str(&footer::section(&view));
    page.push_str(shell::END);
    Ok(json!({"protocol": "archkeel-core-html-1", "status": status, "document": page}))
}

fn intern<'a>(
    text: &'a str,
    ids: &mut BTreeMap<&'a str, usize>,
    strings: &mut Vec<&'a str>,
) -> usize {
    *ids.entry(text).or_insert_with(|| {
        strings.push(text);
        strings.len() - 1
    })
}

fn pack_frame(frame: &Map<String, Value>) -> Result<Value, serde_json::Error> {
    let mut rest = frame.clone();
    let Some(Value::Array(gaps)) = rest.remove("collection_gaps") else {
        return Ok(json!({"frame_json": serde_json::to_string(frame)?}));
    };
    let mut strings = Vec::new();
    let mut ids = BTreeMap::new();
    let mut rows = Vec::new();
    for gap in &gaps {
        let Some(object) = gap.as_object() else {
            rows.push(json!({"raw": serde_json::to_string(gap)?}));
            continue;
        };
        let fields = ["kind", "reason", "subjects", "evidence", "detail"];
        if object.keys().any(|key| !fields.contains(&key.as_str())) {
            rows.push(json!({"raw": serde_json::to_string(gap)?}));
            continue;
        }
        let (Some(kind), Some(reason), Some(subjects), Some(evidence)) = (
            object.get("kind").and_then(Value::as_str),
            object.get("reason").and_then(Value::as_str),
            object.get("subjects").and_then(Value::as_array),
            object.get("evidence").and_then(Value::as_array),
        ) else {
            rows.push(json!({"raw": serde_json::to_string(gap)?}));
            continue;
        };
        let subjects = subjects
            .iter()
            .map(Value::as_str)
            .collect::<Option<Vec<_>>>();
        let evidence = evidence
            .iter()
            .map(Value::as_str)
            .collect::<Option<Vec<_>>>();
        let (Some(subjects), Some(evidence)) = (subjects, evidence) else {
            rows.push(json!({"raw": serde_json::to_string(gap)?}));
            continue;
        };
        if object.get("detail").is_some_and(|item| !item.is_string()) {
            rows.push(json!({"raw": serde_json::to_string(gap)?}));
            continue;
        }
        let mut row = vec![
            json!(intern(kind, &mut ids, &mut strings)),
            json!(intern(reason, &mut ids, &mut strings)),
            json!(subjects
                .iter()
                .map(|text| intern(text, &mut ids, &mut strings))
                .collect::<Vec<_>>()),
            json!(evidence
                .iter()
                .map(|text| intern(text, &mut ids, &mut strings))
                .collect::<Vec<_>>()),
        ];
        if let Some(detail) = object.get("detail").and_then(Value::as_str) {
            row.push(json!(intern(detail, &mut ids, &mut strings)));
        }
        rows.push(Value::Array(row));
    }
    Ok(json!({"frame_json": serde_json::to_string(&rest)?, "strings": strings, "gaps": rows}))
}

#[cfg(test)]
#[path = "html_blocks_tests.rs"]
mod blocks_tests;
#[cfg(test)]
#[path = "html_explorer_tests.rs"]
mod explorer_tests;
#[cfg(test)]
#[path = "html_tests.rs"]
mod tests;
