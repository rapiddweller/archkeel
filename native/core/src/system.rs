// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The frame of a system run (AD-616): one scan for each part of a system document, joined into
//! one frame. The rows of each part stay as they are; a rule id that two parts use refuses the run.
//! The status comes from the status rule of the core (`archkeel_report::system_status`). The part
//! `system` names each part with its profile, which the Language view of the report reads.

use std::collections::BTreeMap;

use archkeel_collect::{System, SystemPart};
use archkeel_report::{system_status, Status};
use serde_json::{json, Map, Value};

use crate::dual_run::{PartRow, SystemFrame};

/// The keys whose maps of all parts the system frame holds; a key that two parts use refuses it.
const RULE_MAPS: [&str; 6] = [
    "rules",
    "explained",
    "violations",
    "details",
    "unknown_kinds",
    "beyond",
];

/// The frame bytes of the system from the frame bytes of its parts.
pub(crate) fn join(system: &System, parts: &[Vec<u8>]) -> Result<Vec<u8>, String> {
    let frames = parts
        .iter()
        .map(|part| serde_json::from_slice::<Map<String, Value>>(part))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| format!("system: a part frame: {error}"))?;
    let first = frames.first().ok_or("system: no part")?;
    let mut frame = Map::new();
    for key in ["engine", "protocol"] {
        frame.insert(
            key.to_owned(),
            first.get(key).cloned().unwrap_or(Value::Null),
        );
    }
    let statuses: Vec<Option<Status>> = frames
        .iter()
        .map(|part| serde_json::from_value(part.get("status")?.clone()).ok())
        .collect();
    frame.insert("status".to_owned(), json!(system_status(&statuses)));
    for key in RULE_MAPS {
        frame.insert(key.to_owned(), Value::Object(disjoint(&frames, key)?));
    }
    frame.insert("locations".to_owned(), Value::Object(locations(&frames)?));
    frame.insert("sections".to_owned(), Value::Object(sections(&frames)));
    for key in ["gaps", "collection_gaps"] {
        let rows = frames.iter().flat_map(|part| list(part, key)).collect();
        frame.insert(key.to_owned(), Value::Array(rows));
    }
    frame.insert("scope".to_owned(), scope(&frames));
    frame.insert("measures".to_owned(), Value::Null);
    let digest = archkeel_facts::identity::sha256_hex(&system.document.1);
    frame.insert("contract_digest".to_owned(), json!(digest));
    frame.insert("self_test".to_owned(), self_test(system, &frames, &digest));
    frame.insert("unsupported".to_owned(), unsupported(&frames));
    let rows = system.parts.iter().zip(&frames).zip(statuses);
    let parts = rows
        .map(|((part, found), status)| row(part, found, status))
        .collect();
    let described = SystemFrame {
        title: system.title.clone(),
        document: system.document.0.clone(),
        parts,
    };
    let described = serde_json::to_value(described).map_err(|error| error.to_string())?;
    frame.insert("system".to_owned(), described);
    serde_json::to_vec(&frame).map_err(|error| error.to_string())
}

fn map<'a>(
    part: &'a Map<String, Value>,
    key: &str,
) -> impl Iterator<Item = (&'a String, &'a Value)> {
    part.get(key)
        .and_then(Value::as_object)
        .into_iter()
        .flatten()
}

fn list<'a>(part: &'a Map<String, Value>, key: &str) -> impl Iterator<Item = Value> + 'a {
    part.get(key)
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .cloned()
}

/// The map `key` of all parts: a rule id names one rule of one part.
fn disjoint(frames: &[Map<String, Value>], key: &str) -> Result<Map<String, Value>, String> {
    let mut joined = Map::new();
    for (name, value) in frames.iter().flat_map(|part| map(part, key)) {
        if joined.insert(name.clone(), value.clone()).is_some() {
            return Err(format!("system: two parts name the rule {name} ({key})"));
        }
    }
    Ok(joined)
}

/// The locations of all parts. An evidence id is a digest of its place, so one id names one place.
fn locations(frames: &[Map<String, Value>]) -> Result<Map<String, Value>, String> {
    let mut joined = Map::new();
    for (id, place) in frames.iter().flat_map(|part| map(part, "locations")) {
        match joined.insert(id.clone(), place.clone()) {
            Some(other) if other != *place => {
                return Err(format!("system: the evidence {id} names two places"))
            }
            _ => {}
        }
    }
    Ok(joined)
}

