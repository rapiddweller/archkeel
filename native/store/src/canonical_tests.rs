// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `testdata/canonical-expected.json` is `canonical_report_bytes` of Python for the model of
//! `testdata/canonical-parts.json`, cut from the H-typescript observation. The model holds a
//! repeated long text, the spellings of a reference, a float and a missing data cell.

use std::collections::HashMap;

use archkeel_facts::envelope::Reply;
use serde_json::{json, Value};

use super::{encode, escaped, profitable};
use crate::stored::Store;

fn testdata(name: &str) -> Vec<u8> {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("testdata")
        .join(name);
    std::fs::read(path).unwrap_or_default()
}

/// A typed reply that holds one import record (in wire form) and one evidence entry.
fn store(record: &Value, evidence: &Value) -> Result<Store, String> {
    let mut wire = record.clone();
    wire["data"]["module_level_import"] = json!(true);
    let id = record["id"].as_str().unwrap_or_default().to_owned();
    let reply = json!({
        "protocol_version": "9.0.0", "provider_sources": [],
        "facts": {
            "profile": "archkeel-typescript-imports",
            "adapter": {"name": "a", "version": "0", "code_digest": "0"},
            "runtime": {"name": "rust", "version": "1", "required": null,
                        "requirement_state": "declared"},
            "source": {"git_head": "a", "dirty": false, "source_digest": "0", "scope": []},
            "capabilities": {"sections": ["imports"], "resolution_features": [], "constructs": []},
            "inputs": [], "files": [],
            "imports": [{"kind": "local", "import_id": id, "module": "m", "file": "f",
                         "runtime_file": null, "declaration_file": null}],
            "sections": [{"name": "imports", "records": [wire]}],
            "coverage": {"selected_files": [], "files_read": 0, "files_parsed": 0,
                         "full_scope": true, "gaps": []},
            "evidence": [evidence], "uncertain_reexports": [], "type_shapes": [],
            "state": {"classes": [], "functions": []}, "candidate_evidence": [],
            "provider_bindings": []
        }
    });
    let reply: Reply = serde_json::from_value(reply).map_err(|e| e.to_string())?;
    Ok(Store::new(reply, HashMap::from([(id, (0, 0))])))
}

#[test]
fn the_store_writes_the_bytes_of_the_python_writer() -> Result<(), String> {
    let parts: Value =
        serde_json::from_slice(&testdata("canonical-parts.json")).map_err(|e| e.to_string())?;
    let store = store(&parts["record"], &parts["evidence"])?;
    let Value::Object(model) = parts["model"].clone() else {
        return Err("no model".to_owned());
    };
    let written = encode(model, &store)?;
    assert!(written == testdata("canonical-expected.json"));
    Ok(())
}

#[test]
fn an_id_that_the_store_does_not_hold_is_an_error() -> Result<(), String> {
    let parts: Value =
        serde_json::from_slice(&testdata("canonical-parts.json")).map_err(|e| e.to_string())?;
    let store = store(&parts["record"], &parts["evidence"])?;
    let mut model = serde_json::Map::new();
    for name in super::CLASSIFIED_SECTIONS {
        model.insert(name.to_owned(), Value::Null);
    }
    model.insert("imports".to_owned(), Value::from(vec!["IMP-unknown"]));
    let error = encode(model, &store).err().unwrap_or_default();
    assert!(error.contains("holds no record IMP-unknown"), "{error}");
    Ok(())
}

#[test]
fn a_text_enters_the_table_by_the_observation_policy() {
    let long = "a repeated text that is long enough";
    // 35 code points: 5 copies save exactly 100 bytes, which is not more than 100.
    assert!(!profitable(long, 5));
    assert!(profitable(long, 6));
    assert!(!profitable(long, 1));
    assert!(!profitable("short", 1000));
    assert!(profitable("$$m", 1));
    for (text, reserved) in [
        ("$m", true),
        ("$$m", true),
        ("$7", true),
        ("$$12", true),
        ("$$$3", true),
        ("$", false),
        ("$x", false),
        ("plain $1", false),
    ] {
        assert_eq!(escaped(text), reserved, "{text}");
    }
}
