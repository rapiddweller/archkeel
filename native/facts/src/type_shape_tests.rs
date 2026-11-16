// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: AD-550. The tree is closed and has one JSON form.

use serde_json::json;

use super::{Binding, Family, TypeShape, Unproven};

fn name(text: &str) -> TypeShape {
    TypeShape::Primitive {
        text: text.to_owned(),
        name: text.to_owned(),
    }
}

#[test]
fn a_nested_tree_round_trips_through_its_json_form() {
    let shape = TypeShape::Collection {
        text: "tuple[int | None, ...]".to_owned(),
        family: Family::Sequence,
        name: "tuple".to_owned(),
        args: vec![TypeShape::Union {
            text: "int | None".to_owned(),
            arms: vec![name("int"), TypeShape::Nothing {}],
        }],
        open_end: true,
    };
    let text = serde_json::to_value(&shape).expect("a tree is JSON");
    assert_eq!(text["shape"], "collection");
    assert_eq!(text["args"][0]["arms"][1], json!({"shape": "nothing"}));
    let back: TypeShape = serde_json::from_value(text).expect("the tree reads back");
    assert_eq!(back, shape);
}

#[test]
fn a_binding_names_its_target_or_the_cause_that_stopped_the_proof() {
    let proven = TypeShape::Named {
        text: "A".to_owned(),
        binding: Binding::Imported {
            target: "app.m.A".to_owned(),
        },
    };
    let value = serde_json::to_value(&proven).expect("a tree is JSON");
    assert_eq!(
        value["binding"],
        json!({"binding": "imported", "target": "app.m.A"})
    );
    let open = Binding::Unproven {
        cause: Unproven::StarImport,
    };
    assert_eq!(
        serde_json::to_value(open).expect("a binding is JSON"),
        json!({"binding": "unproven", "cause": "star_import"})
    );
}

#[test]
fn a_form_or_a_cause_outside_the_vocabulary_is_an_error() {
    assert!(serde_json::from_value::<TypeShape>(json!({"shape": "callable"})).is_err());
    assert!(
        serde_json::from_value::<TypeShape>(json!({"shape": "nothing", "extra": 1})).is_err(),
        "an unknown key is an error"
    );
    assert!(
        serde_json::from_value::<Binding>(json!({"binding": "unproven", "cause": "because"}))
            .is_err()
    );
}
