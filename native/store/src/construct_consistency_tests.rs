// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Cross-product of the public construct/signal vocabulary, before profile acceptance.

use archkeel_facts::envelope::Facts;
use archkeel_facts::vocab::Signal;
use serde_json::{json, Value};

use crate::validate::tests::golden;

const CONSTRUCTS: [(&str, &str); 11] = [
    ("string_literal_compare", "string_literal_compare"),
    ("broad_except", "broad_except"),
    ("getattr_call", "getattr"),
    ("hasattr_call", "hasattr"),
    ("setattr_call", "setattr"),
    ("delattr_call", "delattr"),
    ("vars_call", "vars"),
    ("assert_statement", "assert"),
    ("placeholder_body", "placeholder_body"),
    ("dunder_dict", "dunder_dict"),
    ("construct_selector", "selector"),
];
const PAYLOADS: [&str; 17] = [
    "getattr",
    "hasattr",
    "cast",
    "eval",
    "exec",
    "dynamic_import",
    "type_ignore",
    "any_annotation",
    "placeholder_body",
    "assert",
    "broad_except",
    "setattr",
    "delattr",
    "vars",
    "dunder_dict",
    "string_literal_compare",
    "selector",
];

fn section(kind: &str, name: &str, data: Value) -> Value {
    json!({"name": name, "records": [{"id": "RECORD-consistency", "evidence_class": "FACT",
        "area": if name == "typing_signals" { "type_architecture" } else { "constructs" },
        "kind": kind, "title": "consistency", "subjects": [], "evidence_ids": [],
        "fact_ids": [], "rule_ids": [], "provenance": [], "data": data}]})
}

fn validate(mut section: Value) -> Result<(), String> {
    let mut reply = golden("h-typescript");
    let module = reply["facts"]["files"][0]["module"].clone();
    if section["records"][0]["data"]["owner"] == "shop" {
        section["records"][0]["data"]["owner"] = module;
    }
    section["records"][0]["evidence_ids"] = json!([reply["facts"]["files"][0]["evidence_id"]]);
    let mut sections = reply["facts"]["sections"]
        .as_array()
        .ok_or("no sections")?
        .clone();
    sections.retain(|s| s["name"] != section["name"]);
    sections.push(section);
    reply["facts"]["sections"] = json!(sections);
    reply["facts"]["capabilities"]["constructs"] = json!(PAYLOADS
        .iter()
        .map(|name| json!({"name": name, "status": "supported"}))
        .collect::<Vec<_>>());
    let facts: Facts = serde_json::from_value(reply["facts"].clone()).map_err(|e| e.to_string())?;
    crate::records::records(&facts, &crate::validate::index(&facts)).map(|_| ())
}

fn construct_data(kind: &str, payload: &str) -> Value {
    let mut data = json!({"construct": payload, "owner": "shop"});
    if kind == "placeholder_body" {
        data["form"] = json!("empty");
    }
    if kind == "construct_selector" {
        data = json!({"construct": payload, "owner": "shop", "literal": null, "member": "x",
            "operation": "read", "receiver_binding": null, "receiver_parameter": null,
            "receiver_type": null, "selector_role": "read", "status": "unknown"});
    }
    data
}

#[test]
fn every_kind_payload_disagreement_is_refused_by_record_validation() {
    let mut failures = Vec::new();
    let mut pairs = 0;
    for kind in Signal::ALL {
        for payload in Signal::ALL.iter().filter(|payload| *payload != kind) {
            let data = json!({"owner": "shop", "signal": payload});
            let found = validate(section(kind.as_str(), "typing_signals", data));
            if found.as_ref().err().map(String::as_str)
                != Some("typing-signal kind disagrees with payload signal")
            {
                failures.push(format!("{kind:?}/{payload:?}: {found:?}"));
            }
            pairs += 1;
        }
    }
    for (kind, expected) in CONSTRUCTS {
        for payload in PAYLOADS.into_iter().filter(|payload| *payload != expected) {
            let found = validate(section(kind, "constructs", construct_data(kind, payload)));
            if found.as_ref().err().map(String::as_str)
                != Some("source construct kind disagrees with payload construct")
            {
                failures.push(format!("{kind}/{payload}: {found:?}"));
            }
            pairs += 1;
        }
    }
    assert_eq!(pairs, 308);
    assert!(
        failures.is_empty(),
        "{} disagreement pairs accepted or refused for another reason: {failures:?}",
        failures.len()
    );
}

