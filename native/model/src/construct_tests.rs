// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Test-only recorded-fact entry. It cannot be reached from the binary or a dependent crate.

use std::io::Read;

use archkeel_contract::{Contract, ParsedContract, Rule};
use archkeel_facts::envelope::{Facts, Profile};
use serde_json::{json, Value};

use crate::{Decision, Graph, Model, Producer, Settings, Verdict};

const ROOT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");
const OWNER: &str = "shop.src.data.local_x2e_ts";

fn read(path: &str) -> Result<Value, Box<dyn std::error::Error>> {
    let mut text = String::new();
    flate2::read::GzDecoder::new(std::fs::File::open(format!("{ROOT}/{path}"))?)
        .read_to_string(&mut text)?;
    Ok(serde_json::from_str(&text)?)
}

fn model(
    options: Value,
    change: impl FnOnce(&mut Value),
) -> Result<Model, Box<dyn std::error::Error>> {
    let mut contract: Value = serde_json::from_str(include_str!(
        "../../../fixtures/H-typescript/architecture-contract.json"
    ))?;
    contract["schema_version"] = json!("3.14.0");
    contract["declarations"] = json!({});
    contract["rules"] = json!([{"id": "CONSTRUCT", "kind": "forbidden_construct", "source": "shop",
        "constructs": ["assert"], "rationale": "r", "provenance": ["p"], "decided_by": "architect"}]);
    for (key, value) in options.as_object().ok_or("no options")? {
        contract["rules"][0][key] = value.clone();
    }
    let contract = match archkeel_contract::parse(contract.to_string().as_bytes())? {
        ParsedContract::Complete(c) => c,
        _ => return Err("partial contract".into()),
    };
    let mut reply = read("tests/golden/typescript/h-typescript.json.gz")?;
    reply["facts"]["adapter"]["version"] = json!("0");
    reply["facts"]["adapter"]["code_digest"] = json!("0".repeat(64));
    reply["facts"]["runtime"] = json!({"name": "rust", "version": "1.97.0", "required": ">=1.97", "requirement_state": "declared"});
    reply["facts"]["source"]["git_head"] = json!("a");
    reply["facts"]["source"]["dirty"] = json!(false);
    reply["facts"]["provider_bindings"] = json!([]);
    reply["facts"]["capabilities"]["constructs"] =
        json!([{"name": "assert", "status": "supported"}]);
    change(&mut reply);
    let facts: Facts = serde_json::from_value(reply["facts"].clone())?;
    of(&contract, &facts)
}

fn of(contract: &Contract, facts: &Facts) -> Result<Model, Box<dyn std::error::Error>> {
    let settings = Settings::new("shop".to_owned(), facts.profile.as_str().to_owned(), vec![])
        .with_producer(Producer::Trusted);
    let graph = Graph::recorded(facts, settings).map_err(|r| r.to_string())?;
    Model::of(contract, graph).map_err(|r| r.1.to_string().into())
}

fn decide(model: &Model) -> Result<Decision, String> {
    let rule = model.contract().rules().first().ok_or("no rule")?;
    let Rule::ForbiddenConstruct(construct) = rule else {
        return Err("wrong rule".to_owned());
    };
    let matched = crate::construct_matches(model, construct).map_err(|r| r.to_string())?;
    if matched.iter().any(|m| m.known) {
        return Ok(Decision::fail());
    }
    Ok(model.scope(|scope| match scope.complete(rule) {
        Ok(proof) => scope.pass(proof),
        Err(reason) => Decision::unknown(reason),
    }))
}

fn record(reply: &mut Value, kind: &str, data: Value) {
    let evidence = reply["facts"]["files"][0]["evidence_id"].clone();
    let entry = json!({"id": "CONSTRUCT-site", "evidence_class": "FACT", "area": "constructs",
        "kind": kind, "title": "original", "subjects": [OWNER], "evidence_ids": [evidence],
        "fact_ids": [], "rule_ids": [], "provenance": [], "data": data});
    for section in reply["facts"]["sections"]
        .as_array_mut()
        .into_iter()
        .flatten()
    {
        if section["name"] == "constructs" {
            section["records"] = json!([entry.clone()]);
        }
    }
}

