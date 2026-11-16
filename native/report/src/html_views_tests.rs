// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the views of the architecture picture (AD-594). The frame is built by hand: it has a
// violation, a requirement without an observed import and a pair that a gap holds.

use serde_json::{json, Value};

use super::frame::Frame;
use super::views::{links, Mark, View};
use super::*;

fn frame() -> Value {
    let component = |id: &str, name: &str, layer: &str, public: &[&str]| json!({"id": id, "name": name, "layer": layer, "public": public});
    let module = |name: &str, id: &str| json!({"name": format!("app.{name}"), "path": format!("src/{name}.rs"), "component": id});
    let edge = |source: &str, target: &str, count: usize| json!({"source": source, "target": target, "resolution": "resolved", "count": count});
    let require = |source: &str, target: &str, imports: usize| json!({"source": source, "target": target, "imports": imports});
    json!({"status": "FAIL",
        "rules": {"R": ["forbidden_dependency", "FAIL"], "Q": ["complete_requires", "UNKNOWN"],
            "LAYERS": ["layer_order", "PASS"]},
        "explained": {"Q": "a gap holds a pair"},
        "details": {"R": [{"source": "app.api", "target": "app.store",
            "cause": "forbidden dependency", "evidence": ["E"]}]},
        "locations": {"E": {"path": "src/api.rs", "line": 3}},
        "explain": {"rules": {"R": {"kind": "forbidden_dependency", "direction": "forbids",
                "source": ["API"], "target": ["STORE"]}}, "cycles": {},
            "holds": {"rules": {"Q": {"kind": "pair_gaps", "total": 3,
                "pairs": [{"source": "app.cli", "target": "app.store"},
                    {"source": "app.cli", "target": "ext.lib"}]}}}},
        "topology": {
            "components": [component("API", "api", "edge", &[]),
                component("CLI", "cli", "edge", &[]),
                component("CORE", "core", "core", &["app.core", "app.core:Port"]),
                component("STORE", "store", "core", &[])],
            "modules": [module("api", "API"), module("cli", "CLI"), module("core", "CORE"),
                module("store", "STORE")],
            "component_edges": [edge("API", "CORE", 2), edge("API", "STORE", 1),
                edge("CLI", "CORE", 1)],
            "requires": [require("API", "CORE", 2), require("CLI", "CORE", 1),
                require("CORE", "STORE", 0)],
            "layers": [{"rule": "LAYERS", "layers": ["core", "edge"]}],
            "total": {"components": 4, "modules": 4, "component_edges": 3, "requires": 3,
                "layers": 1}}})
}

fn section(frame: &Value) -> String {
    let rendered = render(frame.as_object().unwrap()).unwrap();
    let page = rendered["document"].as_str().unwrap();
    let start = page.find("<section class=\"rp-sec\" aria-labelledby=\"arch\">");
    let rest = &page[start.unwrap()..];
    rest[..rest.find("</section>").unwrap() + "</section>".len()].to_owned()
}

/// One element on each line, so that a change of the golden file reads as a diff.
fn lines(html: &str) -> String {
    format!("{}\n", html.replace("><", ">\n<"))
}

// Set `ARCHKEEL_WRITE_GOLDEN=1` to write the file again after a change that is intended.
#[test]
fn the_three_views_of_a_small_frame_are_the_golden_section() {
    let found = lines(&section(&frame()));
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/testdata/views.html");
    if std::env::var_os("ARCHKEEL_WRITE_GOLDEN").is_some() {
        std::fs::write(path, &found).unwrap();
    }
    assert_eq!(found, include_str!("../testdata/views.html"));
}

#[test]
fn each_view_marks_a_pair_from_the_facts_of_the_frame() {
    let value = frame();
    let view = Frame::of(&value);
    let (places, names) = (places::Places::of(&view), cases::Names::of(&view));
    let (found, failing) = links(&view, &places, &names);
    let marks = |from: &str, to: &str| {
        let link = found.iter().find(|l| (l.from, l.to) == (from, to)).unwrap();
        View::ALL.map(|view| link.mark(view))
    };
    let (plain, fail) = (Some(Mark::Plain), Some(Mark::Fail));
    // Observed and declared: As-Is and Target show it, Diff does not.
    assert_eq!(marks("API", "CORE"), [plain, plain, None]);
    // Observed and against a rule: no requirement declares it, so Target does not show it.
    assert_eq!(marks("API", "STORE"), [fail, None, fail]);
    // Held by a gap and not observed: only Diff shows it.
    assert_eq!(marks("CLI", "STORE"), [None, None, Some(Mark::Unknown)]);
    // Declared and without an observed import: Target shows it, Diff names it.
    assert_eq!(marks("CORE", "STORE"), [None, plain, Some(Mark::Unused)]);
    assert_eq!(found.len(), 5);
    assert_eq!(failing.into_iter().collect::<Vec<_>>(), ["API"]);
}

