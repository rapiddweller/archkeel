// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The validation of `ingest` on the frozen H-typescript reply (AD-343) and changed copies of it.
//! Each changed copy must fail with the message of the Python check that it ports.

use std::io::{Read, Write};

use flate2::read::GzDecoder;
use flate2::write::ZlibEncoder;
use flate2::Compression;
use serde_json::{json, Value};

use crate::ingest;

const LIMIT: u64 = 1 << 30;

fn reply() -> Value {
    golden("h-typescript")
}

/// The frozen reply of a TypeScript golden case, with the provenance of a run.
pub(crate) fn golden(case: &str) -> Value {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join(format!("../../tests/golden/typescript/{case}.json.gz"));
    let mut text = String::new();
    let file = std::fs::File::open(path).ok();
    if let Some(file) = file {
        let _ = GzDecoder::new(file).read_to_string(&mut text);
    }
    let mut value: Value = serde_json::from_str(&text).unwrap_or(Value::Null);
    // The golden form drops the provenance of the run (`tests/golden_replies.py`); put it back.
    value["facts"]["adapter"]["version"] = json!("0");
    value["facts"]["adapter"]["code_digest"] = json!("0".repeat(64));
    value["facts"]["runtime"] = json!({"name": "rust", "version": "1.88.0", "required": null,
                                       "requirement_state": "declared"});
    value["facts"]["source"]["git_head"] = json!("a");
    value["facts"]["source"]["dirty"] = json!(false);
    value["facts"]["provider_bindings"] = json!([]);
    value["protocol_version"] = json!("9.0.0");
    value["provider_sources"] = json!([]);
    value
}

pub(crate) fn compressed(value: &Value) -> Vec<u8> {
    let mut encoder = ZlibEncoder::new(Vec::new(), Compression::fast());
    let _ = encoder.write_all(value.to_string().as_bytes());
    encoder.finish().unwrap_or_default()
}

fn error_of(value: &Value) -> String {
    ingest(&compressed(value), LIMIT).err().unwrap_or_default()
}

fn section(value: &mut Value, name: &str) -> Option<usize> {
    value["facts"]["sections"]
        .as_array()?
        .iter()
        .position(|section| section["name"] == name)
}

/// The records of one section; a missing section gives an empty list, and the case then fails.
fn records<'a>(value: &'a mut Value, name: &str) -> &'a mut Value {
    let index = section(value, name).unwrap_or(usize::MAX);
    &mut value["facts"]["sections"][index]["records"]
}

#[test]
fn the_frozen_reply_passes_and_gives_the_read_set() -> Result<(), String> {
    let store = ingest(&compressed(&reply()), LIMIT)?;
    let mut frame = Vec::new();
    crate::seam::write_frame(store.reply(), &mut frame)?;
    let length = u64::from_be_bytes(frame[1..9].try_into().map_err(|_| "no header")?);
    assert_eq!(
        frame.len() as u64,
        9 + length,
        "the header counts the document"
    );
    let read: Value = serde_json::from_slice(&frame[9..]).map_err(|e| e.to_string())?;
    let imports = &read["facts"]["sections"][0]["records"][0];
    assert!(
        imports["data"].get("specifier").is_none(),
        "specifier is not read"
    );
    assert!(
        imports.get("title").is_none(),
        "a record of a measured section has no title"
    );
    let unknowns = read["facts"]["sections"].as_array().and_then(|sections| {
        sections
            .iter()
            .find(|section| section["name"] == "unknowns")
    });
    assert!(
        unknowns.is_some(),
        "the unknowns section is in the document"
    );
    let id = imports["id"].as_str().unwrap_or_default();
    assert!(store.saved(id).is_ok());
    Ok(())
}

#[test]
fn a_changed_reply_fails_with_the_message_of_the_python_check() {
    type Change = fn(&mut Value);
    let cases: [(&str, Change); 11] = [
        ("duplicate source record id", |v| {
            let first = records(v, "imports")[0].clone();
            if let Some(list) = records(v, "imports").as_array_mut() {
                list.push(first);
            }
        }),
        ("evidence path escapes source snapshot", |v| {
            v["facts"]["evidence"][0]["file"] = json!("../outside/ghost.ts");
        }),
        ("source record evidence disagrees with its module", |v| {
            records(v, "imports")[0]["evidence_ids"] = json!([]);
        }),
        ("each parsed source file needs an observed module", |v| {
            if let Some(files) = v["facts"]["files"].as_array_mut() {
                files.pop();
            }
        }),
        ("each import needs exactly one typed target", |v| {
            if let Some(targets) = v["facts"]["imports"].as_array_mut() {
                targets.pop();
            }
        }),
        ("source sections disagree with declared capabilities", |v| {
            if let Some(names) = v["facts"]["capabilities"]["sections"].as_array_mut() {
                names.push(json!("typing_signals"));
            }
        }),
        (
            "does not check the resolution feature call-bindings-v1",
            |v| {
                if let Some(features) =
                    v["facts"]["capabilities"]["resolution_features"].as_array_mut()
                {
                    features.push(json!("call-bindings-v1"));
                }
            },
        ),
        ("does not check archkeel-python-analyzer replies", |v| {
            v["facts"]["profile"] = json!("archkeel-python-analyzer");
        }),
        ("does not check archkeel-dart-analyzer replies", |v| {
            v["facts"]["profile"] = json!("archkeel-dart-analyzer");
        }),
        // A Rust reply may claim only the feature of the Rust collector.
        (
            "does not check the resolution feature literal-imports",
            |v| {
                v["facts"]["profile"] = json!("archkeel-rust-imports");
            },
        ),
        ("dangling source evidence reference", |v| {
            records(v, "symbols")[0]["evidence_ids"] = json!(["EVD-missing"]);
        }),
    ];
    for (message, change) in cases {
        let mut value = reply();
        change(&mut value);
        let error = error_of(&value);
        assert!(error.contains(message), "{message}: {error}");
    }
}

#[test]
fn the_store_reads_only_a_complete_compressed_reply() {
    let plain = reply().to_string().into_bytes();
    let error = ingest(&plain, LIMIT).err().unwrap_or_default();
    assert!(error.contains("only the compressed replies"), "{error}");
    let mut trailing = compressed(&reply());
    trailing.push(b' ');
    let error = ingest(&trailing, LIMIT).err().unwrap_or_default();
    assert!(error.contains("trailing data"), "{error}");
    let error = ingest(&compressed(&reply()), 100).err().unwrap_or_default();
    assert!(error.contains("exceeds its 100 byte limit"), "{error}");
}

#[test]
fn a_reply_of_protocol_10_is_refused_until_a_native_python_reply_can_pass() {
    let mut value = reply();
    value["protocol_version"] = json!("10.0.0");
    let error = error_of(&value);
    assert_eq!(
        error,
        "the store does not read protocol 10.0.0 replies yet (AD-334)"
    );
}
