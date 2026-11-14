// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the causes, the components, the rules and the footer of the report page (AD-498).

use serde_json::{json, Value};

use super::markup::escape;
use super::*;

const HOSTILE: &str = "<script>\"&'";

fn document(frame: &Value) -> String {
    let rendered = render(frame.as_object().unwrap()).unwrap();
    rendered["document"].as_str().unwrap().to_owned()
}

fn holds(kind: &str, total: usize, pairs: &[(&str, &str)]) -> Value {
    let list: Vec<Value> = pairs
        .iter()
        .map(|(s, t)| json!({"source": s, "target": t}))
        .collect();
    json!({"cause": "scope_incomplete", "kind": kind, "gaps": [], "pairs": list, "total": total,
        "truncated": false, "unnamed_imports": 0})
}

fn unknown_frame() -> Value {
    json!({"status": "UNKNOWN",
        "rules": {"A": ["complete_requires", "UNKNOWN"], "B": ["complete_requires", "UNKNOWN"],
            "C": ["forbidden_dependency", "UNKNOWN"], "D": ["root_layout", "UNKNOWN"]},
        "explained": {"A": "scope text", "B": "scope text", "C": "pair text", "D": "the core says <b>"},
        "collection_gaps": [
            {"kind": "source_resolution_gap", "subjects": ["m.a"], "reason": "dynamic import"},
            {"kind": "collection_gap", "subjects": ["m.b"], "reason": "macro"},
            {"kind": "source_resolution_gap", "subjects": ["m.zz"], "reason": "outside"}],
        "explain": {"holds": {"rules": {
            "A": holds("coverage_gaps", 3, &[]), "B": holds("coverage_gaps", 3, &[]),
            "C": holds("pair_gaps", 7, &[("m.a", "m.b"), ("m.b", "m.a")])}}},
        "topology": {"components": [{"id": "COMP-1", "name": "one"}, {"id": "COMP-2", "name": "two"}],
            "modules": [{"name": "m.a", "path": "src/a.rs", "component": "COMP-1"},
                {"name": "m.b", "path": "src/b.rs", "component": "COMP-2"}],
            "component_edges": [], "total": {"components": 2, "modules": 2, "component_edges": 0}}})
}

#[test]
fn the_unknown_rules_are_grouped_by_cause_and_the_largest_cause_comes_first() {
    let page = document(&unknown_frame());
    let section = page
        .split("id=\"unknown\"")
        .nth(1)
        .unwrap()
        .split("</section>")
        .next()
        .unwrap();
    assert!(section.contains("4 rules cannot be decided, from 3 causes"));
    assert_eq!(section.matches("class=\"rp-cause\"").count(), 3);
    let first = section.find("3 coverage gaps in the scan").unwrap();
    let second = section.find("7 gaps between two modules").unwrap();
    assert!(first < second, "the cause with two rules is first");
    let code = |id: &str| format!("<span class=\"rp-code\">{id}</span>");
    assert!(section.contains(&format!("Holds {}, {}", code("A"), code("B"))));
    // A rule is named once, in the card of its cause.
    assert_eq!(section.matches(&format!("Holds {}<", code("C"))).count(), 1);
    assert!(section.contains("Where: 3 of 3 components, 3 gaps in all"));
    assert!(section.contains("Where: 2 of 7 between two modules"));
    assert!(section.contains("the core says &lt;b&gt;"));
    assert!(section.contains("Close the gaps listed below"));
}

#[test]
fn a_run_that_is_open_without_an_unknown_rule_shows_its_cause() {
    let page = document(&json!({"status": "UNKNOWN", "scope": "missing <input>"}));
    assert!(page.contains("The run itself is open"));
    assert!(page.contains("missing &lt;input&gt;"));
}