/// The rows of each section, of all parts.
fn sections(frames: &[Map<String, Value>]) -> Map<String, Value> {
    let mut joined: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    for (name, rows) in frames.iter().flat_map(|part| map(part, "sections")) {
        let rows = rows.as_array().into_iter().flatten().cloned();
        joined.entry(name.clone()).or_default().extend(rows);
    }
    joined
        .into_iter()
        .map(|(name, rows)| (name, Value::Array(rows)))
        .collect()
}

/// `complete` when each part is complete, else the reason of the first part that is not.
fn scope(frames: &[Map<String, Value>]) -> Value {
    let open = frames
        .iter()
        .filter_map(|part| part.get("scope"))
        .find(|scope| scope.as_str() != Some("complete"));
    open.cloned().unwrap_or_else(|| json!("complete"))
}

/// The self-test of the system: the rule kinds of all parts, the files of all replies, and the
/// contract files of all parts with the system document. The collection request is the one of the
/// first part: each part reads the same snapshot, and the shell binds its identity (AD-438).
fn self_test(system: &System, frames: &[Map<String, Value>], digest: &str) -> Value {
    let tests: Vec<&Map<String, Value>> = frames
        .iter()
        .filter_map(|part| part.get("self_test").and_then(Value::as_object))
        .collect();
    let rules: Map<String, Value> = tests
        .iter()
        .flat_map(|test| test.get("contract").and_then(|c| c.get("rules")))
        .flat_map(|rules| rules.as_object().into_iter().flatten())
        .map(|(id, kind)| (id.clone(), kind.clone()))
        .collect();
    let other = |key: &str, word: &str| {
        let found = tests.iter().filter_map(|test| test.get(key));
        found
            .into_iter()
            .find(|value| value.get(word).is_none())
            .cloned()
    };
    let contract = other("contract", "rules").unwrap_or_else(|| json!({ "rules": rules }));
    let files: u64 = tests
        .iter()
        .filter_map(|test| test.get("reply").and_then(|r| r.get("files")))
        .filter_map(Value::as_u64)
        .sum();
    let reply = other("reply", "files").unwrap_or_else(|| json!({ "files": files }));
    let collects: Vec<&Value> = tests
        .iter()
        .filter_map(|test| test.get("collect"))
        .collect();
    let refused = collects.iter().find(|c| c.get("refused").is_some());
    let collect = match (refused, collects.first()) {
        (Some(refused), _) => (*refused).clone(),
        (None, Some(first)) => {
            let mut files: Map<String, Value> = collects
                .iter()
                .filter_map(|c| c.get("contract_files").and_then(Value::as_object))
                .flatten()
                .map(|(name, digest)| (name.clone(), digest.clone()))
                .collect();
            files.insert(system.document.0.clone(), json!(digest));
            json!({ "request": first.get("request"), "contract_files": files })
        }
        (None, None) => json!({ "refused": "system: no part ran the collector" }),
    };
    json!({ "contract": contract, "reply": reply, "collect": collect })
}

/// What the parts leave unsupported: the rules and sections of all parts, and a report reason.
fn unsupported(frames: &[Map<String, Value>]) -> Value {
    let parts: Vec<&Map<String, Value>> = frames
        .iter()
        .filter_map(|part| part.get("unsupported").and_then(Value::as_object))
        .collect();
    let mut joined = Map::new();
    for key in ["rules", "sections"] {
        let mut found = Map::new();
        for part in &parts {
            match part.get(key) {
                Some(Value::Object(entries)) => found.extend(entries.clone()),
                // A part that holds its whole contract names it in one text: the system keeps it.
                Some(text @ Value::String(_)) => {
                    joined.insert(key.to_owned(), text.clone());
                }
                _ => {}
            }
        }
        joined.entry(key.to_owned()).or_insert(Value::Object(found));
    }
    let report = parts
        .iter()
        .find_map(|part| part.get("report").filter(|r| !r.is_null()));
    joined.insert("report".to_owned(), report.cloned().unwrap_or(Value::Null));
    Value::Object(joined)
}

fn row(part: &SystemPart, frame: &Map<String, Value>, status: Option<Status>) -> PartRow {
    let request = frame
        .get("self_test")
        .and_then(|test| test.get("collect"))
        .and_then(|collect| collect.get("request"));
    let profile = request
        .and_then(|request| request.get("resolver"))
        .and_then(|resolver| resolver.get("language"))
        .and_then(Value::as_str)
        .map(str::to_owned);
    PartRow {
        id: part.id.clone(),
        title: part.title.clone(),
        config: part.config.clone(),
        profile,
        status: status.unwrap_or(Status::Unknown),
        rules: map(frame, "rules").map(|(id, _)| id.clone()).collect(),
    }
}
