// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `testdata/canonical-expected.json` is `canonical_report_bytes` of Python for the model of
//! `testdata/canonical-parts.json`, cut from the H-typescript observation. The model holds a
//! repeated long text, the spellings of a reference, a float and a missing data cell.

use std::collections::HashMap;

use archkeel_facts::envelope::Reply;
use serde_json::{json, Value};

use super::encode;
use crate::shell::tests::framed;
use crate::stored::Store;
use crate::texts::{escaped, profitable};

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
    let (empty, plain) = framed(json!({"texts": [], "fields": {}, "model": model.clone()}));
    let written = encode(plain, &empty, &store)?;
    assert!(written == testdata("canonical-expected.json"));
    // The same shell records as compact rows (`shell.rs`) give the same bytes.
    let (shell, rows) = framed(crate::shell::tests::as_rows(model));
    assert!(encode(rows, &shell, &store)? == written);
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
    let (empty, model) = framed(json!({"texts": [], "fields": {}, "model": model}));
    let error = encode(model, &empty, &store).err().unwrap_or_default();
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

/// A shell record of `metrics` with the data `data`.
fn shell_record(data: Value) -> Value {
    json!({"id": "METRIC-1", "evidence_class": "FACT", "area": "a", "kind": "k", "title": "t",
           "subjects": [], "evidence_ids": [], "rule_ids": [], "fact_ids": [],
           "provenance": [], "data": data})
}

/// The written observation of a model whose sections are null, with the values of `more`.
fn written(more: Value) -> Result<Value, String> {
    let parts: Value =
        serde_json::from_slice(&testdata("canonical-parts.json")).map_err(|e| e.to_string())?;
    let store = store(&parts["record"], &parts["evidence"])?;
    let mut model = serde_json::Map::new();
    for name in super::CLASSIFIED_SECTIONS {
        model.insert(name.to_owned(), Value::Null);
    }
    if let Value::Object(more) = more {
        model.extend(more);
    }
    let (empty, model) = framed(json!({"texts": [], "fields": {}, "model": model}));
    let bytes = encode(model, &empty, &store)?;
    serde_json::from_slice(&bytes).map_err(|e| e.to_string())
}

/// `observation_profitable` keeps `$$m` at one occurrence, so the hash gate must not drop it.
#[test]
fn the_missing_marker_text_enters_the_table_when_it_occurs_once() -> Result<(), String> {
    let got = written(json!({"metrics": [shell_record(json!({"q": "$$m"}))]}))?;
    assert_eq!(got["string_table"], json!(["$$m"]));
    assert_eq!(got["metrics"][0][10], json!(["$0"]));
    let evidence = json!({"id": "E-1", "file": "$$m", "line": 1, "end_line": 1, "column": 0,
                          "excerpt": "x"});
    let got = written(json!({"evidence": [evidence]}))?;
    assert_eq!(got["string_table"], json!(["$$m"]));
    assert_eq!(got["evidence"][0][1], json!("$0"));
    Ok(())
}

/// The `\d` of Python `re` matches every decimal digit of Unicode, not only ASCII digits.
#[test]
fn a_reference_with_a_unicode_digit_is_escaped() -> Result<(), String> {
    for (text, reserved) in [
        ("$\u{663}", true),
        ("$$\u{967}\u{968}", true),
        ("$\u{ff11}", true),
        ("$\u{1d7ce}", true),
        ("$\u{b2}", false),
        ("$\u{2167}", false),
    ] {
        assert_eq!(escaped(text), reserved, "{text}");
    }
    // Unicode 14.0 has 660 decimal digits (`$m` is the marker); each one is numeric.
    let digits: Vec<char> = (0..=0x10ffff_u32)
        .filter_map(char::from_u32)
        .filter(|digit| *digit != 'm' && escaped(&format!("${digit}")))
        .collect();
    assert_eq!(digits.len(), 660);
    assert!(digits.iter().all(|digit| digit.is_numeric()));
    let got = written(json!({"metrics": [shell_record(json!({"q": "$\u{663}"}))]}))?;
    assert_eq!(got["metrics"][0][10], json!(["$$\u{663}"]));
    Ok(())
}

#[test]
fn a_coverage_that_is_not_an_object_is_an_error() {
    let error = written(json!({"coverage": 5})).err().unwrap_or_default();
    assert!(error.contains("coverage must be an object"), "{error}");
}
