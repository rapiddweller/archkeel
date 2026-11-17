// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The run-level floor of the Explorer (AD-730): a box, a cell or an edge shows PASS only when the
// run decides every rule. A run that is UNKNOWN for a reason of the whole run (an UNKNOWN rule
// without a gap, a refused contract, an open scope) or that states no status shows no PASS.

use super::*;

/// Every status that the Explorer data shows for a component, a cell or an edge of a level.
fn shown(data: &Value) -> Vec<String> {
    let atlas = &data["atlas"];
    let word = |v: &Value| v.as_str().unwrap().to_owned();
    let nodes = atlas["components"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| word(&c["status"]));
    let cells = atlas["cells"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| word(&c[3]));
    let edges = atlas["levels"].as_array().unwrap().iter().flat_map(|l| {
        l["edges"]
            .as_array()
            .unwrap()
            .iter()
            .map(|e| word(&e["status"]))
    });
    nodes.chain(cells).chain(edges).collect()
}

/// A frame of three components and two imports between them, with this status and these rules.
fn frame_of(status: Option<&str>, rules: Value) -> Value {
    let mut frame = json!({"rules": rules, "topology": components(3, &[(0, 1), (1, 2)]),
        "scope": "incomplete scope: the collector does not state every public symbol"});
    if let Some(status) = status {
        frame["status"] = json!(status);
    }
    frame
}

// #1451: the rule is UNKNOWN for the whole run, and no gap or held pair names a module. Before
// AD-730 every box and every cell showed PASS: a false PASS on the page.
#[test]
fn a_run_that_is_unknown_for_a_reason_of_the_whole_run_shows_no_pass() {
    let unknown_rule =
        json!({"R-USED": ["unused_public", "UNKNOWN"], "R-DEP": ["forbidden_dependency", "PASS"]});
    let cases = [
        (
            "unknown rule",
            frame_of(Some("UNKNOWN"), unknown_rule.clone()),
        ),
        ("open scope", frame_of(Some("UNKNOWN"), json!({}))),
        ("fail beside an unknown rule", {
            let mut rules = unknown_rule.clone();
            rules["R-CYCLE"] = json!(["no_component_cycles", "FAIL"]);
            frame_of(Some("FAIL"), rules)
        }),
        ("no status", frame_of(None, unknown_rule)),
    ];
    for (name, frame) in cases {
        let data = payload(&document(&frame));
        let found = shown(&data);
        assert!(found.len() > 3, "{name}: {found:?}");
        assert!(!found.iter().any(|s| s == "PASS"), "{name}: {found:?}");
        // The box tells why: it has no gap of its own, the run is open.
        let reason = data["atlas"]["components"][0]["reason_ref"]
            .as_u64()
            .unwrap() as usize;
        let text = data["atlas"]["reference_ids"][reason].as_str().unwrap();
        assert!(text.contains("the run is not decided"), "{name}: {text}");
    }
}

// AD-730: the floor holds only an open run. A decided run keeps PASS where nothing fails.
#[test]
fn a_decided_run_keeps_pass_where_no_rule_fails() {
    let pass = frame_of(
        Some("PASS"),
        json!({"R-DEP": ["forbidden_dependency", "PASS"]}),
    );
    assert!(shown(&payload(&document(&pass)))
        .iter()
        .all(|s| s == "PASS"));
    // A FAIL run that proves every rule decided (complete scope, no rule without a row): the box
    // without a violated place stays PASS.
    assert_eq!(boxes(&decided_fail()), ["FAIL", "PASS"]);
}

/// The status of each component box of the rendered page.
fn boxes(frame: &Value) -> Vec<String> {
    payload(&document(frame))["atlas"]["components"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| c["status"].as_str().unwrap().to_owned())
        .collect()
}

/// A FAIL frame of one violated import that proves each rule of the contract decided, as the
/// core writes it: the scope is `complete` and `unsupported.rules` is an empty list.
fn decided_fail() -> Value {
    let mut frame = dependency_frame(1);
    frame["scope"] = json!("complete");
    frame["unsupported"] = json!({"rules": {}, "sections": {}, "report": null});
    frame
}

// #1507: a FAIL run beside an unported rule. The unported rule has no row (it sits in
// `unsupported.rules`) and may break inside any box, so no box shows PASS. The same holds for an
// open scope, a frame without the list, one reason for the whole contract, and a rule that
// `explain` names without a row.
#[test]
fn a_fail_beside_a_rule_without_a_row_shows_no_pass_box() {
    let unported = json!({"PROTOCOLS-IN-SERVICE":
        "unsupported: rule kind SymbolPlacement: the slice of its family ports it"});
    let mut cases = Vec::new();
    let mut frame = decided_fail();
    frame["unsupported"]["rules"] = unported;
    cases.push(("unported rule", frame));
    let mut frame = decided_fail();
    frame["scope"] = json!("incomplete scope: the profile cannot decide a budget");
    cases.push(("open scope", frame));
    let mut frame = decided_fail();
    frame.as_object_mut().unwrap().remove("unsupported");
    cases.push(("no list", frame));
    let mut frame = decided_fail();
    frame["unsupported"]["rules"] = json!("contract <refused>");
    cases.push(("whole contract", frame));
    let mut frame = decided_fail();
    frame["explain"]["rules"]["PLACE"] = json!({"kind": "symbol_placement"});
    cases.push(("unshaped rule", frame));
    for (name, frame) in cases {
        assert_eq!(boxes(&frame), ["FAIL", "UNKNOWN"], "{name}");
        let page = document(&frame);
        assert!(page.contains("<h1>Verdict: FAIL</h1>"), "{name}");
    }
    // The title does not say "0 unknown" alone: the unported rule is not decided either.
    let mut frame = decided_fail();
    frame["unsupported"]["rules"] = json!({"PLACE": "unsupported: rule kind"});
    let page = document(&frame);
    assert!(
        page.contains("1 rule violated in 1 place, 0 unknown, 1 gap with no rule"),
        "{page}"
    );
    assert!(document(&decided_fail()).contains("1 rule violated in 1 place, 0 unknown<"));
}

// AD-730: a frame without a status still names its cause and a next step.
#[test]
fn a_frame_without_a_status_names_its_cause_and_a_next_step() {
    let page = document(&json!({"rules": {}, "scope": "missing input: no valid collector reply"}));
    assert!(page.contains("<h1>Verdict: unavailable</h1>"));
    assert!(page.contains("keeps the run open: missing input: no valid collector reply"));
    let bare = document(&json!({}));
    assert!(bare.contains("The frame states no status"), "{bare}");
    assert!(bare.contains("archkeel validate --verbose"));
}
