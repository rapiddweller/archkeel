// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// System topology and interface presentation.

use super::*;

// AD-618: a part of a system is one top box; its layers are boxes inside it, and its components
// sit in the layer that they name. The verdict of the part is the weakest verdict inside it.
#[test]
fn a_part_of_a_system_holds_its_own_layers() {
    let comp = |id: &str, parent: Option<&str>, layer: Option<&str>| json!({"id": id, "name": id, "parent": parent, "layer": layer});
    let frame = json!({"status": "UNKNOWN", "topology": {
        "components": [comp("PART:a", None, None), comp("A1", Some("PART:a"), Some("L1")),
            comp("A2", Some("PART:a"), Some("L2")), comp("PART:b", None, None),
            comp("B1", Some("PART:b"), Some("L1"))],
        "modules": [{"name": "m.a1", "path": "a1", "component": "A1", "language": "python"},
            {"name": "m.b1", "path": "b1", "component": "B1", "language": "rust"}],
        "layers": [{"part": "PART:a", "rule": "R", "layers": ["L1", "L2"]},
            {"part": "PART:b", "rule": "S", "layers": ["L1", "L2"]}]},
        "collection_gaps": [{"kind": "collection_gap", "subjects": ["m.b1"], "reason": "macro"}]});
    let data = payload(&document(&frame));
    let parent = |id: &str| {
        let found = data["atlas"]["components"].as_array().unwrap();
        let of = |id: &str| found.iter().find(|c| c["id"] == id).unwrap().clone();
        (
            of(id)["parent_id"].clone(),
            of(id)["status"].clone(),
            of(id)["language"].clone(),
        )
    };
    assert_eq!(parent("LAYER:PART:a:L1").0, json!("PART:a"));
    assert_eq!(parent("A1").0, json!("LAYER:PART:a:L1"));
    assert_eq!(parent("A2").0, json!("LAYER:PART:a:L2"));
    assert_eq!(parent("B1").0, json!("LAYER:PART:b:L1"));
    // Each part names the language of its modules; the gap in b holds part b only.
    assert_eq!(parent("PART:a").2, json!("python"));
    assert_eq!(parent("PART:b").2, json!("rust"));
    assert_eq!(parent("PART:a").1, json!("PASS"));
    assert_eq!(parent("PART:b").1, json!("UNKNOWN"));
}

// AD-620: an interface between two parts is an edge with no import site, named by its title; it is
// no deviation and no declared-but-unused requirement.
#[test]
fn an_interface_between_two_parts_is_one_named_edge() {
    let comp = |id: &str| json!({"id": id, "name": id, "parent": null, "layer": null});
    let frame = json!({"status": "PASS",
        "topology": {"components": [comp("PART:a"), comp("PART:b")], "modules": []},
        "system": {"interfaces": [{"id": "i", "source": "a", "target": "b",
            "title": "Wire protocol", "schema": "schema/x.json"}]}});
    let data = payload(&document(&frame));
    let root = data["atlas"]["levels"]
        .as_array()
        .unwrap()
        .iter()
        .find(|level| level["parent_id"].is_null())
        .unwrap();
    let edges = root["edges"].as_array().unwrap();
    assert_eq!(edges.len(), 1);
    assert_eq!(edges[0]["crossing"], json!("Wire protocol"));
    assert_eq!(edges[0]["import_sites"], json!(0));
    assert!(root["deviation_ids"].as_array().unwrap().is_empty());
}

#[test]
fn system_orders_belong_to_their_parts() {
    let frame = json!({"status": "PASS", "topology": {
        "components": [
            {"id": "PART:a", "name": "a"}, {"id": "PART:b", "name": "b"},
            {"id": "A1", "name": "A1", "parent": "PART:a", "layer": "domain"},
            {"id": "A2", "name": "A2", "parent": "PART:a", "layer": "ui"},
            {"id": "B1", "name": "B1", "parent": "PART:b", "layer": "domain"},
            {"id": "B2", "name": "B2", "parent": "PART:b", "layer": "ui"}],
        "layers": [
            {"part": "PART:a", "rule": "A", "layers": ["domain", "ui"]},
            {"part": "PART:b", "rule": "B", "layers": ["ui", "domain"]}]}});
    let data = payload(&document(&frame));
    let components = data["atlas"]["components"].as_array().unwrap();
    let rank = |id: &str| components.iter().find(|c| c["id"] == id).unwrap()["layer_rank"].clone();
    assert_eq!(rank("LAYER:PART:a:domain"), json!(0));
    assert_eq!(rank("LAYER:PART:b:domain"), json!(1));
}

#[test]
fn interfaces_are_distinct_and_unchecked() {
    let frame = json!({"status": "PASS",
        "topology": {"components": [{"id": "PART:a", "name": "a"}, {"id": "PART:b", "name": "b"}]},
        "system": {"interfaces": [
            {"id": "one", "source": "a", "target": "b", "title": "One", "schema": "unrelated.json"},
            {"id": "two", "source": "a", "target": "b", "title": "Two", "schema": "unrelated.json"}]}});
    let data = payload(&document(&frame));
    let root = data["atlas"]["levels"]
        .as_array()
        .unwrap()
        .iter()
        .find(|level| level["parent_id"].is_null())
        .unwrap();
    let edges = root["edges"].as_array().unwrap();
    assert_eq!(edges.len(), 2);
    assert_eq!(edges[0]["interface_id"], "one");
    assert_eq!(edges[1]["interface_id"], "two");
    assert!(edges.iter().all(|edge| edge["status"] == "UNKNOWN"));
}
