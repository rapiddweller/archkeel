// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the report page (AD-496). Frames are built by hand, so each block has a test of its own.

use serde_json::{json, Value};

use super::*;

fn document(frame: &Value) -> String {
    let rendered = render(frame.as_object().unwrap()).unwrap();
    rendered["document"].as_str().unwrap().to_owned()
}

#[test]
fn all_text_is_escaped_without_truncation() {
    let plant = format!("<script>\"'&\u{fffd}{}", "x".repeat(100_000));
    let safe = escape(&plant);
    assert!(safe.starts_with("&lt;script&gt;&quot;&#39;&amp;\u{fffd}"));
    assert!(safe.ends_with(&"x".repeat(100_000)));
    let frame = json!({"status": "UNKNOWN", "rules": {plant.clone(): [plant.clone(), "UNKNOWN"]},
        "explained": {plant.clone(): plant.clone()}, "locations": {"e": {"path": plant.clone()}},
        "unsupported": {"rules": plant.clone()}, "self_test": {"collect": {"refused": plant.clone()}}});
    let page = document(&frame);
    assert!(page.contains(&safe));
    // The page has its one theme script; the planted text adds none.
    assert_eq!(page.matches("<script>").count(), 1);
    assert!(page.contains("<h1>Verdict: UNKNOWN</h1>"));
}

#[test]
fn the_policy_admits_the_theme_script_by_its_hash_and_nothing_else() {
    let page = document(&json!({"status": "PASS"}));
    let policy = page
        .split("Content-Security-Policy\" content=\"")
        .nth(1)
        .and_then(|rest| rest.split('"').next())
        .unwrap();
    assert!(policy.contains(&format!("script-src 'sha256-{}'", shell::THEME_HASH)));
    assert!(policy.starts_with("default-src 'none'"));
    assert!(!policy.contains("unsafe-eval") && !policy.contains("http"));
    let script = page
        .split("<script>")
        .nth(1)
        .unwrap()
        .split("</script>")
        .next()
        .unwrap();
    assert_eq!(script, shell::THEME_SCRIPT);
    assert!(!page.contains("<link") && !page.contains("@import") && !page.contains("src="));
}

fn components(count: usize, edges: &[(usize, usize)]) -> Value {
    let list: Vec<Value> = (0..count)
        .map(|i| json!({"id": format!("COMP-{i}"), "name": format!("c{i}")}))
        .collect();
    let links: Vec<Value> = edges
        .iter()
        .map(|(a, b)| {
            json!({"source": format!("COMP-{a}"), "target": format!("COMP-{b}"),
                "resolution": "resolved", "count": 2})
        })
        .collect();
    json!({"components": list, "modules": [], "component_edges": links,
        "total": {"components": count, "modules": 0, "edges": 0, "component_edges": links.len()}})
}

#[test]
fn a_small_run_has_the_map_and_a_large_run_has_the_matrix_only() {
    let small = document(&json!({"status": "PASS", "topology": components(3, &[(0, 1), (1, 2)])}));
    assert!(small.contains("class=\"ak-diagram rp-map\"") && small.contains("class=\"rp-mx\""));
    let many = document(&json!({"status": "PASS", "topology": components(13, &[(0, 1)])}));
    assert!(!many.contains("class=\"ak-diagram rp-map\"") && many.contains("class=\"rp-mx\""));
    let dense: Vec<(usize, usize)> = (0..7).flat_map(|a| (0..7).map(move |b| (a, b))).collect();
    let thick = document(&json!({"status": "PASS", "topology": components(7, &dense)}));
    assert!(
        !thick.contains("class=\"ak-diagram rp-map\""),
        "more than 30 dependencies draw the matrix"
    );
    let none = document(&json!({"status": "PASS"}));
    assert!(!none.contains("id=\"arch\""));
}

