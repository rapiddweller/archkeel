// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the report page (AD-496). Frames are built by hand, so each block has a test of its own.

use serde_json::{json, Value};

use super::markup::escape;
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
    assert!(page.contains("2 members are in this cycle. Shortest closed path shown: 2 steps."));
    assert!(page.contains("Step 2 imports <span title=\"m.a\">m.a</span>, where step 1 starts."));
    assert!(page.contains("src/m.rs:9") && page.contains("and 2 more"));
    let cut = document(&cycle_frame(1, 3));
    assert!(cut.contains("The frame lists 1 of 3 cycles of <span class=\"rp-code\">CY</span>."));
}

// Review of #1163, finding S1: the direction of a rule comes from the frame and is escaped.
#[test]
fn a_forged_direction_is_escaped() {
    let mut frame = dependency_frame(1);
    frame["explain"]["rules"]["R"]["direction"] = json!("<i onclick=\"x\">&'");
    let page = document(&frame);
    assert!(page.contains("&lt;i onclick=&quot;x&quot;&gt;&amp;&#39;: a"));
    assert!(!page.contains("<i onclick"));
}

// S2: a run that is UNKNOWN without an UNKNOWN rule names its cause, not "0 unknown rules".
#[test]
fn an_open_run_without_an_unknown_rule_names_its_cause() {
    let frame = json!({"status": "UNKNOWN", "rules": {}, "scope": "missing input: no valid collector reply",
        "unsupported": {"rules": "contract <refused>"}});
    let page = document(&frame);
    assert!(!page.contains("0 unknown rules"));
    assert!(page.contains("Remove the cause that keeps the run open: contract &lt;refused&gt;"));
    let scope = json!({"status": "UNKNOWN", "rules": {}, "scope": "incomplete scope: 3 gaps"});
    assert!(document(&scope).contains("keeps the run open: incomplete scope: 3 gaps"));
}

const HOSTILE: &str = "<script>\"&'";

fn hostile_frame(components: usize) -> Value {
    let mut frame = dependency_frame(1);
    let list: Vec<Value> = (0..components)
        .map(|i| json!({"id": format!("COMP-{i}"), "name": format!("{HOSTILE}{i}")}))
        .collect();
    frame["topology"]["components"] = json!(list);
    frame["topology"]["total"]["components"] = json!(components);
    frame["explain"]["cycles"] = json!({"CY": {"total": 1, "items": [{"index": 1,
        "members": [HOSTILE], "steps_total": 2, "truncated": false, "path": [
        {"from": HOSTILE, "to": "m.b", "from_component": "COMP-0", "to_component": "COMP-1",
            "evidence": [], "evidence_total": 0},
        {"from": "m.b", "to": HOSTILE, "from_component": "COMP-1", "to_component": "COMP-0",
            "evidence": [], "evidence_total": 0}]}]}});
    frame["rules"]["CY"] = json!(["no_component_cycles", "FAIL"]);
    frame["details"]["CY"] = json!([
        {"source": "m.a", "target": "m.b", "cause": "forbidden dependency", "evidence": []},
        {"source": HOSTILE, "target": "m.b", "cause": "dependency cycle", "evidence": []}]);
    frame
}

// S4: a hostile component or module name reaches no markup, in the map and in the matrix.
#[test]
fn hostile_names_are_escaped_in_the_map_the_matrix_and_the_cycle_rows() {
    for components in [2, 13] {
        let page = document(&hostile_frame(components));
        let safe = escape(HOSTILE);
        assert!(page.contains(&safe), "{components} components");
        assert!(!page.contains("<script>\""), "{components} components");
        assert_eq!(page.matches("<script>").count(), 1);
        assert!(page.contains("class=\"rp-mx\""));
        assert_eq!(
            page.contains("class=\"ak-diagram rp-map\""),
            components <= 12
        );
        assert!(page.contains(&format!("<title>{safe}0")) || components > 12);
        assert!(page.contains(&format!("title=\"{safe}0")) || components <= 12);
        let cycle = page.split("Cycle of 1 member").nth(1).unwrap();
        assert!(cycle.contains(&format!("<span title=\"{safe}\">{safe}</span>")));
    }
}

// The pairing of a cycle with its row follows the `index` of the frame: a rule that has an import
// row before its cycle row keeps both.
#[test]
fn a_rule_with_an_import_row_and_a_cycle_row_pairs_each_with_its_own_row() {
    let page = document(&hostile_frame(2));
    assert_eq!(page.matches("class=\"rp-dos\"").count(), 3);
    assert!(page.contains("Cycle of 1 member"));
    assert!(page.contains("m.a imports m.b"));
    // The cycle row is not shown a second time as an import place.
    assert!(!page.contains(&format!("{} imports m.b", escape(HOSTILE))));
}

/// The boxes `(x, y, width, height)` and the paths of the edges of the map.
fn drawing(page: &str) -> (Vec<[f64; 4]>, Vec<String>) {
    let number = |chunk: &str, key: &str| -> f64 {
        let at = chunk.split(&format!("{key}=\"")).nth(1).unwrap();
        at.split('"').next().unwrap().parse().unwrap()
    };
    let boxes = page
        .split("<rect class=\"ak-node__box\"")
        .skip(1)
        .map(|chunk| ["x", "y", "width", "height"].map(|key| number(chunk, key)))
        .collect();
    let paths = page
        .split("<path class=\"ak-edge")
        .skip(1)
        .map(|chunk| {
            chunk
                .split("d=\"")
                .nth(1)
                .unwrap()
                .split('"')
                .next()
                .unwrap()
                .to_owned()
        })
        .collect();
    (boxes, paths)
}

