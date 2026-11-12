// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The clip of an inside contract to its parent (`_inside_source_domain`, AD-385).

use serde_json::{json, Value};

use crate::contract::parse;
use crate::document::{Contract, ParsedContract};
use crate::policy::clip_inside;

fn component(label: &str, packages: &[&str], exact: &[&str]) -> Value {
    let mut item = json!({
        "id": format!("C-{label}"), "label": label, "role": "component", "packages": packages,
        "responsibilities": ["Own it."], "forbidden_responsibilities": [],
        "provenance": ["docs/a.md"],
    });
    if !exact.is_empty() {
        item["exact_modules"] = json!(exact);
    }
    item
}

fn contract(components: Vec<Value>) -> Option<Contract> {
    let value = json!({"schema_version": "3.14.0", "components": components, "rules": []});
    match parse(&serde_json::to_vec(&value).unwrap_or_default()) {
        Ok(ParsedContract::Complete(contract)) => Some(contract),
        _ => None,
    }
}

fn names(contract: &Contract, label: &str) -> (Vec<String>, Vec<String>) {
    let component = contract
        .components()
        .iter()
        .find(|item| item.label().as_text() == label);
    let text = |items: &[crate::model::Package]| items.iter().map(|p| p.0.clone()).collect();
    component.map_or((Vec::new(), Vec::new()), |item| {
        (text(item.packages()), text(item.exact_modules()))
    })
}

fn clip(parent: &Contract, inside: &Contract) -> crate::policy::Clipped {
    let parent = &parent.components()[0];
    clip_inside(parent.packages(), parent.exact_modules(), inside)
}

#[test]
fn a_claim_below_the_parent_stays_and_a_claim_outside_is_cut_and_named() {
    let parent = contract(vec![component("d", &["p.d"], &["q.one"])]);
    let inside = contract(vec![
        component(
            "in",
            &["p.d.a", "p.dx", "p"],
            &["q.one", "p.d.b.m", "q.two"],
        ),
        component("ok", &["p.d"], &[]),
    ]);
    let (Some(parent), Some(inside)) = (parent, inside) else {
        assert_eq!("the test contracts must parse", "loaded");
        return;
    };
    let clipped = clip(&parent, &inside);
    let (packages, exact) = names(clipped.contract(), "in");
    // A text prefix (`p.dx`) and a parent package (`p`) are outside; `q.one` is an exact module
    // of the parent; `p.d.b.m` lies below a package of the parent.
    assert_eq!(packages, ["p.d.a"]);
    assert_eq!(exact, ["q.one", "p.d.b.m"]);
    assert_eq!(names(clipped.contract(), "ok").0, ["p.d"]);
    let outside: Vec<&str> = clipped.outside().iter().map(|id| id.0.as_str()).collect();
    assert_eq!(outside, ["C-in"]);
    assert_eq!(clipped.contract().digest(), inside.digest());
}

#[test]
fn a_parent_without_packages_cuts_every_package_claim() {
    let (Some(parent), Some(inside)) = (
        contract(vec![component("d", &[], &["q.one"])]),
        contract(vec![component("in", &["q"], &["q.one"])]),
    ) else {
        assert_eq!("the test contracts must parse", "loaded");
        return;
    };
    let clipped = clip(&parent, &inside);
    assert_eq!(
        names(clipped.contract(), "in"),
        (vec![], vec!["q.one".to_owned()])
    );
    assert_eq!(clipped.outside().len(), 1);
}

/// Review of #1086, S2: a component that loses only an exact module is named too.
#[test]
fn a_component_that_loses_only_an_exact_module_is_named() {
    let (Some(parent), Some(inside)) = (
        contract(vec![component("d", &["p.d"], &[])]),
        contract(vec![
            component("ok", &["p.d.a"], &[]),
            component("x", &[], &["q.outside"]),
        ]),
    ) else {
        assert_eq!("the test contracts do not parse", "loaded");
        return;
    };
    let clipped = clip(&parent, &inside);
    assert_eq!(names(clipped.contract(), "x"), (vec![], vec![]));
    let outside: Vec<&str> = clipped.outside().iter().map(|id| id.0.as_str()).collect();
    assert_eq!(outside, ["C-x"]);
}
