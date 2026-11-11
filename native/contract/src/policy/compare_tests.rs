// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Tests of `compare_trees` (AD-373). The parity test in `tests/` compares each message with
//! Python; these tests name the decision of each classifier.

use serde_json::{json, Value};

use crate::policy::{assemble_tree, compare_trees, ChangeDirection, ContractTree};

const ROOT: &str = "architecture-contract.json";

fn component(label: &str) -> Value {
    json!({
        "id": format!("C-{label}"),
        "label": label,
        "role": "component",
        "packages": [format!("p.{label}")],
        "responsibilities": ["Own it."],
        "forbidden_responsibilities": [],
        "provenance": ["d.md"],
    })
}

fn rule(id: &str, kind: &str, extra: &Value) -> Value {
    let mut value = json!({
        "id": id, "kind": kind, "rationale": "r", "provenance": ["d.md"], "decided_by": "architect",
    });
    if let (Some(map), Some(more)) = (value.as_object_mut(), extra.as_object()) {
        map.extend(more.clone());
    }
    value
}

fn base() -> Value {
    let mut b = component("b");
    b["requires"] = json!([{"component": "a", "rationale": "r", "through": ["p.a.x"]}]);
    let mut a = component("a");
    a["public"] = json!(["p.a.x"]);
    a["planned"] = json!(["p.a.y"]);
    json!({
        "schema_version": "3.14.0",
        "components": [a, b],
        "rules": [
            rule("R-DEP", "forbidden_dependency",
                 &json!({"source": "p.b", "target": "p.a", "include_type_checking": true})),
            rule("R-ALLOW", "allowed_dependency", &json!({"source": "p.b", "target": "p.a"})),
        ],
    })
}

fn tree(value: &Value) -> ContractTree {
    let root = crate::contract::parse(&serde_json::to_vec(value).unwrap()).unwrap();
    assemble_tree(ROOT, root, &[]).unwrap()
}

/// The messages from `before` to `after`, with `+` for a widening and `-` for a narrowing.
fn messages(before: &Value, after: &Value) -> Vec<String> {
    let comparison = compare_trees(&tree(before), &tree(after));
    let sign = |direction: &ChangeDirection| match direction {
        ChangeDirection::Widened => '+',
        ChangeDirection::Narrowed => '-',
    };
    let found: Vec<String> = comparison
        .changes()
        .iter()
        .map(|change| format!("{}{}", sign(change.direction()), change.message()))
        .collect();
    assert_eq!(
        comparison.widened(),
        found.iter().any(|item| item.starts_with('+'))
    );
    found
}

fn changed(edit: impl FnOnce(&mut Value)) -> Vec<String> {
    let mut after = base();
    edit(&mut after);
    messages(&base(), &after)
}

#[test]
fn an_equal_tree_has_no_change() {
    assert!(messages(&base(), &base()).is_empty());
}

#[test]
fn a_component_added_or_removed_widens() {
    let added = changed(|value| {
        value["components"]
            .as_array_mut()
            .unwrap()
            .push(component("c"))
    });
    assert_eq!(added, ["+component 'c' added"]);
    let mut smaller = base();
    smaller["components"].as_array_mut().unwrap().pop();
    smaller["rules"] = json!([]);
    let removed = messages(&base(), &smaller);
    assert!(
        removed.contains(&"+component 'b' removed".to_owned()),
        "{removed:?}"
    );
    assert!(removed.contains(&"+rule R-DEP (forbidden_dependency) removed".to_owned()));
    assert!(removed.contains(&"-rule R-ALLOW (allowed_dependency) removed".to_owned()));
}

#[test]
fn a_public_entry_gained_widens_and_a_promoted_entry_does_not() {
    let moved = changed(|value| value["components"][0]["public"] = json!(["p.a.z.x"]));
    let expected = [
        "+component 'a'.public gained 'p.a.z.x' in place of 'p.a.x'",
        "-component 'a'.public lost 'p.a.x'",
    ];
    assert_eq!(moved, expected);
    let promoted = changed(|value| {
        value["components"][0]["public"] = json!(["p.a.x", "p.a.y"]);
        value["components"][0]["planned"] = json!([]);
    });
    assert!(promoted.is_empty(), "{promoted:?}");
    let dropped = changed(|value| value["components"][0]["planned"] = json!([]));
    assert_eq!(dropped, ["+component 'a'.planned lost 'p.a.y'"]);
}

