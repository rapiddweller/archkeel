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

use crate::dual_run::{InterfaceRow, PartRow, SystemFrame};

/// The keys whose maps of all parts the system frame holds; a key that two parts use refuses it.
const RULE_MAPS: [&str; 7] = [
    "rules",
    "rule_rationales",
    "explained",
    "violations",
    "details",
    "unknown_kinds",
    "beyond",
];

/// The frame bytes of the system from the frame bytes of its parts.
pub(crate) fn join(
    system: &System,
    parts: &[Vec<u8>],
    (html, topology): (bool, bool),
) -> Result<Vec<u8>, String> {
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
    let typed: Vec<PartFrame> = frames.iter().map(PartFrame::of).collect();
    let statuses: Vec<Option<Status>> = typed.iter().map(|part| part.status).collect();
    let status = system_status(&statuses);
    frame.insert("status".to_owned(), json!(status));
    for key in RULE_MAPS {
        frame.insert(key.to_owned(), Value::Object(disjoint(&frames, key)?));
    }
    frame.insert("locations".to_owned(), Value::Object(locations(&frames)?));
    frame.insert("sections".to_owned(), Value::Object(sections(&frames)));
    // A part that names its whole contract in one text makes it the text of the system (the
    // first such part, as for the refused collect): its gap row is then the only one (AD-546).
    let whole = frames.iter().find(|part| whole_contract(part).is_some());
    let gaps = match whole {
        Some(part) => list(part, "gaps").collect(),
        None => frames.iter().flat_map(|part| list(part, "gaps")).collect(),
    };
    frame.insert("gaps".to_owned(), Value::Array(gaps));
    let rows = frames.iter().flat_map(|part| list(part, "collection_gaps"));
    frame.insert("collection_gaps".to_owned(), Value::Array(rows.collect()));
    let excluded: Vec<Value> = frames
        .iter()
        .flat_map(|part| list(part, "excluded_sources"))
        .collect();
    if !excluded.is_empty() {
        frame.insert("excluded_sources".to_owned(), Value::Array(excluded));
    }
    join_premises(&frames, &mut frame)?;
    let ids: Vec<&str> = system.parts.iter().map(|part| part.id.as_str()).collect();
    let scope = scope(&ids, &typed, status)?;
    frame.insert("scope".to_owned(), scope.clone());
    if let Some(premise) = premise(&frames) {
        frame.insert("premise".to_owned(), json!(premise));
    }
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
        interfaces: system
            .interfaces
            .iter()
            .map(|i| InterfaceRow {
                id: i.id.clone(),
                source: i.source.clone(),
                target: i.target.clone(),
                title: i.title.clone(),
                schema: i.schema.clone(),
            })
            .collect(),
    };
    if topology || html {
        let sources: Vec<_> = system.parts.iter().zip(&frames).collect();
        if let Some(found) = crate::system_topology::topology(
            &sources,
            scope.as_str().filter(|word| *word != "complete"),
        )? {
            frame.insert("topology".to_owned(), found);
        }
        if let Some(found) = crate::system_topology::explain(&frames) {
            frame.insert("explain".to_owned(), found);
        }
    }
    let described = serde_json::to_value(described).map_err(|error| error.to_string())?;
    frame.insert("system".to_owned(), described);
    if html {
        let page = archkeel_report::page(&frame).map_err(|error| error.to_string())?;
        frame.insert("html".to_owned(), page);
    }
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

