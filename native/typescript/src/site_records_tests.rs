// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: PR 4.3a-3d, which puts the records on the wire. The expected values follow the Python
// collector; `tests/test_collector_native_records.py` compares every record on real trees.

use archkeel_facts::envelope::Dirty;
use archkeel_facts::envelope::{Profile, Provenance};
use archkeel_facts::request::{Scope, Snapshot, TypeScriptRequest, TypeScriptSettings};
use archkeel_wire::protocol::Version;
use archkeel_wire::reply::Record;
use serde_json::Value;

use crate::collect::records;
use crate::records::Records;
use archkeel_snapshot::test_tree::Tree;

fn request(tree: &Tree) -> TypeScriptRequest {
    TypeScriptRequest {
        protocol_version: Version::V9,
        snapshot: Snapshot {
            root: tree.path(),
            git_head: "a".repeat(40),
            dirty: Dirty::Known(false),
        },
        scope: Scope {
            roots: vec!["src".to_owned()],
            namespace: "shop".to_owned(),
            exclude_test_sources: Some(false),
        },
        resolver: TypeScriptSettings {
            tsconfig: "tsconfig.json".to_owned(),
            bundler: false,
        },
    }
}

fn provenance() -> Provenance {
    Provenance::native(
        Profile::TypeScript,
        ("0+unknown", &"0".repeat(64)),
        ("1.88.0", "1.88"),
    )
}

fn run(files: &[(&str, &str)]) -> Records {
    let mut all = vec![("tsconfig.json", r#"{"include":["src"]}"#)];
    all.extend_from_slice(files);
    let tree = Tree::new(&all);
    records(&request(&tree), provenance()).unwrap().1
}

fn call<'a>(found: &'a Records, expression: &str) -> &'a Record {
    found
        .calls
        .iter()
        .find(|record| record.title == expression)
        .unwrap()
}

#[test]
fn a_call_of_a_local_function_resolves_and_a_second_definition_makes_it_partial() {
    let found = run(&[(
        "src/a.ts",
        "function f() {}\nfunction g() {}\nfunction g() {}\nf(); g(); h();\n",
    )]);
    let data = |name: &str| call(&found, name).data.clone();
    assert_eq!(data("f")["status"], "resolved");
    assert_eq!(data("f")["candidate_count"], 1);
    assert_eq!(data("g")["status"], "partially_resolved");
    assert_eq!(
        data("g")["reason"],
        "multiple definition sites share the target name"
    );
    assert_eq!(data("h")["status"], "unresolved");
    assert_eq!(data("h")["reason"], "definition is missing or ambiguous");
    assert!(data("f").get("source_definition_id").is_none());
}

#[test]
fn a_shadowed_a_rebound_and_a_computed_name_keep_their_reason() {
    let found = run(&[(
        "src/a.ts",
        "function f() {}\nfunction w(f) { f(); }\nlet g = 1; g = 2;\nfunction g() {}\ng();\nobj[f]();\n",
    )]);
    let reasons: Vec<(&str, &str)> = found
        .calls
        .iter()
        .map(|record| {
            (
                record.title.as_str(),
                record
                    .data
                    .get("reason")
                    .and_then(Value::as_str)
                    .unwrap_or(""),
            )
        })
        .collect();
    assert!(reasons.contains(&("f", "lexical binding may shadow the name")));
    assert!(reasons.contains(&("g", "name is rebound in module scope")));
    assert!(reasons.iter().any(|(title, _)| title.starts_with("obj[")));
}

#[test]
fn a_this_member_resolves_to_the_field_of_its_class_and_an_import_to_the_exporting_file() {
    let found = run(&[
        ("src/a.ts", "export function one() {}\nexport class Box {}\n"),
        (
            "src/b.ts",
            "import { one, Box } from './a';\nclass K { f = 1; m() { return this.f + this.nope; } }\n\
             one(); const b = new Box();\n",
        ),
    ]);
    let this_refs: Vec<(&str, &str)> = found
        .references
        .iter()
        .filter(|record| record.title.starts_with("this."))
        .map(|record| {
            (
                record.title.as_str(),
                record.data["status"].as_str().unwrap(),
            )
        })
        .collect();
    assert_eq!(
        this_refs,
        [("this.f", "resolved"), ("this.nope", "unresolved")]
    );
    let imported = call(&found, "one");
    assert_eq!(imported.data["status"], "resolved");
    assert!(imported.data["targets"][0]
        .as_str()
        .unwrap()
        .ends_with("a_x2e_ts.one"));
}

#[test]
fn a_new_expression_assigned_to_a_name_makes_a_construction_and_a_value_binding() {
    let found = run(&[("src/a.ts", "class C {}\nconst c: C = new C();\nnew C();\n")]);
    assert_eq!(found.bindings.len(), 1);
    assert!(found.bindings[0].id.starts_with("VALUEBIND-"));
    assert!(found.bindings[0].title.ends_with(".c binding"));
    let news: Vec<&Record> = found
        .calls
        .iter()
        .filter(|record| record.title == "C")
        .collect();
    assert_eq!(news.len(), 2);
    assert_eq!(news[0].data["construction"]["status"], "resolved");
    assert_eq!(news[0].data["result_bindings"][0]["annotation"], "C");
    assert_eq!(news[1].data["result_bindings"], Value::Array(vec![]));
}

#[test]
fn a_construction_of_a_name_with_two_classes_is_partial_and_a_hidden_export_is_not_imported() {
    let found = run(&[
        ("src/a.ts", "function hidden() {}\nexport function shown() {}\n"),
        (
            "src/b.ts",
            "import { hidden, shown } from './a';\nclass D {}\nclass D {}\nnew D(); hidden(); shown();\n",
        ),
    ]);
    let new_d = call(&found, "D");
    assert_eq!(new_d.data["status"], "partially_resolved");
    assert_eq!(new_d.data["construction"]["status"], "partially_resolved");
    assert_eq!(call(&found, "hidden").data["status"], "unresolved");
    assert_eq!(call(&found, "shown").data["status"], "resolved");
}
