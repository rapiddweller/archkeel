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
        "collection_gaps": [{"kind": "collection_gap", "subjects": ["m.b1"], "reason": "macro"}],
        "system": {"parts": [{"id": "a", "status": "PASS", "rules": []},
            {"id": "b", "status": "UNKNOWN", "rules": []}]}});
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
    // Each part names the language of its modules; the gap in b holds part b only. Part a is a
    // run of its own that decides every rule, so it keeps PASS under the open system (AD-730).
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

// E4 (#1451): the root of the Explorer of a system page is the title of the system.
#[test]
fn the_root_of_a_system_page_is_the_title_of_the_system() {
    let frame = json!({"status": "PASS", "topology": components(3, &[]),
        "system": {"title": "ArchKeel", "parts": []}});
    let data = payload(&document(&frame));
    assert_eq!(data["atlas"]["repository"], "ArchKeel");
    assert_eq!(
        data["navigation"],
        json!({"repository": "ArchKeel", "main_href": ""})
    );
    let alone = payload(&document(
        &json!({"status": "PASS", "topology": components(3, &[])}),
    ));
    assert_eq!(
        alone["navigation"],
        json!({"repository": "System", "main_href": ""})
    );
}

// E4: the page of a part reads "<part> of <system>" and links to the page of the system. The
// link is an input of the page: the frame does not carry it.
#[test]
fn the_page_of_a_part_names_its_system_and_links_up() {
    let part_of =
        json!({"part_of": {"system": "ArchKeel", "part": "Python shell", "href": "index.html"}});
    let ruling = json!({"status": "PASS", "topology": components(3, &[])});
    let written = crate::engine_frame::write(Ok(ruling), Ok(json!({})), &part_of, true);
    let frame: Value = serde_json::from_slice(&written.unwrap().into_bytes()).unwrap();
    assert!(frame.get("part_of").is_none());
    let data = payload(frame["html"]["document"].as_str().unwrap());
    assert_eq!(data["atlas"]["repository"], "Python shell of ArchKeel");
    assert_eq!(
        data["navigation"],
        json!({"repository": "Python shell of ArchKeel", "main_href": "", "part_title": "Python shell",
            "system_title": "ArchKeel", "system_href": "index.html"})
    );
}

// E5 (#1451): every Explorer payload has an atlas, so the Explorer has no other branch. The one
// maker of the payload is `atlas::payload`; a frame without a topology has no Explorer at all.
#[test]
fn every_explorer_payload_has_an_atlas() {
    let part_of = json!({"system": "S", "part": "P", "href": "s.html"});
    let frames = [
        json!({"status": "PASS", "topology": components(3, &[(0, 1)])}),
        json!({"status": "FAIL", "topology": components(13, &[(0, 1), (1, 2)])}),
        json!({"status": "PASS", "topology": components(2, &[]), "system": {"title": "S", "parts": []}}),
        json!({"status": "UNKNOWN", "topology": components(2, &[]), "part_of": part_of}),
    ];
    for frame in &frames {
        let data = payload(&document(frame));
        assert!(data["atlas"]["levels"]
            .as_array()
            .is_some_and(|l| !l.is_empty()));
        assert!(data["navigation"].get("module_ids").is_none());
    }
    let page = document(&json!({"status": "PASS"}));
    assert!(!page.contains("id=\"flow-data\""));
}

#[test]
fn explorer_preserves_complete_gap_messages_and_their_record_counts() {
    let frame = json!({
        "status": "UNKNOWN", "topology": components(2, &[]),
        "collection_gaps": [
            {"kind": "collection_gap", "reason": "The macro schemars::JsonSchema: not read",
             "subjects": ["m.a"], "evidence": ["e1"]},
            {"kind": "collection_gap", "reason": "The macro schemars::JsonSchema: not read",
             "subjects": ["m.b"], "evidence": []},
            {"kind": "collection_gap", "reason": "The macro schemars::Other: not read",
             "subjects": ["m.c"], "evidence": []}
        ],
        "locations": {"e1": {"path": "src/a.rs", "line": 42}}
        , "rules": {"A": ["complete_assignment", "UNKNOWN"], "B": ["complete_requires", "UNKNOWN"]},
        "explain": {"holds": {"rules": {"A": {"kind": "coverage_gaps", "total": 1},
                                         "B": {"kind": "coverage_gaps", "total": 1}}}}
    });
    let data = payload(&document(&frame));
    let atlas = &data["atlas"];
    assert_eq!(atlas["unknown_count"], 3);
    assert_eq!(atlas["gap_messages_complete"], true);
    assert_eq!(atlas["whole_scan_holds"], json!([{"gaps": 1, "rules": 2}]));
    let rows = atlas["unknowns"].as_array().unwrap();
    assert_eq!(rows.len(), 2);
    let first = rows.iter().find(|row| row["count"] == 2).unwrap();
    assert_eq!(first["reason"], "The macro schemars::JsonSchema: not read");
    assert_eq!(first["example"], "src/a.rs:42");
    assert!(atlas["architecture_href"].is_null());
}