#[test]
fn roles_forms_owners_and_areas_cannot_give_two_identities() {
    use archkeel_facts::vocab::{ConstructForm, Operation, SelectorRole};
    let mut pairs = 0;
    for role in SelectorRole::ALL {
        let expected = match role.as_str() {
            "read" => "read",
            "write" => "write",
            "call" => "call",
            "constructor" => "construct",
            "reflect" | "type_probe" => "probe",
            _ => "compare",
        };
        for operation in Operation::ALL.iter().filter(|o| o.as_str() != expected) {
            let mut data = construct_data("construct_selector", "selector");
            data["selector_role"] = json!(role);
            data["operation"] = json!(operation);
            assert_eq!(
                validate(section("construct_selector", "constructs", data)),
                Err("selector role disagrees with its operation".to_owned()),
                "{role:?}/{operation:?}"
            );
            pairs += 1;
        }
    }
    assert_eq!(pairs, 66);
    for (kind, construct) in CONSTRUCTS.into_iter().filter(|(k, _)| {
        matches!(
            *k,
            "broad_except"
                | "getattr_call"
                | "hasattr_call"
                | "setattr_call"
                | "delattr_call"
                | "vars_call"
        )
    }) {
        for form in ConstructForm::ALL {
            let mut data = construct_data(kind, construct);
            data["form"] = json!(form);
            assert_eq!(
                validate(section(kind, "constructs", data)),
                Err("access or exception record cannot have a comparison form".to_owned())
            );
        }
    }
    let mut comparison = construct_data("string_literal_compare", "string_literal_compare");
    comparison["form"] = json!("binary");
    assert_eq!(
        validate(section("string_literal_compare", "constructs", comparison)),
        Err("string comparison disagrees with its construct form".to_owned())
    );
    for (owner, name) in [
        ("shop", "shop.other.f"),
        (
            "shop.src.data.local_x2e_ts.f",
            "shop.src.data.local_x2e_ts.other",
        ),
    ] {
        let data = json!({"signal": "type_ignore", "owner": owner, "qualified_name": name});
        assert_eq!(
            validate(section("type_ignore", "typing_signals", data)),
            Err("typing-signal qualified name disagrees with its owner".to_owned())
        );
    }
    for (kind, name, data, reason) in [
        (
            "type_ignore",
            "typing_signals",
            json!({"owner": "shop", "signal": "type_ignore"}),
            "typing-signal area disagrees with its section",
        ),
        (
            "assert_statement",
            "constructs",
            construct_data("assert_statement", "assert"),
            "construct record area disagrees with its section",
        ),
    ] {
        let mut record = section(kind, name, data);
        record["records"][0]["area"] = json!("source");
        assert_eq!(validate(record), Err(reason.to_owned()));
    }
}

#[test]
fn agreeing_kinds_and_payloads_keep_the_existing_proof_refusals() {
    for kind in Signal::ALL {
        let data = json!({"owner": "shop", "signal": kind});
        assert_eq!(
            validate(section(kind.as_str(), "typing_signals", data)),
            Ok(())
        );
    }
    for (kind, construct) in CONSTRUCTS {
        let expected = if kind == "construct_selector" {
            Err("the store does not check construct_selector records yet".to_owned())
        } else {
            Ok(())
        };
        assert_eq!(
            validate(section(kind, "constructs", construct_data(kind, construct))),
            expected
        );
    }
    let data = json!({"signal": "type_ignore", "owner": "shop", "qualified_name": "shop.src.data.local_x2e_ts.f"});
    assert_eq!(
        validate(section("type_ignore", "typing_signals", data)),
        Ok(())
    );
}

#[test]
fn numeric_form_and_operation_still_need_the_numeric_proof() {
    use archkeel_facts::vocab::{ConstructForm, Operation};
    let mut pairs = 0;
    for form in ConstructForm::ALL {
        for operation in Operation::ALL {
            let data = json!({"owner": "shop", "module": "shop.src.data.local_x2e_ts", "binding_scopes": [],
                "column": 0, "line": 1, "end_line": 1, "end_column": 1, "derivation": [], "form": form,
                "operation": operation, "proof": "known", "subject": null, "value": 1});
            let valid = *form == ConstructForm::Binary && *operation == Operation::Modulo;
            let expected = if valid {
                "the store does not check numeric_operand records yet"
            } else {
                "numeric operand disagrees with its form or operation"
            };
            assert_eq!(
                validate(section("numeric_operand", "constructs", data)),
                Err(expected.to_owned())
            );
            pairs += usize::from(!valid);
        }
    }
    assert_eq!(pairs, 41);
}

#[test]
fn a_real_ingest_refuses_conflicting_construct_identity() {
    let mut reply = golden("h-typescript");
    let data = json!({"owner": reply["facts"]["files"][0]["module"], "construct": "assert"});
    let mut changed = section("string_literal_compare", "constructs", data);
    changed["records"][0]["evidence_ids"] = json!([reply["facts"]["files"][0]["evidence_id"]]);
    for section in reply["facts"]["sections"]
        .as_array_mut()
        .into_iter()
        .flatten()
    {
        if section["name"] == "constructs" {
            *section = changed.clone();
        }
    }
    let refused = crate::ingest_reply(&crate::validate::tests::compressed(&reply), 1 << 30).err();
    assert_eq!(
        refused.as_deref(),
        Some("source construct kind disagrees with payload construct")
    );
}

