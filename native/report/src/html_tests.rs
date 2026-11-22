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
fn the_light_palette_matches_the_design_tokens() {
    let tokens = include_str!("../assets/tokens.css");
    let palette = tokens
        .split_once("[data-theme=\"light\"]{")
        .and_then(|(_, rest)| rest.split_once('}'))
        .map(|(body, _)| body)
        .expect("the light token block");
    let page = document(&json!({"status": "PASS"}));
    assert!(page.contains(&format!("{{{palette}color-scheme:light}}")));
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
    let modules: Vec<Value> = (0..count)
        .map(|i| json!({"name": format!("m{i}"), "path": format!("src/m{i}.rs"), "component": format!("COMP-{i}")}))
        .collect();
    let imports: Vec<Value> = edges
        .iter()
        .map(|(a, b)| json!({"source": format!("m{a}"), "target": format!("m{b}"), "resolution": "resolved", "count": 2}))
        .collect();
    json!({"components": list, "modules": modules, "edges": imports, "component_edges": [],
        "total": {"components": count, "modules": count, "edges": imports.len(), "component_edges": 0}})
}

/// The data of the Explorer that a page holds.
fn payload(page: &str) -> Value {
    let (_, rest) = page
        .split_once("<script id=\"flow-data\" type=\"application/json\">")
        .unwrap();
    serde_json::from_str(rest.split_once("</script>").unwrap().0).unwrap()
}

/// The observed edges between the top components, as (source, target, import sites).
fn top_edges(data: &Value) -> Vec<(String, String, u64)> {
    let root = data["atlas"]["levels"]
        .as_array()
        .unwrap()
        .iter()
        .find(|level| level["parent_id"].is_null())
        .unwrap();
    root["edges"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| {
            let text = |key: &str| e[key].as_str().unwrap().to_owned();
            (
                text("source_id"),
                text("target_id"),
                e["import_sites"].as_u64().unwrap(),
            )
        })
        .collect()
}