fn dependency_frame(rows: usize) -> Value {
    let details: Vec<Value> = (0..rows)
        .map(|i| {
            json!({"source": format!("app.a{i}"), "target": "app.b", "cause": "forbidden dependency",
                "evidence": [format!("E{i}")]})
        })
        .collect();
    let locations: Value = (0..rows)
        .map(|i| {
            (
                format!("E{i}"),
                json!({"path": format!("src/a{i}.rs"), "line": i + 1}),
            )
        })
        .collect::<serde_json::Map<_, _>>()
        .into();
    json!({"status": "FAIL", "rules": {"R": ["forbidden_dependency", "FAIL"]},
        "details": {"R": details}, "locations": locations,
        "explain": {"rules": {"R": {"kind": "forbidden_dependency", "direction": "forbids",
            "source": ["COMP-0"], "target": ["COMP-1"]}}, "cycles": {}},
        "topology": {"components": [{"id": "COMP-0", "name": "a"}, {"id": "COMP-1", "name": "b"}],
            "modules": [{"name": "app.a0", "path": "src/a0.rs", "component": "COMP-0"},
                {"name": "app.b", "path": "src/b.rs", "component": "COMP-1"}],
            "component_edges": [{"source": "COMP-0", "target": "COMP-1", "resolution": "resolved", "count": 1}],
            "total": {"components": 2, "modules": 2, "component_edges": 1}}})
}

#[test]
fn a_violated_import_is_one_block_with_its_path_its_line_and_the_sides_of_its_rule() {
    let page = document(&dependency_frame(1));
    let block = page
        .split("id=\"x1\"")
        .nth(1)
        .unwrap()
        .split("</article>")
        .next()
        .unwrap();
    assert!(block.contains("app.a0 imports app.b"));
    assert!(block.contains("<span class=\"tag\">component</span>"));
    assert!(block.contains("src/a0.rs") && block.contains("src/b.rs"));
    assert!(block.contains("IMPORTS") && block.contains("line 1"));
    assert!(block.contains("Violates <b class=\"rp-code\">R</b>"));
    assert!(block.contains("forbids: a to b"));
    // The picture marks the place and links to its block.
    assert!(page.contains("href=\"#x1\"") && page.contains("ak-edge--violation"));
    assert_eq!(page.matches("<h1>Verdict: FAIL</h1>").count(), 1);
}

#[test]
fn rules_that_fail_at_one_import_share_one_block() {
    let mut frame = dependency_frame(1);
    frame["rules"]["Q"] = json!(["complete_requires", "FAIL"]);
    let row = frame["details"]["R"][0].clone();
    frame["details"]["Q"] = json!([row]);
    let page = document(&frame);
    assert_eq!(page.matches("class=\"rp-dos\"").count(), 1);
    assert!(page.contains("Violates <b class=\"rp-code\">Q</b>"));
    assert!(page.contains("Violates <b class=\"rp-code\">R</b>"));
}

#[test]
fn a_cut_of_the_places_states_both_numbers() {
    let page = document(&dependency_frame(120));
    assert_eq!(page.matches("class=\"rp-dos\"").count(), places::MAX_PLACES);
    assert!(page.contains("120 places in the code"));
    assert!(page.contains("The page shows 100 of 120 places."));
}

fn cycle_frame(listed: usize, total: usize) -> Value {
    let step = |from: &str, to: &str| {
        json!({"from": from, "to": to, "from_component": "COMP-0", "to_component": "COMP-0",
            "imports": 1, "evidence": ["E"], "evidence_total": 3})
    };
    let items: Vec<Value> = (0..listed)
        .map(|i| {
            json!({"id": format!("V{i}"), "index": i, "members": ["m.a", "m.b"],
                "path": [step("m.a", "m.b"), step("m.b", "m.a")], "steps_total": 2, "truncated": false})
        })
        .collect();
    let rows: Vec<Value> = (0..total)
        .map(|i| json!({"source": format!("m.a -> m.b{i}"), "target": "m.a", "cause": "dependency cycle", "evidence": ["E"]}))
        .collect();
    json!({"status": "FAIL", "rules": {"CY": ["no_component_cycles", "FAIL"]},
        "details": {"CY": rows}, "locations": {"E": {"path": "src/m.rs", "line": 9}},
        "explain": {"rules": {}, "cycles": {"CY": {"total": total, "items": items}}}})
}

#[test]
fn a_cycle_is_one_block_with_its_closed_path_and_a_cut_list_says_so() {
    let page = document(&cycle_frame(2, 2));
    assert_eq!(page.matches("class=\"rp-dos\"").count(), 2);
    assert!(page.contains("Cycle of 2 members"));
    assert!(page.contains("Step 2 returns to step 1."));
    assert!(page.contains("src/m.rs:9") && page.contains("and 2 more"));
    let cut = document(&cycle_frame(1, 3));
    assert!(cut.contains("The frame lists 1 of 3 cycles of <span class=\"rp-code\">CY</span>."));
}
