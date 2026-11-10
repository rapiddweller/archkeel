// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: PR 4.3a-3d, which puts the records on the wire, and PR 4.3a-3c, which reads the symbol
// table. The expected values follow the Python collector; `tests/test_collector_native_records.py`
// compares every record on real trees.

use archkeel_facts::envelope::Dirty;
use archkeel_facts::envelope::{Profile, Provenance};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::request::{Scope, Snapshot, TypeScriptRequest, TypeScriptSettings};
use archkeel_wire::protocol::Version;
use archkeel_wire::reply::Record;
use serde_json::Value;

use crate::collect::records;
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

fn symbols(source: &str) -> Vec<Record> {
    let tree = Tree::new(&[
        ("tsconfig.json", r#"{"include":["src"]}"#),
        ("src/a.ts", source),
    ]);
    records(&request(&tree), provenance()).unwrap().1.symbols
}

fn named<'a>(list: &'a [Record], name: &str) -> &'a Record {
    list.iter()
        .find(|record| record.data["name"] == name)
        .unwrap()
}

#[test]
fn a_class_has_its_id_its_inventories_its_bases_and_its_methods() {
    let list = symbols(
        "interface I { a: number }\nclass B {}\n\
         class C extends B implements I, Missing { f: number = 1; static m(x: number, ...r: string[]) {} }\n",
    );
    let class = named(&list, "C");
    let line_column = (3, 1);
    let id = stable_id(
        "TSDEF",
        &[
            Part::Text("src/a.ts"),
            Part::Number(line_column.0),
            Part::Number(line_column.1),
            Part::Text(class.data["qualified_name"].as_str().unwrap()),
            Part::Text("class"),
        ],
    );
    assert_eq!(class.id, id);
    let inventories = class.data["member_inventories"].as_array().unwrap();
    assert_eq!(inventories[0]["status"], "complete");
    assert_eq!(
        inventories[0]["definition_ids"].as_array().unwrap().len(),
        1
    );
    assert_eq!(
        inventories[1]["definition_ids"].as_array().unwrap().len(),
        1
    );
    let bases: Vec<(&str, &str)> = class.data["base_declarations"]
        .as_array()
        .unwrap()
        .iter()
        .map(|base| {
            (
                base["relationship_kind"].as_str().unwrap(),
                base["status"].as_str().unwrap(),
            )
        })
        .collect();
    assert_eq!(
        bases,
        [
            ("inherits", "resolved"),
            ("realizes", "resolved"),
            ("realizes", "unresolved")
        ]
    );
    let method = named(&list, "m");
    assert_eq!(method.data["method_kind"], "static");
    assert_eq!(method.data["parameters"][1]["kind"], "varargs");
    assert_eq!(
        method.data["lexical_parent_id"],
        Value::from(class.id.clone())
    );
}

#[test]
fn an_interface_is_a_protocol_and_an_enum_lists_its_members() {
    let list = symbols("interface I { a: number }\nenum E { X, Y }\n");
    assert_eq!(named(&list, "I").data["class_kind"], "protocol");
    let en = named(&list, "E");
    assert_eq!(en.data["class_kind"], "enum");
    assert_eq!(en.data["enum_members"], serde_json::json!(["X", "Y"]));
    assert_eq!(en.kind, "class");
}

#[test]
fn a_name_with_two_definitions_is_not_unique_and_its_inventory_is_partial() {
    let list = symbols(
        "class K {}\nclass K { a = 1 }\nfunction f(a: number): void;\nfunction f(a: any) {}\n",
    );
    for record in list.iter().filter(|record| record.data["name"] == "K") {
        assert_eq!(record.data["source_binding_unique"], false);
        let inventories = record.data["member_inventories"].as_array().unwrap();
        assert_eq!(inventories[0]["status"], "partial");
        assert_eq!(
            inventories[0]["reason"],
            "computed or unsupported member syntax"
        );
    }
    assert!(list
        .iter()
        .filter(|record| record.data["name"] == "f")
        .all(|record| record.data["source_binding_unique"] == false));
}

#[test]
fn an_enum_is_not_a_base_class_and_a_nested_class_keeps_its_own_methods() {
    let list = symbols("enum E {}\nclass D extends E {}\nfunction f() { class L { n() {} } }\n");
    let bases = named(&list, "D").data["base_declarations"]
        .as_array()
        .unwrap()
        .clone();
    assert_eq!(bases[0]["status"], "unresolved");
    assert_eq!(bases[0]["reason"], "Base is not a unique local classifier");
    let inner = named(&list, "L");
    assert_eq!(
        inner.data["member_inventories"][1]["definition_ids"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(
        inner.data["parent"].as_str().unwrap().rsplit('.').next(),
        Some("f")
    );
}

#[test]
fn a_top_level_name_without_a_visibility_is_unknown_and_a_nested_one_is_public() {
    let list = symbols("function top() { function inner() {} }\n");
    let top = &named(&list, "top").data["visibility_detail"];
    assert_eq!(
        (top["kind"].as_str(), top["basis"].as_str()),
        (Some("unknown"), Some("unknown"))
    );
    let inner = &named(&list, "inner").data["visibility_detail"];
    assert_eq!(
        (inner["kind"].as_str(), inner["basis"].as_str()),
        (Some("public"), Some("language"))
    );
}

#[test]
fn a_base_name_that_several_classifiers_share_is_partially_resolved() {
    let list = symbols("interface K {}\nclass K {}\nclass D extends K {}\n");
    let bases = named(&list, "D").data["base_declarations"]
        .as_array()
        .unwrap()
        .clone();
    assert_eq!(bases[0]["status"], "partially_resolved");
    assert_eq!(bases[0]["candidate_count"], 2);
    assert_eq!(
        bases[0]["reason"],
        "multiple classifier definition sites share the target name"
    );
    assert_eq!(bases[0]["targets"].as_array().unwrap().len(), 1);
}