#[test]
fn one_mark_is_one_element_that_names_each_view_that_shows_it() {
    let page = section(&frame());
    // As-Is is the view that a page opens with.
    assert_eq!(page.matches("type=\"radio\"").count(), 3);
    assert_eq!(page.matches(" checked>").count(), 1);
    assert!(page.contains("id=\"rp-view-a\" checked>"));
    // The map and the matrix draw each pair: one path and one cell mark for each mark.
    assert_eq!(
        page.matches("<path class=\"ak-edge rp-in rp-a rp-t\"")
            .count(),
        2
    );
    assert!(page.contains("<path class=\"ak-edge ak-edge--violation rp-in rp-a rp-d\""));
    assert!(page.contains("<path class=\"ak-edge rp-edge--unknown rp-in rp-d\""));
    assert!(page.contains("<path class=\"ak-edge rp-edge--unused rp-in rp-d\""));
    assert!(page.contains(
        "<a class=\"rp-v rp-in rp-a rp-d\" href=\"#x1\" title=\"api to store: 1 violation\">1</a>"
    ));
    assert!(page.contains(
        "<a class=\"rp-u rp-in rp-d\" href=\"#unknown\" title=\"cli to store: a gap holds this pair\">?</a>"
    ));
    assert!(page.contains(
        "<span class=\"rp-un rp-in rp-d\" title=\"core to store: declared, no observed import uses it\"></span>"
    ));
}

#[test]
fn diff_names_each_difference_and_target_states_the_declared_structure() {
    let page = section(&frame());
    // Diff lists each violated place with its rules, and each pair of modules that a gap holds,
    // also a pair that no pair of components carries.
    assert!(page.contains("<b>Diff:</b> 1 violated place, 2 pairs of modules that a gap holds, 1 requirement without an observed import."));
    assert!(page.contains(
        "<a href=\"#x1\"><span class=\"rp-no\">1</span> src/api.rs imports src/store.rs</a> &#183; <b class=\"rp-code\">R</b>"
    ));
    assert!(page.contains("Held by a gap, not decided: 2"));
    assert!(page.contains("<a href=\"#unknown\">app.cli <span class=\"rp-at\">(cli)</span> to ext.lib</a> &#183; <b class=\"rp-code\">Q</b>"));
    assert!(page.contains("The frame names 2 of 3 pairs that a gap holds for a rule."));
    assert!(page.contains("Declared and without an observed import, for information: 1"));
    // Target states the layers and the public surface that the contract declares.
    assert!(page.contains("Layers of <b class=\"rp-code\">LAYERS</b>, inner to outer: core, edge."));
    assert!(page.contains(">core &#183; 2 public</text>"));
    assert!(page.contains("title=\"app.core, app.core:Port\">2</td>"));
}

#[test]
fn a_frame_without_declared_rows_says_so_and_keeps_the_picture() {
    let mut value = frame();
    let topology = value["topology"].as_object_mut().unwrap();
    topology.remove("requires");
    topology.remove("layers");
    for component in topology["components"].as_array_mut().unwrap() {
        *component = json!({"id": component["id"], "name": component["name"]});
    }
    let page = section(&value);
    assert!(page
        .contains("<b>Target:</b> the contract declares no requirement, layer or public surface."));
    assert!(page.contains("class=\"ak-diagram rp-map\"") && !page.contains(">Layer</th>"));
    assert!(!page.contains("rp-edge--unused") && page.contains("rp-edge--unknown"));
}

#[test]
fn the_views_add_no_script_and_each_link_has_a_target() {
    let rendered = render(frame().as_object().unwrap()).unwrap();
    let page = rendered["document"].as_str().unwrap();
    assert_eq!(page.matches("<script>").count(), 1);
    for link in page.split("href=\"#").skip(1) {
        let id = link.split('"').next().unwrap();
        assert!(page.contains(&format!("id=\"{id}\"")), "{id} has no target");
    }
    for label in page.split("<label class=\"ak-seg__btn ui\" for=\"").skip(1) {
        let id = label.split('"').next().unwrap();
        assert!(page.contains(&format!("id=\"{id}\"")), "{id} has no input");
    }
}

#[test]
fn a_hostile_layer_and_rule_reach_no_markup() {
    let mut value = frame();
    let hostile = "<script>\"x";
    value["topology"]["components"][0]["layer"] = json!(hostile);
    value["topology"]["components"][0]["public"] = json!([hostile]);
    value["topology"]["layers"][0] = json!({"rule": hostile, "layers": [hostile]});
    let page = section(&value);
    assert!(!page.contains("<script>") && page.contains("&lt;script&gt;&quot;x"));
}