fn component_frame(components: usize, modules_each: usize) -> Value {
    let list: Vec<Value> = (0..components)
        .map(|i| json!({"id": format!("COMP-{i}"), "name": format!("c{i}")}))
        .collect();
    let modules: Vec<Value> = (0..components)
        .flat_map(|c| {
            (0..modules_each).map(move |m| {
                json!({"name": format!("p{c}.m{m}"), "path": format!("src/p{c}/m{m}.rs"),
                    "component": format!("COMP-{c}")})
            })
        })
        .collect();
    let evidence: Vec<Value> = (1..=5)
        .map(|l| json!({"path": "src/p0/m0.rs", "line": l}))
        .collect();
    let edges = json!([{"source": "COMP-0", "target": "COMP-1", "resolution": "resolved",
        "count": 9, "evidence": evidence, "evidence_total": 9}]);
    json!({"status": "PASS", "topology": {"components": list, "modules": modules,
        "component_edges": edges, "total": {"components": components, "modules": components * modules_each,
            "component_edges": 1}}})
}

/// A gap in the first module of each named component: the components get a block.
fn gaps_in(frame: &mut Value, components: &[usize]) {
    let gaps: Vec<Value> = components
        .iter()
        .map(|c| json!({"kind": "collection_gap", "subjects": [format!("p{c}.m0")], "reason": "r"}))
        .collect();
    frame["collection_gaps"] = json!(gaps);
}

#[test]
fn a_component_opens_to_its_modules_its_files_and_its_imports_with_file_and_line() {
    let mut frame = component_frame(3, 2);
    gaps_in(&mut frame, &[0, 1]);
    let page = document(&frame);
    let panel = page
        .split("id=\"c-comp-0\"")
        .nth(1)
        .unwrap()
        .split("</details>")
        .next()
        .unwrap();
    assert!(panel.contains("2 modules"));
    assert!(panel.contains("p0.m0") && panel.contains("src/p0/m1.rs"));
    assert!(panel.contains("Modules: 2 of 2"));
    assert!(panel.contains("Imports of other components: 1 of 1"));
    assert!(panel.contains("src/p0/m0.rs:1") && panel.contains("and 6 more"));
    let target = page
        .split("id=\"c-comp-1\"")
        .nth(1)
        .unwrap()
        .split("</details>")
        .next()
        .unwrap();
    assert!(target.contains("Imports by other components: 1 of 1"));
    // The levels have a glyph and a word; the page shows no level below a file.
    assert!(panel.contains("<span class=\"tag\">") || panel.contains("rp-kind"));
    let components = page
        .split("id=\"components\"")
        .nth(1)
        .unwrap()
        .split("</section>")
        .next()
        .unwrap();
    assert!(!components.contains("function") && !components.contains("class member"));
}

#[test]
fn the_page_keeps_its_size_by_rule_and_states_the_cut() {
    let mut frame = component_frame(70, 30);
    let gapped: Vec<usize> = (0..31).collect();
    gaps_in(&mut frame, &gapped);
    frame["rules"] = json!({"R": ["forbidden_dependency", "FAIL"]});
    frame["status"] = json!("FAIL");
    frame["details"] = json!({"R": [{"source": "p69.m0", "target": "p0.m0",
        "cause": "forbidden dependency", "evidence": []}]});
    let page = document(&frame);
    assert!(page.contains("32 of 70 components have a violation or a gap. All tables for 24 components; one line for 8 components."));
    // A component with a violation is first, whatever its size; one without an exception has no block.
    let first = page.find("id=\"c-comp-69\"").unwrap();
    let last = page.find("id=\"c-comp-0\"").unwrap();
    assert!(first < last);
    assert!(!page.contains("id=\"c-comp-50\""));
    assert!(page.contains("Modules: 25 of 30"));
    assert_eq!(page.matches("class=\"rp-comp rp-comp--line\"").count(), 8);
    assert!(page.len() < 600_000);
}