#[test]
fn complete_absence_passes_only_through_the_scope_proof() -> Result<(), Box<dyn std::error::Error>>
{
    let model = model(json!({}), |_| {})?;
    assert!(matches!(decide(&model)?.verdict(), Verdict::Pass(_)));
    let missing = self::model(json!({"source": "absent"}), |_| {})?;
    let decision = decide(&missing)?;
    assert!(matches!(decision.verdict(), Verdict::Unknown));
    assert!(decision
        .reason()
        .is_some_and(|r| r.to_string().contains("selects no module")));
    Ok(())
}

#[test]
fn a_signal_payload_cannot_change_the_record_kind_or_borrow_its_allowance(
) -> Result<(), Box<dyn std::error::Error>> {
    let allowance =
        json!({"qualified_name": OWNER, "line": 17, "statement": "x = call()", "tag": "arg-type"});
    for (kind, signal, construct) in [
        ("type_ignore", "cast_call", "type_ignore"),
        ("cast_call", "type_ignore", "cast"),
    ] {
        let model = model(
            json!({"constructs": [construct], "allowed_type_ignores": [allowance]}),
            |v| {
                v["facts"]["capabilities"]["constructs"] =
                    json!([{"name": construct, "status": "decided"}]);
                let evidence = v["facts"]["files"][0]["evidence_id"].clone();
                let mut data = if kind == "cast_call" {
                    allowance.clone()
                } else {
                    json!({})
                };
                data["signal"] = json!(signal);
                data["owner"] = json!(OWNER);
                let record = json!({"id": "SIGNAL-mismatch", "evidence_class": "FACT", "area": "type_architecture",
                "kind": kind, "title": "mismatched signal", "subjects": [OWNER], "evidence_ids": [evidence],
                "fact_ids": [], "rule_ids": [], "provenance": [], "data": data});
                if let Some(sections) = v["facts"]["sections"].as_array_mut() {
                    sections.push(json!({"name": "typing_signals", "records": [record]}));
                }
            },
        )?;
        let decision = decide(&model)?;
        assert!(
            matches!(decision.verdict(), Verdict::Fail),
            "{kind}/{signal}: {decision:?}"
        );
    }
    Ok(())
}