// AD-606: a run with a topology has the Explorer and its data; a run without one has no section.
#[test]
fn a_run_with_a_topology_has_the_explorer_and_its_data() {
    for size in [3, 13] {
        let page =
            document(&json!({"status": "PASS", "topology": components(size, &[(0, 1), (1, 2)])}));
        let data = payload(&page);
        let all = data["atlas"]["components"].as_array().unwrap();
        let real = all
            .iter()
            .filter(|c| !c["id"].as_str().unwrap().starts_with("GROUP:"))
            .count();
        assert_eq!(real, size);
        // A level of at most six boxes draws each edge. A larger set is split into groups: an
        // import between two groups is one edge between them, and one inside a group is drawn
        // when the group is opened. Each import of the two chains is on some level (AD-630).
        let edges = top_edges(&data);
        let drawn: usize = data["atlas"]["levels"]
            .as_array()
            .unwrap()
            .iter()
            .map(|level| level["edges"].as_array().unwrap().len())
            .sum();
        assert!(if size <= 12 {
            edges.len() == 2
        } else {
            drawn >= 2
        });
        assert!(page.contains("id=\"flow\" class=\"flow\" data-atlas=\"true\""));
        assert_eq!(
            page.matches("<script").count(),
            12,
            "the theme, the data and ten scripts"
        );
    }
    let none = document(&json!({"status": "PASS"}));
    assert!(!none.contains("id=\"arch\"") && !none.contains("flow-data"));
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

// AD-668: two sites of one import that break one rule give one line of the rule and both places.
#[test]
fn a_rule_that_two_sites_of_one_import_break_is_listed_once() {
    let mut frame = dependency_frame(2);
    frame["details"]["R"][1]["source"] = json!("app.a0");
    let page = document(&frame);
    assert_eq!(
        page.matches("Violates <b class=\"rp-code\">R</b>").count(),
        1
    );
    assert!(page.contains("src/a0.rs:1") && page.contains("src/a1.rs:2"));
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
    assert!(page.contains("contract &lt;refused&gt;"));
    let scope = json!({"status": "UNKNOWN", "rules": {}, "scope": "incomplete scope: 3 gaps"});
    assert!(document(&scope).contains("incomplete scope: 3 gaps"));
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

#[test]
// S4: a hostile component or module name reaches no markup: the data block writes `<` as
// `\u003c`, and the Explorer reads the name as text.
fn hostile_names_are_escaped_in_the_data_and_the_cycle_rows() {
    for components in [2, 13] {
        let page = document(&hostile_frame(components));
        let safe = escape(HOSTILE);
        assert!(page.contains(&safe), "{components} components");
        assert!(!page.contains("<script>\""), "{components} components");
        let data = payload(&page);
        assert_eq!(
            data["atlas"]["components"][0]["label"],
            format!("{HOSTILE}0")
        );
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

// S6: an import inside one component is no edge between components.
#[test]
fn the_edges_leave_out_the_imports_inside_one_component() {
    let page =
        document(&json!({"status": "PASS", "topology": components(3, &[(0, 1), (1, 1), (2, 2)])}));
    let edges = top_edges(&payload(&page));
    assert_eq!(edges, [("COMP-0".to_owned(), "COMP-1".to_owned(), 2)]);
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
    for (index, part) in page.split("<script").enumerate() {
        let html = if index == 0 {
            part
        } else {
            part.split_once("</script>").unwrap().1
        };
        for link in html.split("href=\"#").skip(1) {
            let id = link.split('"').next().unwrap();
            assert!(page.contains(&format!("id=\"{id}\"")), "{id} has no target");
        }
    }
}

// Recorded evidence stays in the folded Unknown section, not a generic task list.
#[test]
fn the_verdict_does_not_make_generic_gap_tasks() {
    let frame = json!({"status": "UNKNOWN",
        "rules": {"A": ["k", "UNKNOWN"], "B": ["k", "UNKNOWN"], "C": ["k", "UNKNOWN"], "D": ["k", "UNKNOWN"]},
        "explained": {"C": "pair text", "D": "other <b>"},
        "explain": {"holds": {"rules": {
            "A": {"kind": "coverage_gaps", "total": 5}, "B": {"kind": "coverage_gaps", "total": 5},
            "C": {"kind": "pair_gaps", "total": 7}}}}});
    let page = document(&frame);
    let head = page.split("id=\"unknown\"").next().unwrap();
    assert!(
        !head.contains("keep the run open"),
        "no count line of the causes"
    );
    assert!(!head.contains("class=\"body-sm ak-verdict__note\">2 unknown rules:"));
    assert!(!head.contains("Close the gaps behind"));
    assert!(page.contains("5 coverage gaps in the scan"));
    assert!(page.contains("7 module pairs with gaps"));
    assert!(page.contains("other &lt;b&gt;"));
}

// Red main (#1169): a page of an UNKNOWN run says why, with the code of the cause, and which rules
// are held: at most five ids by name, then the number of the others.
#[test]
fn a_named_gap_without_a_rule_row_shows_its_code_on_the_page() {
    let frame = json!({"status": "UNKNOWN", "rules": {"P": ["layer_order", "PASS"]},
        "unsupported": {"rules": {"hygiene:graph.count:a": "contract hygiene graph.count: expected <1>"}}});
    let page = document(&frame);
    assert!(page.contains("contract hygiene graph.count: expected &lt;1&gt;"));
    // The card counts the gap, so its numbers equal its list: no unknown rule, one gap.
    assert!(page.contains("Gaps with no rule</dt><dd class=\"ak-num h2\">1</dd>"));
    assert!(!page.contains("Remove the cause that keeps the run open"));
}

#[test]
fn every_unknown_run_names_a_cause_and_the_rules_it_holds_with_a_bound() {
    for held in [1usize, 5, 6, 40] {
        let rules: serde_json::Map<String, Value> = (0..held)
            .map(|i| (format!("R{i:02}"), json!(["k", "UNKNOWN"])))
            .collect();
        let explained: serde_json::Map<String, Value> = (0..held)
            .map(|i| (format!("R{i:02}"), json!("why")))
            .collect();
        let frame = json!({"status": "UNKNOWN", "rules": rules, "explained": explained});
        let page = document(&frame);
        let card = page
            .split("id=\"unknown\"")
            .nth(1)
            .unwrap()
            .split("</article>")
            .next()
            .unwrap();
        for index in 0..held {
            assert!(
                card.contains(&format!("R{index:02}")),
                "{held}: R{index:02}"
            );
        }
        if held > 5 {
            assert!(card.contains(&format!("+{} more", held - 5)), "{held}");
            let fold = card
                .split("<summary class=\"caption rp-at\">+")
                .nth(1)
                .unwrap();
            assert!(fold.contains("R05"), "the sixth id is in the fold");
        }
        assert!(card.contains("why"), "the cause is recorded");
    }
    let empty = document(&json!({"status": "UNKNOWN", "scope": "missing input"}));
    assert!(empty.contains("missing input"));
}

// A tower lays out its rows on the row tracks of its path (`subgrid`). A path without its row
// tracks puts each row in one track: the rows of a module and of its file are drawn over each
// other. Each path that a page writes has its tracks in the style.
#[test]
fn each_evidence_path_of_a_page_has_its_row_tracks() {
    let frame = json!({"status": "FAIL", "rules": {"A": ["complete_assignment", "FAIL"]},
        "details": {"A": [{"source": "app.loose", "target": null, "cause": "module has no unique owner",
            "evidence": ["E"]}]},
        "locations": {"E": {"path": "src/loose.rs", "line": 1}},
        "topology": {"components": [], "component_edges": [], "edges": [],
            "modules": [{"name": "app.loose", "path": "src/loose.rs", "component": null}],
            "total": {"components": 0, "modules": 1, "edges": 0, "component_edges": 0}}});
    let page = document(&frame);
    let style = include_str!("../assets/report.css");
    let paths: std::collections::BTreeSet<&str> = page
        .split("class=\"rp-path rp-path--")
        .skip(1)
        .filter_map(|rest| rest.split('"').next())
        .collect();
    assert!(
        paths.contains("2"),
        "a module without a component has two rows: {paths:?}"
    );
    for rows in paths {
        let rule = format!(".rp-path--{rows} {{ grid-template-rows: repeat({rows}, auto); }}");
        assert!(style.contains(&rule), "{rule} is missing");
    }
}

#[path = "html_system_tests.rs"]
mod system_tests;

#[path = "html_groups_tests.rs"]
mod groups_tests;

#[path = "html_next_tests.rs"]
mod next_tests;

#[path = "html_floor_tests.rs"]
mod floor_tests;

#[path = "html_premise_tests.rs"]
mod premise_tests;

#[path = "html_names_tests.rs"]
mod names_tests;