#[test]
fn the_rules_that_hold_are_one_line_each_folded_by_kind() {
    let frame = json!({"status": "PASS", "rules": {
        "P1": ["complete_requires", "PASS"], "P2": ["complete_requires", "PASS"],
        "P3": ["layer_order", "PASS"], "D1": ["allowed_dependency", "DECLARATION"]}});
    let page = document(&frame);
    let section = page
        .split("id=\"rules\"")
        .nth(1)
        .unwrap()
        .split("</section>")
        .next()
        .unwrap();
    assert!(section.contains("3 rules hold, 1 rule declare a permission, 0 fail, 0 are unknown"));
    assert!(
        section.contains("complete requires &#183; 2 rules")
            && section.contains("layer order &#183; 1 rule")
    );
    assert_eq!(section.matches("<li class=\"body-sm\">").count(), 4);
    assert!(section.contains("allowed dependency &#183; 1 rule"));
    assert!(!section.contains("<details class=\"rp-fold rp-grp\" open"));
}

#[test]
fn the_old_parts_are_gone_and_the_footer_names_the_run_without_a_date() {
    let mut frame = component_frame(1, 1);
    frame["engine"] = json!("archkeel-core abcdef0123456789abcdef");
    frame["contract_digest"] = json!("0123456789abcdef0123");
    frame["self_test"] = json!({"collect": {"request": {"snapshot": {"git_head": "1234567890abcdef", "dirty": true}},
        "contract_files": {"c.json": "ff00"}}});
    let page = document(&frame);
    for old in [
        "Counts",
        "Gaps",
        "Unsupported",
        "Tool",
        "Request identity</h2>",
    ] {
        assert!(!page.contains(&format!("<h2>{old}")), "{old}");
    }
    let footer = page.split("<footer").nth(1).unwrap();
    assert!(footer.contains("commit 1234567890ab"));
    assert!(footer.contains("Core abcdef012345") && footer.contains("contract 0123456789ab"));
    assert!(footer.contains("<dt>c.json</dt><dd>ff00</dd>"));
    assert!(footer.contains("archkeel report --topology"));
}

#[test]
fn headings_follow_in_order_and_never_skip_a_level() {
    let mut frame = unknown_frame();
    frame["rules"]["P"] = json!(["layer_order", "PASS"]);
    let page = document(&frame);
    let mut last = 0;
    let mut found = 0;
    for part in page.split("<h").skip(1) {
        let Some(level) = part.chars().next().and_then(|c| c.to_digit(10)) else {
            continue;
        };
        if !(1..=6).contains(&level) || !part[1..].starts_with(['>', ' ']) {
            continue;
        }
        assert!(level <= last + 1, "h{level} after h{last}");
        last = level;
        found += 1;
    }
    assert!(found > 5);
}

#[test]
fn hostile_names_reach_no_markup_in_any_new_block() {
    let mut frame = unknown_frame();
    frame["explained"]["D"] = json!(HOSTILE);
    frame["rules"][HOSTILE] = json!(["layer_order", "PASS"]);
    frame["rules"]["Q"] = json!([HOSTILE, "DECLARATION"]);
    frame["topology"]["components"][0]["name"] = json!(HOSTILE);
    frame["topology"]["modules"][0] =
        json!({"name": HOSTILE, "path": HOSTILE, "component": "COMP-1"});
    frame["collection_gaps"][0] =
        json!({"kind": HOSTILE, "subjects": [HOSTILE], "reason": HOSTILE});
    frame["explain"]["holds"]["rules"]["C"] = holds("pair_gaps", 1, &[(HOSTILE, HOSTILE)]);
    frame["topology"]["component_edges"] = json!([{"source": "COMP-1", "target": "COMP-2",
        "resolution": "resolved", "count": 1, "evidence": [{"path": HOSTILE, "line": 3}], "evidence_total": 1}]);
    frame["engine"] = json!(format!("archkeel-core {HOSTILE}"));
    frame["self_test"] = json!({"collect": {"contract_files": {HOSTILE: HOSTILE}}});
    let page = document(&frame);
    assert!(
        !page.contains("<script>\""),
        "a hostile name is raw in the page"
    );
    assert_eq!(page.matches("<script>").count(), 1);
    for block in [
        "id=\"unknown\"",
        "id=\"components\"",
        "id=\"rules\"",
        "<footer",
    ] {
        let part = page.split(block).nth(1).unwrap();
        assert!(part.contains(&escape(HOSTILE)), "{block}");
    }
}

