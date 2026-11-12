// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The registered capability sets (AD-378, L-35a), each dimension one at a time.

use serde_json::{json, Value};

use crate::ingest;
use crate::validate::tests::{compressed, golden};

/// One change of a reply.
type Change = Box<dyn FnOnce(&mut Value)>;

const NOT_REGISTERED: &str = "source sections or resolution features are not registered";

fn error_after(change: impl FnOnce(&mut Value)) -> String {
    let mut value = golden("h-typescript");
    change(&mut value);
    ingest(&compressed(&value), 1 << 30)
        .err()
        .unwrap_or_default()
}

fn drop_section(value: &mut Value, name: &str) {
    let facts = &mut value["facts"];
    if let Some(sections) = facts["sections"].as_array_mut() {
        sections.retain(|section| section["name"] != name);
    }
    if let Some(names) = facts["capabilities"]["sections"].as_array_mut() {
        names.retain(|section| section != name);
    }
}

#[test]
fn the_frozen_reply_is_a_registered_set() {
    assert_eq!(error_after(|_| {}), "");
}

#[test]
fn each_typescript_dimension_outside_the_registry_is_refused() {
    let cases: Vec<Change> = vec![
        Box::new(|v| v["facts"]["capabilities"]["constructs"][0]["status"] = json!("unsupported")),
        Box::new(|v| v["facts"]["capabilities"]["constructs"] = json!([])),
        Box::new(|v| {
            if let Some(features) = v["facts"]["capabilities"]["resolution_features"].as_array_mut()
            {
                features.retain(|feature| feature != "literal-imports");
            }
        }),
        Box::new(|v| drop_section(v, "unknowns")),
        Box::new(|v| drop_section(v, "constructs")),
    ];
    for change in cases {
        assert_eq!(error_after(change), NOT_REGISTERED);
    }
    // Without the `constructs` section and its capability, the inner UML set is registered.
    let without = error_after(|v| {
        drop_section(v, "constructs");
        v["facts"]["capabilities"]["constructs"] = json!([]);
    });
    assert_ne!(without, NOT_REGISTERED);
}

#[test]
fn a_rust_section_set_outside_the_registry_is_refused() {
    let rust = |v: &mut Value| {
        v["facts"]["profile"] = json!("archkeel-rust-imports");
        v["facts"]["capabilities"]["resolution_features"] = json!(["rust-crate-edges"]);
        v["facts"]["capabilities"]["constructs"] = json!([]);
    };
    let wrong = "source sections do not match the registered profile";
    assert_eq!(error_after(rust), wrong);
    let registered = error_after(|v| {
        rust(v);
        for name in ["calls", "references", "bindings", "constructs"] {
            drop_section(v, name);
        }
    });
    assert_ne!(registered, wrong);
    let without_unknowns = error_after(|v| {
        rust(v);
        for name in ["calls", "references", "bindings", "constructs", "unknowns"] {
            drop_section(v, name);
        }
    });
    assert_eq!(without_unknowns, wrong);
}
