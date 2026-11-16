// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the frame of a system run keeps the premise of each part (AD-540, AD-616), so the
// shell accepts a system with a Python part.

use archkeel_collect::{System, SystemPart};
use serde_json::{json, Value};

use super::join;

fn system(ids: &[&str]) -> System {
    let parts = ids.iter().map(|id| SystemPart {
        id: (*id).to_owned(),
        title: (*id).to_owned(),
        config: format!("{id}.toml"),
        responsibilities: Vec::new(),
        forbidden_responsibilities: Vec::new(),
        provides: Vec::new(),
    });
    System {
        title: "Fixture".to_owned(),
        document: ("system.json".to_owned(), b"{}".to_vec()),
        parts: parts.collect(),
        interfaces: Vec::new(),
    }
}

fn part(status: &str, premise: Option<&str>) -> Vec<u8> {
    let mut frame = json!({"engine": "e", "protocol": "p", "status": status, "scope": "complete"});
    if let Some(text) = premise {
        frame["premise"] = json!(text);
    }
    serde_json::to_vec(&frame).unwrap()
}

fn joined(parts: &[Vec<u8>]) -> Value {
    let ids: Vec<String> = (0..parts.len()).map(|n| format!("p{n}")).collect();
    let ids: Vec<&str> = ids.iter().map(String::as_str).collect();
    serde_json::from_slice(&join(&system(&ids), parts, (false, false)).unwrap()).unwrap()
}

#[test]
fn the_system_frame_keeps_the_premise_of_each_part_once() {
    let shell = "code outside the scan roots hands in no module object of the scan";
    let frame = joined(&[part("PASS", Some(shell)), part("PASS", None)]);
    assert_eq!(frame["premise"], json!(shell));
    let frame = joined(&[part("PASS", Some(shell)), part("PASS", Some(shell))]);
    assert_eq!(frame["premise"], json!(shell));
    let frame = joined(&[part("PASS", Some("a")), part("FAIL", Some("b"))]);
    assert_eq!(
        (frame["premise"].clone(), frame["status"].clone()),
        (json!("a; b"), json!("FAIL"))
    );
    assert_eq!(joined(&[part("PASS", None)]).get("premise"), None);
}