/// A frame of one component of two modules with one cycle between them.
fn one_cycle_frame() -> Value {
    let step = |from: &str, to: &str| {
        json!({"from": from, "to": to, "from_component": "COMP-0", "to_component": "COMP-0",
            "imports": 1, "evidence": ["E"], "evidence_total": 1})
    };
    let mut frame = component_frame(1, 2);
    frame["status"] = json!("FAIL");
    frame["rules"] = json!({"CY": ["no_component_cycles", "FAIL"]});
    frame["details"] = json!({"CY": [{"source": "p0.m0 -> p0.m1", "target": "p0.m0",
        "cause": "dependency cycle", "evidence": ["E"]}]});
    frame["locations"] = json!({"E": {"path": "src/p0/m0.rs", "line": 1}});
    frame["explain"] = json!({"rules": {}, "cycles": {"CY": {"total": 1, "items": [
        {"id": "V0", "index": 0, "members": ["p0.m0", "p0.m1"],
         "path": [step("p0.m0", "p0.m1"), step("p0.m1", "p0.m0")],
         "steps_total": 2, "truncated": false}]}}});
    frame
}

#[test]
fn a_cycle_over_two_modules_of_one_component_is_one_violation() {
    let page = document(&one_cycle_frame());
    let panel = page.split("id=\"c-comp-0\"").nth(1).unwrap();
    let summary = panel.split("</summary>").next().unwrap();
    assert!(
        summary.contains("1 violation") && !summary.contains("2 violations"),
        "{summary}"
    );
}

#[test]
fn the_next_step_counts_only_the_causes_that_hold_a_rule() {
    let frame = json!({"status": "UNKNOWN",
        "rules": {"R": ["k", "UNKNOWN"]}, "explained": {"R": "why"},
        "unsupported": {"rules": {"h:a": "named one", "h:b": "named two"}}});
    let page = document(&frame);
    assert!(
        page.contains("1 unknown rule: 1 cause holds them."),
        "{page}"
    );
}

#[test]
fn ids_beyond_five_are_in_a_fold_of_the_card_bounded_at_forty() {
    let rules: serde_json::Map<String, Value> = (0..50)
        .map(|i| (format!("R{i:02}"), json!(["k", "UNKNOWN"])))
        .collect();
    let explained: serde_json::Map<String, Value> = (0..50)
        .map(|i| (format!("R{i:02}"), json!("why")))
        .collect();
    let page = document(&json!({"status": "UNKNOWN", "rules": rules, "explained": explained}));
    let card = page
        .split("id=\"unknown\"")
        .nth(1)
        .unwrap()
        .split("</article>")
        .next()
        .unwrap();
    assert!(card.contains("R05") && card.contains("R39") && !card.contains("R40"));
    assert!(card.contains("<details class=\"rp-fold\"><summary class=\"caption rp-at\">+45 more"));
    assert!(card.contains("and 10 more"));
}

#[test]
fn the_page_wraps_a_long_term_and_the_folds_print_open() {
    let css = include_str!("../assets/report.css");
    assert!(css.contains(".rp-kv dt { color: var(--ink-muted); overflow-wrap: anywhere; }"));
    assert!(css.contains("details::details-content"));
    // At 390 px the identity list is one column and a small table scrolls inside itself.
    assert!(css.contains(".rp-kv { grid-template-columns: minmax(0, 1fr); }"));
    assert!(css.contains(".rp-mini { display: block; max-width: 100%; overflow-x: auto; }"));
}