/// The points of a path of the map in order: a curve counts with its two control points.
fn points(path: &str) -> Vec<(f64, f64)> {
    let mut found: Vec<(f64, f64)> = Vec::new();
    let mut tokens: Vec<String> = Vec::new();
    let mut word = String::new();
    for c in path.chars() {
        if c.is_ascii_alphabetic() {
            if !word.is_empty() {
                tokens.push(std::mem::take(&mut word));
            }
            tokens.push(c.to_string());
        } else if c == ' ' {
            if !word.is_empty() {
                tokens.push(std::mem::take(&mut word));
            }
        } else {
            word.push(c);
        }
    }
    tokens.push(word);
    let (mut x, mut y) = (0.0, 0.0);
    let mut at = 0;
    while at < tokens.len() {
        let value = |i: usize| tokens[i].parse::<f64>().unwrap();
        match tokens[at].as_str() {
            "M" => (x, y, at) = (value(at + 1), value(at + 2), at + 3),
            "H" => (x, at) = (value(at + 1), at + 2),
            "V" => (y, at) = (value(at + 1), at + 2),
            "C" => {
                found.push((value(at + 1), value(at + 2)));
                found.push((value(at + 3), value(at + 4)));
                (x, y, at) = (value(at + 5), value(at + 6), at + 7);
            }
            other => assert!(other.is_empty(), "unknown path command {other}"),
        }
        found.push((x, y));
    }
    found
}

// S5: no edge segment crosses the inside of a box. A box is the end of an edge only at its border.
#[test]
fn no_edge_of_the_map_crosses_a_box() {
    let edges = [
        (0, 1),
        (1, 2),
        (0, 2),
        (0, 3),
        (3, 1),
        (2, 0),
        (4, 5),
        (5, 4),
        (3, 3),
        (0, 5),
        (1, 4),
    ];
    let page = document(&json!({"status": "PASS", "topology": components(6, &edges)}));
    let (boxes, paths) = drawing(&page);
    assert_eq!(boxes.len(), 6);
    assert_eq!(
        paths.len(),
        10,
        "the edge of a component to itself is not drawn"
    );
    for path in &paths {
        let line = points(path);
        for pair in line.windows(2) {
            let (low_x, high_x) = (pair[0].0.min(pair[1].0), pair[0].0.max(pair[1].0));
            let (low_y, high_y) = (pair[0].1.min(pair[1].1), pair[0].1.max(pair[1].1));
            for [x, y, w, h] in &boxes {
                let inside = low_x < x + w - 1.0
                    && high_x > x + 1.0
                    && low_y < y + h - 1.0
                    && high_y > y + 1.0;
                assert!(!inside, "{path} crosses the box at {x},{y}");
            }
        }
    }
}

// S6: the number of dependencies is the number that the map draws.
#[test]
fn the_count_of_dependencies_leaves_out_the_edges_to_the_component_itself() {
    let page =
        document(&json!({"status": "PASS", "topology": components(3, &[(0, 1), (1, 1), (2, 2)])}));
    assert!(page.contains("1 dependency between components"));
    assert!(page.contains("Component map: 3 components, 1 dependency."));
}

// B1: equal places are shown once with their number, and the page has no link without a target.
#[test]
fn an_equal_place_is_shown_once_with_its_number_and_no_link_lacks_a_target() {
    let mut frame = cycle_frame(1, 1);
    frame["locations"]["F"] = json!({"path": "src/m.rs", "line": 9});
    frame["explain"]["cycles"]["CY"]["items"][0]["path"][0]["evidence"] = json!(["E", "F", "E"]);
    frame["explain"]["cycles"]["CY"]["items"][0]["path"][0]["evidence_total"] = json!(3);
    let page = document(&frame);
    assert!(page.contains("src/m.rs:9</span> &#215;3"));
    assert!(!page.contains("src/m.rs:9</span>, <span class=\"rp-code\">src/m.rs:9"));
    let dead = dependency_frame(1);
    let page = document(&dead);
    assert!(
        !page.contains("href=\"#c-"),
        "a component has no block to link to"
    );
    for link in page.split("href=\"#").skip(1) {
        let id = link.split('"').next().unwrap();
        assert!(page.contains(&format!("id=\"{id}\"")), "{id} has no target");
    }
}

// B1: the causes show under the verdict as one line, the three largest, with the rule counts.
#[test]
fn the_verdict_names_the_largest_causes_in_one_line() {
    let frame = json!({"status": "UNKNOWN",
        "rules": {"A": ["k", "UNKNOWN"], "B": ["k", "UNKNOWN"], "C": ["k", "UNKNOWN"], "D": ["k", "UNKNOWN"]},
        "explained": {"C": "pair text", "D": "other <b>"},
        "explain": {"holds": {"rules": {
            "A": {"kind": "coverage_gaps", "total": 5}, "B": {"kind": "coverage_gaps", "total": 5},
            "C": {"kind": "pair_gaps", "total": 7}}}}});
    let page = document(&frame);
    assert!(page.contains(
        "Unknown because of 3 causes. 2 rules: 5 coverage gaps in the scan; \
1 rule: other &lt;b&gt;; 1 rule: 7 gaps between two modules."
    ));
    assert!(page.contains("4 unknown rules: 3 causes hold them."));
}