#[test]
fn every_frozen_construct_and_signal_has_consistent_identity(
) -> Result<(), Box<dyn std::error::Error>> {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/golden");
    frozen(&root)
}

fn frozen(path: &std::path::Path) -> Result<(), Box<dyn std::error::Error>> {
    use std::io::Read;
    for entry in std::fs::read_dir(path)? {
        let path = entry?.path();
        if path.is_dir() {
            frozen(&path)?;
            continue;
        }
        if !path.to_string_lossy().ends_with(".json.gz") {
            continue;
        }
        let mut text = String::new();
        flate2::read::GzDecoder::new(std::fs::File::open(&path)?).read_to_string(&mut text)?;
        let value: Value = serde_json::from_str(&text)?;
        frozen_sections(&value).map_err(|e| format!("{}: {e}", path.display()))?;
    }
    Ok(())
}

fn frozen_sections(reply: &Value) -> Result<(), Box<dyn std::error::Error>> {
    for section in reply["facts"]["sections"].as_array().into_iter().flatten() {
        if !matches!(
            section["name"].as_str(),
            Some("constructs" | "typing_signals" | "references")
        ) {
            continue;
        }
        let typed = serde_json::from_value::<archkeel_facts::Section>(section.clone())?;
        crate::record_identity::validate(&typed)?;
    }
    Ok(())
}

#[test]
fn access_kind_and_use_cannot_disagree_or_escape_their_source_module() {
    use archkeel_facts::vocab::Use;
    let module = "shop.src.data.local_x2e_ts";
    let mut pairs = 0;
    for (kind, usage) in [
        ("value_reference", Use::Value),
        ("attribute_reference", Use::Attribute),
        ("source_role", Use::SourceRole),
        ("script_namespace_effect", Use::Value),
    ] {
        let (area, wrong_area) = if kind == "script_namespace_effect" {
            ("source", "call_hierarchy")
        } else {
            ("call_hierarchy", "source")
        };
        for wrong in Use::ALL {
            let mut data = json!({"expression": "x", "source_module": module, "source_scope": module,
                "status": "unresolved", "targets": [], "use": wrong});
            if kind == "source_role" {
                let fields = json!({"canonical_name": "shop.x", "column": 0, "line": 1,
                    "end_line": 1, "end_column": 1, "declaration_id": "DECL-x", "declaration_owner_id": "OWNER-x",
                    "declaration_owner_scope": module, "role": "write"});
                data.as_object_mut()
                    .expect("object")
                    .extend(fields.as_object().expect("object").clone());
            }
            let mut record = section(kind, "references", data);
            record["records"][0]["area"] = json!(area);
            let reason = if *wrong == usage {
                record["records"][0]["area"] = json!(wrong_area);
                "access record area disagrees with its kind"
            } else {
                "access kind disagrees with payload use"
            };
            assert_eq!(validate(record), Err(reason.to_owned()), "{kind}/{wrong:?}");
            pairs += usize::from(*wrong != usage);
        }
    }
    assert_eq!(pairs, 24);
    let data = json!({"expression": "x", "source_module": module, "source_scope": "shop.other.f",
        "status": "unresolved", "targets": [], "use": "value"});
    let mut record = section("references", "references", data);
    record["records"][0]["area"] = json!("source");
    assert_eq!(
        validate(record),
        Err("source record source_scope disagrees with its module".to_owned())
    );
}

#[test]
fn a_subject_has_one_kind_and_one_qualified_name() -> Result<(), Box<dyn std::error::Error>> {
    use archkeel_facts::vocab::SymbolCategory;
    let reply = golden("h-typescript");
    let symbols = reply["facts"]["sections"]
        .as_array()
        .ok_or("no sections")?
        .iter()
        .find(|s| s["name"] == "symbols")
        .ok_or("no symbols")?["records"]
        .as_array()
        .ok_or("no records")?;
    let mut pairs = 0;
    for kind in ["class", "function", "method"] {
        let original = symbols
            .iter()
            .find(|r| r["kind"] == kind)
            .ok_or("no subject kind")?;
        for category in SymbolCategory::ALL.iter().filter(|c| c.as_str() != kind) {
            let mut record = original.clone();
            record["data"]["symbol_category"] = json!(category);
            let section = serde_json::from_value::<archkeel_facts::Section>(
                json!({"name": "symbols", "records": [record]}),
            )?;
            assert_eq!(
                crate::record_identity::validate(&section),
                Err("subject kind disagrees with payload symbol category".to_owned())
            );
            pairs += 1;
        }
        let mut record = original.clone();
        record["data"]["name"] = json!("different");
        let section = serde_json::from_value::<archkeel_facts::Section>(
            json!({"name": "symbols", "records": [record]}),
        )?;
        assert_eq!(
            crate::record_identity::validate(&section),
            Err("subject name disagrees with its qualified name".to_owned())
        );
    }
    assert_eq!(pairs, 18);
    Ok(())
}