/// The premises of the parts (AD-664, #1549): a PASS under a declared door reach or a stated
/// external user stays qualified in the system frame, and the run names its premises in words.
fn join_premises(
    frames: &[Map<String, Value>],
    frame: &mut Map<String, Value>,
) -> Result<(), String> {
    // AD-664: a PASS under a declared door reach stays qualified in the system frame.
    let assumed = disjoint(frames, "assumed")?;
    if !assumed.is_empty() {
        frame.insert("assumed".to_owned(), Value::Object(assumed));
    }
    let doors: Vec<Value> = frames
        .iter()
        .flat_map(|part| list(part, "door_reach"))
        .collect();
    let door_count = doors.len();
    if !doors.is_empty() {
        frame.insert("door_reach".to_owned(), Value::Array(doors));
    }
    // #1549: each premise of a part stays with its rule, and the run names them in words.
    let premises = disjoint(frames, "premises")?;
    let mut pairs: Vec<(&str, &str)> = Vec::new();
    for rows in premises.values() {
        for row in Value::as_array(rows).into_iter().flatten() {
            let row: &Value = row;
            let kind = Value::as_str(&row["kind"]).unwrap_or("");
            pairs.push((kind, Value::as_str(&row["subject"]).unwrap_or("")));
        }
    }
    let words = archkeel_report::premise_words(door_count, pairs.into_iter())
        .map_err(|why| format!("system: {why}"))?;
    if !premises.is_empty() {
        frame.insert("premises".to_owned(), Value::Object(premises));
    }
    if let Some(words) = words {
        frame.insert("assuming".to_owned(), json!(words));
    }
    Ok(())
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

/// The assumptions that the collectors of the parts state (AD-540), each once in the order of the
/// parts: a part whose proofs rest on a premise keeps it in the system frame.
fn premise(frames: &[Map<String, Value>]) -> Option<String> {
    let mut found: Vec<&str> = Vec::new();
    for text in frames
        .iter()
        .filter_map(|part| part.get("premise")?.as_str())
    {
        if !found.contains(&text) {
            found.push(text);
        }
    }
    let (_, prefixes) = found.split_last_mut()?;
    for text in prefixes {
        *text = text.trim_end_matches('.');
    }
    Some(found.join("; "))
}

/// The scope of one part: complete, or open with the value that the frame of the part carries.
#[derive(Clone, Debug, PartialEq)]
enum PartScope {
    Complete,
    Open(Value),
}

/// What the join reads of the frame of one part, typed once: its status (none when unreadable)
/// and its scope (a frame without a scope is complete).
struct PartFrame {
    status: Option<Status>,
    scope: PartScope,
    /// The first row that explains why the part is not PASS: the text of a rule row that is
    /// UNKNOWN, of a rule without a decision, or of a gap.
    explanation: Option<String>,
}

impl PartFrame {
    fn of(part: &Map<String, Value>) -> Self {
        let status = part
            .get("status")
            .and_then(|status| serde_json::from_value(status.clone()).ok());
        let scope = match part.get("scope") {
            None => PartScope::Complete,
            Some(scope) if scope.as_str() == Some("complete") => PartScope::Complete,
            Some(open) => PartScope::Open(open.clone()),
        };
        PartFrame {
            status,
            scope,
            explanation: explanation(part),
        }
    }
}

/// The first explaining row of a part frame: an UNKNOWN rule (by rule id), a rule without a
/// decision, or a gap. A part that is UNKNOWN has one, or the frame is unsound.
fn explanation(part: &Map<String, Value>) -> Option<String> {
    let text = |value: &Value| value.as_str().map(str::to_owned);
    let rule = map(part, "explained").find_map(|(_, why)| text(why));
    let unsupported = || match part.get("unsupported")?.get("rules")? {
        Value::Object(rules) => rules.values().find_map(text),
        other => text(other),
    };
    let gap = || {
        ["gaps", "collection_gaps"]
            .into_iter()
            .flat_map(|key| list(part, key))
            .find_map(|gap| text(gap.get("reason")?))
    };
    rule.or_else(unsupported).or_else(gap)
}

/// The scope of the system: the reason of the first open part; else, when the system is UNKNOWN,
/// the explaining row of the first part that is not PASS (an UNKNOWN system never says
/// `complete`); else `complete`. An UNKNOWN part without an explaining row refuses the system.
fn scope(ids: &[&str], parts: &[PartFrame], status: Status) -> Result<Value, String> {
    let open = parts.iter().find_map(|part| match &part.scope {
        PartScope::Complete => None,
        PartScope::Open(reason) => Some(reason.clone()),
    });
    if let Some(reason) = open {
        return Ok(reason);
    }
    for (id, part) in ids.iter().zip(parts) {
        if part.status != Some(Status::Pass)
            && part.status != Some(Status::Fail)
            && part.explanation.is_none()
        {
            return Err(format!(
                "system: the part {id} is UNKNOWN without an explaining row"
            ));
        }
    }
    if status != Status::Unknown {
        return Ok(json!("complete"));
    }
    let why = parts
        .iter()
        .filter(|part| part.status != Some(Status::Pass))
        .find_map(|part| part.explanation.clone());
    Ok(why.map_or_else(|| json!("complete"), Value::from))
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

/// The text of a part that holds its whole contract (`unsupported.rules` is one text).
fn whole_contract(part: &Map<String, Value>) -> Option<&Value> {
    part.get("unsupported")?
        .get("rules")
        .filter(|rules| rules.is_string())
}

/// What the parts leave unsupported: the rules and sections of all parts, and a report reason.
/// A part that holds its whole contract names it in one text: the system keeps the first one.
fn unsupported(frames: &[Map<String, Value>]) -> Value {
    let parts: Vec<&Map<String, Value>> = frames
        .iter()
        .filter_map(|part| part.get("unsupported").and_then(Value::as_object))
        .collect();
    let mut joined = Map::new();
    for key in ["rules", "sections"] {
        let mut found = Map::new();
        let mut whole = None;
        for part in &parts {
            match part.get(key) {
                Some(Value::Object(entries)) => found.extend(entries.clone()),
                Some(text @ Value::String(_)) => whole = whole.or(Some(text)),
                _ => {}
            }
        }
        let value = whole.cloned().unwrap_or(Value::Object(found));
        joined.insert(key.to_owned(), value);
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

#[cfg(test)]
#[path = "system_tests.rs"]
mod tests;
