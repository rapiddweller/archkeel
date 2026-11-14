// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The contract references of AD-466 against the rules of the reference engine.

use archkeel_contract::{parse, Contract, ParsedContract};
use serde_json::{json, Value};

use super::{namespace, placeholder, public, rationale, repeats, responsibility};

fn component(label: &str, extra: Value) -> Value {
    let mut item = json!({
        "id": format!("C-{label}"), "label": label, "role": "component",
        "packages": [format!("app.{label}")], "responsibilities": ["Own it."],
        "forbidden_responsibilities": [], "provenance": ["d.md"], "decided_by": "architect",
    });
    if let (Some(map), Value::Object(more)) = (item.as_object_mut(), extra) {
        map.extend(more);
    }
    item
}

fn rule(id: &str, kind: &str, extra: Value) -> Value {
    let mut item = json!({"id": id, "kind": kind, "rationale": "Keep the layers apart.",
                          "provenance": ["d.md"], "decided_by": "architect"});
    if let (Some(map), Value::Object(more)) = (item.as_object_mut(), extra) {
        map.extend(more);
    }
    item
}

fn contract(components: Vec<Value>, rules: Vec<Value>) -> Contract {
    let value = json!({"schema_version": "3.14.0", "components": components, "rules": rules});
    let parsed = parse(&serde_json::to_vec(&value).unwrap_or_default()).ok();
    let complete = parsed.and_then(|parsed| match parsed {
        ParsedContract::Complete(contract) => Some(contract),
        ParsedContract::NeedsTree(_) => None,
    });
    complete.expect("a complete contract")
}

fn codes(found: Vec<super::Finding>) -> Vec<String> {
    found
        .into_iter()
        .map(|(code, pointer, subject, _)| format!("{code} {pointer} {subject}"))
        .collect()
}

#[test]
fn a_placeholder_is_a_word_at_the_start_with_a_boundary() {
    for text in ["TODO", "todo: explain", "TBD.", "Placeholder for now"] {
        assert!(placeholder(text).is_some(), "{text}");
    }
    for text in ["todos", "tbdx", "explain later: todo", "to do"] {
        assert!(placeholder(text).is_none(), "{text}");
    }
}

#[test]
fn a_repeated_rationale_is_the_whole_sentence() {
    let forbidden = ["does not depend on"];
    assert!(repeats("The domain does not depend on data.", &forbidden));
    assert!(repeats("domain DOES NOT DEPEND ON data.", &forbidden));
    assert!(repeats("a.b does not depend on c.d.", &forbidden));
    assert!(!repeats("domain does not depend on data", &forbidden));
    assert!(!repeats("domain  does not depend on data.", &forbidden));
    assert!(!repeats(
        "domain does not depend on data. It is pure.",
        &forbidden
    ));
    let requires = ["depends on", "requires", "uses", "needs"];
    assert!(repeats("app uses data.", &requires));
    assert!(!repeats("app uses data to load orders.", &requires));
}

#[test]
fn rationale_names_rules_and_requires_entries() {
    let requires =
        json!({"requires": [{"component": "b", "rationale": "a needs b.", "through": []}]});
    let found = rationale(&contract(
        vec![component("a", requires), component("b", json!({}))],
        vec![rule("R", "complete_requires", json!({"rationale": "tbd"}))],
    ));
    assert_eq!(
        codes(found),
        [
            "rationale.placeholder /rules/0/rationale R",
            "rationale.repeated /components/0/requires/0/rationale a -> b",
        ]
    );
}

#[test]
fn an_architect_component_needs_a_substantive_responsibility() {
    let found = responsibility(&contract(
        vec![
            component("a", json!({"responsibilities": ["todo:"]})),
            component("b", json!({"responsibilities": ["todo: own the orders"]})),
            component("c", json!({"responsibilities": [], "decided_by": "agent"})),
            component("d", json!({"responsibilities": ["PLACEHOLDER"]})),
        ],
        Vec::new(),
    ));
    assert_eq!(
        codes(found),
        [
            "responsibility.missing /components/0/responsibilities a",
            "responsibility.missing /components/3/responsibilities d",
        ]
    );
}

#[test]
fn each_held_reference_stays_in_the_namespace() {
    let found = namespace(
        &contract(
            vec![
                component("a", json!({"public": ["other.a:Name"]})),
                component("b", json!({"packages": ["other.b"]})),
            ],
            vec![
                rule(
                    "F",
                    "forbidden_dependency",
                    json!({"source": "app.a", "target": "lib", "include_type_checking": true,
                            "allowed_sources": ["x.y"]}),
                ),
                rule(
                    "N",
                    "forbidden_dependency",
                    json!({"source": "app.a", "target": "lib", "include_type_checking": true,
                            "target_kind": "import_namespace", "allowed_sources": []}),
                ),
                rule(
                    "S",
                    "sibling_isolation",
                    json!({"members": ["app.a", "elsewhere"]}),
                ),
            ],
        ),
        "app",
    );
    assert_eq!(
        codes(found),
        [
            "reference.namespace /components/0/public/0 other.a:Name",
            "reference.namespace /components/1/packages/0 other.b",
            "reference.namespace /rules/0/target lib",
            "reference.namespace /rules/0/allowed_sources/0 x.y",
            "reference.namespace /rules/2/members/1 elsewhere",
        ]
    );
}

#[test]
fn a_public_entry_needs_its_own_owner_and_no_underscore_name() {
    let found = public(&contract(
        vec![
            component(
                "a",
                json!({"public": ["app.b.m", "app.a.m:_hidden", "app.a.m:Shown"]}),
            ),
            component("b", json!({"planned": ["app.a.n"]})),
        ],
        Vec::new(),
    ));
    assert_eq!(
        codes(found),
        [
            "reference.public_owner /components/0/public/0 app.b.m",
            "reference.public_underscore /components/0/public/1 app.a.m:_hidden",
            "reference.public_owner /components/1/planned/0 app.a.n",
        ]
    );
}