#[test]
fn exact_and_prefix_exemptions_have_pass_fail_and_unknown_cases(
) -> Result<(), Box<dyn std::error::Error>> {
    for key in ["allowed_sources", "exact_sources"] {
        for (exemption, pass) in [
            (OWNER.to_owned(), true),
            (format!("{OWNER}.neighbor"), false),
        ] {
            let model = model(json!({key: [exemption]}), |v| {
                record(
                    v,
                    "assert_statement",
                    json!({"owner": OWNER, "construct": "assert"}),
                );
            })?;
            let decision = decide(&model)?;
            assert_eq!(
                matches!(decision.verdict(), Verdict::Pass(_)),
                pass,
                "{key} {decision:?}"
            );
            assert_eq!(matches!(decision.verdict(), Verdict::Fail), !pass);
        }
        let incomplete = model(json!({key: [OWNER]}), |v| {
            record(
                v,
                "assert_statement",
                json!({"owner": OWNER, "construct": "assert"}),
            );
            v["facts"]["coverage"]["files_read"] = json!(0);
            v["facts"]["coverage"]["files_parsed"] = json!(0);
            v["facts"]["coverage"]["full_scope"] = json!(false);
            v["facts"]["coverage"]["gaps"] = json!([{"id": "UNKNOWN-gap", "evidence_class": "UNKNOWN", "area": "source", "kind": "collection_gap", "title": "gap", "subjects": [], "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [], "data": {"reason": "gap"}}]);
        })?;
        assert!(matches!(decide(&incomplete)?.verdict(), Verdict::Unknown));
    }
    Ok(())
}

#[test]
fn each_selector_role_matches_identity_and_never_passes_an_empty_inventory(
) -> Result<(), Box<dyn std::error::Error>> {
    for role in [
        "equality",
        "match",
        "read",
        "write",
        "call",
        "reflect",
        "constructor",
        "type_probe",
        "membership",
        "startswith",
        "endswith",
    ] {
        let literal_role = matches!(
            role,
            "equality" | "match" | "membership" | "startswith" | "endswith"
        );
        let member = if matches!(role, "constructor" | "type_probe") {
            Value::Null
        } else {
            json!("backend")
        };
        let mut selector = json!({"receiver": "shop.Connection", "member": member, "role": role});
        if literal_role {
            selector["literal"] = json!("forbidden");
        }
        let options = json!({"constructs": ["string_literal_compare"], "selector": selector});
        for (literal, expected) in [
            ("forbidden", "FAIL"),
            ("other", if literal_role { "PASS" } else { "FAIL" }),
        ] {
            let model = model(options.clone(), |v| {
                v["facts"]["profile"] = json!(Profile::Python.as_str());
                v["facts"]["adapter"]["name"] = json!(Profile::Python.as_str());
                v["facts"]["capabilities"]["constructs"] =
                    json!([{"name": "string_literal_compare", "status": "supported"}]);
                record(
                    v,
                    "construct_selector",
                    json!({"construct": "string_literal_compare", "owner": OWNER,
                    "selector_role": role, "receiver_type": "shop.Connection", "member": member,
                    "literal": if literal_role {json!(literal)} else {Value::Null}, "status": "decided",
                    "operation": "compare", "receiver_binding": null, "receiver_parameter": null}),
                );
            })?;
            let result = decide(&model)?;
            assert_eq!(
                matches!(result.verdict(), Verdict::Pass(_)),
                expected == "PASS",
                "{role} {result:?}"
            );
            assert_eq!(
                matches!(result.verdict(), Verdict::Fail),
                expected == "FAIL"
            );
        }
        let empty = model(options, |v| {
            v["facts"]["profile"] = json!(Profile::Python.as_str());
            v["facts"]["adapter"]["name"] = json!(Profile::Python.as_str());
            v["facts"]["capabilities"]["constructs"] =
                json!([{"name": "string_literal_compare", "status": "supported"}]);
        })?;
        assert!(matches!(decide(&empty)?.verdict(), Verdict::Unknown));
    }
    Ok(())
}

#[test]
fn type_ignore_allowances_bind_each_field_and_cannot_hide_an_unread_file(
) -> Result<(), Box<dyn std::error::Error>> {
    let allowance =
        json!({"qualified_name": OWNER, "line": 17, "statement": "x = call()", "tag": "arg-type"});
    for field in [
        None,
        Some("qualified_name"),
        Some("line"),
        Some("statement"),
        Some("tag"),
    ] {
        let model = model(
            json!({"constructs": ["type_ignore"], "allowed_type_ignores": [allowance]}),
            |v| {
                v["facts"]["capabilities"]["constructs"] =
                    json!([{"name": "type_ignore", "status": "supported"}]);
                let evidence = v["facts"]["files"][0]["evidence_id"].clone();
                let mut data = allowance.clone();
                data["owner"] = json!(OWNER);
                data["signal"] = json!("type_ignore");
                if let Some(field) = field {
                    data[field] = different(field);
                }
                let record = json!({"id": "SIGNAL-ignore", "evidence_class": "FACT", "area": "type_architecture",
                "kind": "type_ignore", "title": "ignore", "subjects": [OWNER], "evidence_ids": [evidence],
                "fact_ids": [], "rule_ids": [], "provenance": [], "data": data});
                if let Some(sections) = v["facts"]["sections"].as_array_mut() {
                    sections.push(json!({"name": "typing_signals", "records": [record]}));
                }
            },
        )?;
        let decision = decide(&model)?;
        assert_eq!(
            matches!(decision.verdict(), Verdict::Pass(_)),
            field.is_none(),
            "{field:?} {decision:?}"
        );
        assert_eq!(matches!(decision.verdict(), Verdict::Fail), field.is_some());
    }
    let unknown = model(
        json!({"constructs": ["type_ignore"], "allowed_type_ignores": [allowance]}),
        |v| {
            v["facts"]["capabilities"]["constructs"] =
                json!([{"name": "type_ignore", "status": "decided"}]);
            if let Some(sections) = v["facts"]["sections"].as_array_mut() {
                sections.push(json!({"name": "typing_signals", "records": []}));
            }
            v["facts"]["coverage"]["full_scope"] = json!(false);
            v["facts"]["coverage"]["gaps"] = json!([{"id": "UNKNOWN-ignore-file", "evidence_class": "UNKNOWN",
                "area": "source", "kind": "collection_gap", "title": "unread file", "subjects": [OWNER],
                "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [], "data": {"reason": "unread file", "module": OWNER}}]);
        },
    )?;
    assert!(matches!(decide(&unknown)?.verdict(), Verdict::Unknown));
    Ok(())
}

fn different(field: &str) -> Value {
    if field == "line" {
        json!(18)
    } else {
        json!("different")
    }
}

#[test]
fn selectors_with_wrong_or_missing_identity_are_unknown() -> Result<(), Box<dyn std::error::Error>>
{
    let options = json!({"constructs": ["string_literal_compare"], "selector": {
        "receiver": "shop.Connection", "member": "backend", "role": "equality", "literal": "forbidden"}});
    for (role, receiver, status, literal) in [
        (
            "equality",
            Some("other.Connection"),
            "decided",
            Some("forbidden"),
        ),
        (
            "match",
            Some("shop.Connection"),
            "decided",
            Some("forbidden"),
        ),
        ("equality", None, "unknown", Some("forbidden")),
        ("equality", Some("shop.Connection"), "decided", None),
    ] {
        let model = model(options.clone(), |v| {
            v["facts"]["profile"] = json!(Profile::Python.as_str());
            v["facts"]["adapter"]["name"] = json!(Profile::Python.as_str());
            v["facts"]["capabilities"]["constructs"] =
                json!([{"name": "string_literal_compare", "status": "decided"}]);
            record(
                v,
                "construct_selector",
                json!({"construct": "string_literal_compare", "owner": OWNER,
                "selector_role": role, "receiver_type": receiver, "member": "backend", "literal": literal,
                "status": status, "operation": "compare", "receiver_binding": null, "receiver_parameter": null}),
            );
        })?;
        let decision = decide(&model)?;
        assert!(
            matches!(decision.verdict(), Verdict::Unknown),
            "{role} {receiver:?} {decision:?}"
        );
        assert!(decision.reason().is_some());
    }
    Ok(())
}

#[test]
fn actual_symbol_subjects_do_not_widen_to_the_containing_module(
) -> Result<(), Box<dyn std::error::Error>> {
    let owner = "shop.src.presentation.page_x2e_ts.page";
    let present = model(json!({"source": owner}), |_| {})?;
    assert!(matches!(decide(&present)?.verdict(), Verdict::Pass(_)));
    let missing = model(json!({"source": format!("{owner}.missing")}), |_| {})?;
    assert!(matches!(decide(&missing)?.verdict(), Verdict::Unknown));
    let not_selected = model(json!({"source": owner}), |v| {
        record(
            v,
            "assert_statement",
            json!({"owner": OWNER, "construct": "assert"}),
        );
    })?;
    assert!(matches!(decide(&not_selected)?.verdict(), Verdict::Pass(_)));
    Ok(())
}
