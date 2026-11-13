// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Every construct and signal of every frozen collector reply must decode by its original kind.

use std::collections::BTreeSet;
use std::io::Read;
use std::path::Path;

use serde_json::{json, Value};

fn visit(path: &Path, seen: &mut BTreeSet<String>) -> Result<(), Box<dyn std::error::Error>> {
    for entry in std::fs::read_dir(path)? {
        let path = entry?.path();
        if path.is_dir() {
            visit(&path, seen)?;
        } else if path.to_string_lossy().ends_with(".json.gz") {
            reply(&path, seen)?;
        }
    }
    Ok(())
}

fn reply(path: &Path, seen: &mut BTreeSet<String>) -> Result<(), Box<dyn std::error::Error>> {
    let mut text = String::new();
    flate2::read::GzDecoder::new(std::fs::File::open(path)?).read_to_string(&mut text)?;
    let value: Value = serde_json::from_str(&text)?;
    for section in value["facts"]["sections"].as_array().into_iter().flatten() {
        let name = section["name"].as_str().ok_or("section without name")?;
        if !matches!(name, "constructs" | "typing_signals") {
            continue;
        }
        for record in section["records"].as_array().into_iter().flatten() {
            let kind = record["kind"].as_str().ok_or("record without kind")?;
            seen.insert(format!("{name}/{kind}"));
            let single = json!({"name": name, "records": [record]});
            if let Err(error) = serde_json::from_value::<crate::Section>(single) {
                return Err(format!("{}: {name}/{kind}: {error}", path.display()).into());
            }
        }
    }
    Ok(())
}

#[test]
fn every_frozen_construct_and_signal_kind_decodes() -> Result<(), Box<dyn std::error::Error>> {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/golden");
    let mut seen = BTreeSet::new();
    visit(&root, &mut seen)?;
    for kind in [
        "assert_statement",
        "placeholder_body",
        "dunder_dict",
        "construct_selector",
    ] {
        assert!(
            seen.contains(&format!("constructs/{kind}")),
            "missing golden {kind}"
        );
    }
    println!("decoded kinds: {seen:?}");
    Ok(())
}

#[test]
fn corrected_constructs_reject_missing_and_unknown_fields() {
    for kind in ["assert_statement", "placeholder_body", "dunder_dict"] {
        let mut data = json!({"construct": "assert", "owner": "app.f"});
        if kind == "placeholder_body" {
            data["form"] = json!("empty");
        }
        let record = json!({"id": "CONSTRUCT-x", "evidence_class": "FACT", "area": "constructs",
            "kind": kind, "title": "x", "subjects": [], "evidence_ids": [], "fact_ids": [],
            "rule_ids": [], "provenance": [], "data": data});
        let section = json!({"name": "constructs", "records": [record]});
        assert!(serde_json::from_value::<crate::Section>(section.clone()).is_ok());
        for key in data.as_object().into_iter().flat_map(|o| o.keys()) {
            let mut missing = section.clone();
            if let Some(object) = missing["records"][0]["data"].as_object_mut() {
                object.remove(key);
            }
            assert!(
                serde_json::from_value::<crate::Section>(missing).is_err(),
                "{kind}/{key}"
            );
        }
        let mut unknown = section;
        unknown["records"][0]["data"]["extra"] = json!(true);
        assert!(
            serde_json::from_value::<crate::Section>(unknown).is_err(),
            "{kind}/extra"
        );
    }
}

#[test]
fn a_section_cannot_decode_a_kind_from_the_other_construct_family() {
    use crate::vocab::Signal;
    for signal in Signal::ALL
        .iter()
        .filter(|s| !matches!(s.as_str(), "getattr_call" | "hasattr_call"))
    {
        let value = json!({"name": "constructs", "records": [{"id": "FACT-x", "evidence_class": "FACT",
            "area": "constructs", "kind": signal.as_str(), "title": "x", "subjects": [], "evidence_ids": [],
            "rule_ids": [], "fact_ids": [], "provenance": [], "data": {"owner": "app", "signal": signal}}]});
        let error = serde_json::from_value::<crate::Section>(value)
            .expect_err("kind is outside the section");
        assert!(
            error.to_string().contains("not a kind of ConstructFact"),
            "{signal:?}: {error}"
        );
    }
    for kind in [
        "string_literal_compare",
        "broad_except",
        "setattr_call",
        "delattr_call",
        "vars_call",
        "construct_selector",
        "numeric_operand",
        "assert_statement",
        "placeholder_body",
        "dunder_dict",
    ] {
        let value = json!({"name": "typing_signals", "records": [{"id": "FACT-x", "evidence_class": "FACT",
            "area": "type_architecture", "kind": kind, "title": "x", "subjects": [], "evidence_ids": [],
            "rule_ids": [], "fact_ids": [], "provenance": [], "data": {"owner": "app", "construct": "assert"}}]});
        let error = serde_json::from_value::<crate::Section>(value)
            .expect_err("kind is outside the section");
        assert!(
            error.to_string().contains("not a kind of SignalFact"),
            "{kind}: {error}"
        );
    }
    for kind in ["getattr_call", "hasattr_call"] {
        for (name, data) in [
            ("constructs", json!({"owner": "app", "signal": kind})),
            (
                "typing_signals",
                json!({"owner": "app", "construct": "getattr"}),
            ),
        ] {
            let value = json!({"name": name, "records": [{"id": "FACT-x", "evidence_class": "FACT",
                "area": "constructs", "kind": kind, "title": "x", "subjects": [], "evidence_ids": [],
                "rule_ids": [], "fact_ids": [], "provenance": [], "data": data}]});
            assert!(
                serde_json::from_value::<crate::Section>(value).is_err(),
                "{name}/{kind}"
            );
        }
    }
}