#[test]
fn the_page_embeds_the_frame_without_exposing_script_closers() {
    let frame = json!({
        "status": "UNKNOWN", "topology": components(2, &[]),
        "collection_gaps": [{"kind": "collection_gap", "reason": "</script><script>alert(1)</script>"}]
    });
    let page = document(&frame);
    assert!(page.contains("id=\"run-frame-data\""));
    assert!(!page.contains("</script><script>alert(1)</script>"));
}

#[test]
fn the_embedded_frame_keeps_unusual_gap_fields_and_large_integers() {
    let gap = json!({"reason": "</script>", "extra": 18446744073709551615_u64});
    let frame = json!({"large": 18446744073709551615_u64, "collection_gaps": [gap.clone()]});
    let packed = super::super::pack_frame(frame.as_object().unwrap()).unwrap();
    assert!(packed["frame_json"]
        .as_str()
        .unwrap()
        .contains("18446744073709551615"));
    let restored: Value = serde_json::from_str(packed["gaps"][0]["raw"].as_str().unwrap()).unwrap();
    assert_eq!(restored, gap);
}

// The Explorer names the result of the run in the words of its verdict (AD-764), not the 4.0.1
// "observation", which only said that a list of the topology was cut by its budget.
#[test]
fn the_explorer_names_the_result_of_the_run_and_no_observation() {
    let premised = json!({"status": "PASS", "topology": components(2, &[]),
        "rules": {"R": ["unused_public", "PASS"]},
        "premises": {"R": [{"kind": "external_user", "subject": "m.f"}]},
        "assuming": "1 stated external user"});
    let plain = json!({"status": "PASS", "topology": components(2, &[])});
    let open = json!({"status": "UNKNOWN", "topology": components(2, &[])});
    for (frame, result) in [
        (premised, "PASS assuming 1 stated external user"),
        (plain, "PASS"),
        (open, "UNKNOWN"),
    ] {
        let data = payload(&document(&frame));
        assert_eq!(data["atlas"]["result"], result);
        assert!(data["atlas"].get("observation_complete").is_none());
    }
}

// The page budget (#880): a declared boundary permission is one row for each `requires`, with
// its rationale once in the reference table, and a module row holds no field that is the same for
// each module. `report-scene.js` restores the full rows; the page shows the same.
#[test]
fn the_payload_writes_each_repeated_value_once() {
    let mut topology = components(2, &[(0, 1)]);
    topology["requires"] = json!([{"source": "COMP-0", "target": "COMP-1", "imports": 2,
        "rationale": "Read the typed rows.", "through": ["m1.a", "m1.b"]},
        {"source": "COMP-1", "target": "COMP-0", "imports": 0, "rationale": "No port.", "through": []}]);
    let data = payload(&document(&json!({"status": "PASS", "topology": topology})));
    let rows = data["boundary_permissions"]["requires"].as_array().unwrap();
    assert_eq!(rows.len(), 1);
    let refs = &data["atlas"]["reference_ids"];
    let rationale = rows[0][2].as_u64().unwrap() as usize;
    assert_eq!(
        (&rows[0][0], &rows[0][1], &refs[rationale], &rows[0][3]),
        (
            &json!("COMP-0"),
            &json!("COMP-1"),
            &json!("Read the typed rows."),
            &json!(["m1.a", "m1.b"])
        )
    );
    assert!(data["boundary_permissions"].get("declared").is_none());
    let module = &data["atlas"]["modules"][0];
    for repeated in ["name", "rank", "evidence_ids", "symbol_coverage", "symbols"] {
        assert!(module.get(repeated).is_none(), "{repeated}");
    }
    let edge = &data["atlas"]["components"][0]["requires"][0];
    assert!(edge.get("id").is_none() && edge.get("decided_by").is_none());
}