#[test]
fn a_requires_entry_that_permits_more_widens() {
    let wider = changed(|value| value["components"][1]["requires"][0]["through"] = json!(["p.a"]));
    let expected = [
        "+component 'b'.requires['a'] gained an entry through ['p.a']",
        "-component 'b'.requires['a'] narrowed from [['p.a']] to [['p.a.x']]",
    ];
    assert_eq!(wider[0], expected[0]);
    let narrower =
        changed(|value| value["components"][1]["requires"][0]["through"] = json!(["p.a.x.y"]));
    assert_eq!(
        narrower,
        ["-component 'b'.requires['a'] narrowed from [['p.a.x']] to [['p.a.x.y']]"]
    );
    let gone = changed(|value| value["components"][1]["requires"] = json!([]));
    assert_eq!(
        gone,
        ["-component 'b'.requires['a'] dropped through [['p.a.x']]"]
    );
    let symbol =
        changed(|value| value["components"][1]["requires"][0]["through"] = json!(["p.a.x:K"]));
    assert_eq!(
        symbol,
        ["-component 'b'.requires['a'] narrowed from [['p.a.x']] to [['p.a.x:K']]"]
    );
}

#[test]
fn a_new_requires_target_and_another_field_widen() {
    let mut start = base();
    start["components"][1]["requires"] = json!([]);
    let edge = messages(&start, &base());
    assert_eq!(edge, ["+component 'b'.requires gained an edge to 'a'"]);
    let layer = changed(|value| value["components"][0]["layer"] = json!("Core"));
    assert_eq!(layer, ["+component 'a'.layer changed from None to 'Core'"]);
    let namespace = changed(|value| value["components"][0]["namespace"] = json!("p.a"));
    assert!(namespace.is_empty());
    let mut named = base();
    named["components"][0]["namespace"] = json!("p.a");
    let renamed = messages(&named, &base());
    assert_eq!(
        renamed,
        ["+component 'a'.namespace changed from 'p.a' to None"]
    );
}

#[test]
fn a_rule_classifier_reports_the_widening_side_only() {
    let more = changed(|value| value["rules"][0]["allowed_sources"] = json!(["p.b.x"]));
    assert_eq!(more, ["+rule R-DEP.allowed_sources gained 'p.b.x'"]);
    let relaxed = changed(|value| value["rules"][0]["include_type_checking"] = json!(false));
    assert_eq!(
        relaxed,
        ["+rule R-DEP.include_type_checking relaxed from true to false"]
    );
    let target = changed(|value| value["rules"][0]["target"] = json!("p.c"));
    assert_eq!(target, ["+rule R-DEP.target changed from 'p.a' to 'p.c'"]);
    let kind = changed(|value| {
        value["rules"][1] = rule(
            "R-ALLOW",
            "complete_requires",
            &json!({"include_type_checking": true}),
        );
    });
    let expected = "+rule R-ALLOW changed kind from allowed_dependency to complete_requires";
    assert_eq!(kind, [expected]);
}

#[test]
fn a_restriction_added_narrows_and_a_permission_added_widens() {
    let mut start = base();
    start["rules"] = json!([]);
    let found = messages(&start, &base());
    let expected = [
        "+rule R-ALLOW (allowed_dependency) added",
        "-rule R-DEP (forbidden_dependency) added",
    ];
    assert_eq!(found, expected);
}

#[test]
fn a_kind_without_a_classifier_fails_closed() {
    let order = |rationale: &str| {
        rule(
            "R-L",
            "layer_order",
            &json!({"layers": ["a", "b"], "rationale": rationale}),
        )
    };
    let mut before = base();
    before["rules"].as_array_mut().unwrap().push(order("r"));
    let mut after = base();
    after["rules"].as_array_mut().unwrap().push(order("other"));
    let found = messages(&before, &after);
    assert_eq!(
        found,
        ["+rule R-L changed in a way this comparison does not enumerate"]
    );
}

#[test]
fn a_declaration_change_widens() {
    let schema = changed(|value| value["$schema"] = json!("s"));
    assert_eq!(schema, ["+contract.$schema changed from None to 's'"]);
    let module = changed(|value| {
        value["declarations"] =
            json!({"modules": [{"path": "src/a.py", "responsibility": "Own a."}]});
    });
    let expected = "+contract.declarations changed in a way this comparison does not enumerate";
    assert_eq!(module, [expected]);
    let compat = changed(|value| {
        value["declarations"] =
            json!({"compat": [{"module": "p.old", "target": "p.a", "lifetime": "permanent"}]});
    });
    assert_eq!(compat, ["+compat module 'p.old' added"]);
    let mut budget = base();
    budget["declarations"] =
        json!({"measurement_budgets": [{"name": "cycle_edges", "provenance": ["d.md"]}]});
    let lost = messages(&budget, &base());
    assert_eq!(
        lost,
        ["+contract.declarations.measurement_budgets lost 'cycle_edges'"]
    );
}

#[test]
fn a_value_without_its_fields_widens() {
    let fields = serde_json::Map::new();
    let found = crate::policy::change::generic_widenings("rule R", None, Some(&fields), &[]);
    let messages: Vec<&str> = found
        .iter()
        .map(|change| change.message().as_str())
        .collect();
    assert_eq!(messages, ["rule R could not be compared field by field"]);
}
