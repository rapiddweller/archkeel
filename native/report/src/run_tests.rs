// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The model fixtures used by the live ruling tests.

use std::io::{Read, Write};

use archkeel_contract::{Contract, ParsedContract};
use archkeel_model::{Graph, ModelTree, Producer, Settings};
use flate2::read::GzDecoder;
use flate2::write::ZlibEncoder;
use flate2::Compression;
use serde_json::{json, Value};

const ROOT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");

pub(crate) fn read_json(path: &str) -> Value {
    let mut text = String::new();
    let full = format!("{ROOT}/{path}");
    if path.ends_with(".gz") {
        if let Ok(file) = std::fs::File::open(&full) {
            let _ = GzDecoder::new(file).read_to_string(&mut text);
        }
    } else {
        text = std::fs::read_to_string(&full).unwrap_or_default();
    }
    serde_json::from_str(&text).unwrap_or(Value::Null)
}

/// The H-typescript contract with only the rules `keep`.
pub(crate) fn contract(keep: &[&str]) -> Contract {
    parsed(keep, Vec::new()).unwrap()
}

/// The H-typescript contract with only the rules `keep`, then the rules `extra`.
pub(crate) fn parsed(keep: &[&str], extra: Vec<Value>) -> Option<Contract> {
    let mut value = read_json("fixtures/H-typescript/architecture-contract.json");
    let rules: Vec<Value> = value["rules"]
        .as_array()
        .map(|rules| {
            let kept = rules
                .iter()
                .filter(|r| keep.iter().any(|id| r["id"] == *id));
            kept.cloned().chain(extra).collect()
        })
        .unwrap_or_default();
    value["rules"] = json!(rules);
    match archkeel_contract::parse(value.to_string().as_bytes()) {
        Ok(ParsedContract::Complete(contract)) => Some(contract),
        _ => None,
    }
}

/// The H-typescript reply as the store accepts it.
pub(crate) fn reply() -> archkeel_store::Ingested {
    reply_with(|_| {})
}

/// The H-typescript reply after `change`.
pub(crate) fn reply_with(change: impl FnOnce(&mut Value)) -> archkeel_store::Ingested {
    let mut value = read_json("tests/golden/typescript/h-typescript.json.gz");
    value["facts"]["adapter"]["version"] = json!("0");
    value["facts"]["adapter"]["code_digest"] = json!("0".repeat(64));
    value["facts"]["runtime"] = json!({"name": "rust", "version": "1.88.0", "required": ">=1.88",
                                       "requirement_state": "declared"});
    value["facts"]["source"]["git_head"] = json!("a");
    value["facts"]["source"]["dirty"] = json!(false);
    value["facts"]["provider_bindings"] = json!([]);
    value["protocol_version"] = json!("11.0.0");
    // The golden form drops the validation table of the collector (AD-688); put it back.
    value["facts"]["validation"] = serde_json::from_str(include_str!(
        "../../../tests/golden/typescript/validation.json"
    ))
    .unwrap_or_default();
    value["provider_sources"] = json!([]);
    change(&mut value);
    let mut encoder = ZlibEncoder::new(Vec::new(), Compression::fast());
    encoder.write_all(value.to_string().as_bytes()).unwrap();
    archkeel_store::ingest_reply(&encoder.finish().unwrap(), 1 << 30).unwrap()
}

/// A model of the contract; `trusted` false gives the cause `Producer`, an incomplete scope.
pub(crate) fn model(contract: &Contract, trusted: bool) -> ModelTree {
    model_of(contract, &reply(), trusted)
}

pub(crate) fn model_of(
    contract: &Contract,
    reply: &archkeel_store::Ingested,
    trusted: bool,
) -> ModelTree {
    let profile = reply.reply().facts.profile.as_str().to_owned();
    let settings = Settings::new("shop".to_owned(), profile, Vec::new());
    let settings = if trusted {
        settings.with_producer(Producer::Trusted)
    } else {
        settings
    };
    ModelTree::of(contract, Graph::derive(reply, settings).unwrap()).unwrap()
}

/// Point the first import of `shop.src.domain` at the undeclared package `transport.client`
/// (the `retarget` of `eval/src/external_tests.rs`).
pub(crate) fn undeclared_import(value: &mut Value) {
    let id = value["facts"]["imports"][3]["import_id"].clone();
    value["facts"]["imports"][3] =
        json!({"kind": "external", "package": "transport.client", "import_id": id.clone()});
    let Some(sections) = value["facts"]["sections"].as_array_mut() else {
        return;
    };
    for section in sections.iter_mut().filter(|s| s["name"] == "imports") {
        let Some(records) = section["records"].as_array_mut() else {
            continue;
        };
        for record in records.iter_mut().filter(|r| r["id"] == id) {
            record["data"]["target_module"] = json!("vendor.entry");
            record["data"]["target_package"] = json!("transport.client");
            let source = record["data"]["source_module"]
                .as_str()
                .unwrap_or("")
                .to_owned();
            let mut subjects = vec![source, "vendor.entry".to_owned()];
            subjects.sort();
            record["subjects"] = json!(subjects);
        }
    }
}

pub(crate) fn allow() -> Value {
    json!({"id": "ALLOW", "kind": "allowed_dependency", "source": "shop.src.data",
        "target": "shop.src.domain", "rationale": "data reads the domain values",
        "provenance": ["docs/architecture/shop.md"], "decided_by": "architect"})
}
