// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The read set of each rule kind (AD-564).
//! The rules come from the contract of `F-architecture`, which holds a rule of each kind except
//! `complete_requires`. `reads` takes a module name, so no reply has to hold the modules.

use std::io::Read;

use archkeel_contract::{head_of, Contract, ParsedContract, Rule};
use archkeel_facts::envelope::Facts;
use serde_json::{json, Value};

use super::{reads, ReadSet};
use crate::{Graph, Model, Producer, Settings};

const ROOT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");

const NONE: ReadSet = ReadSet {
    edges: false,
    code: false,
    layout: false,
};
const BOTH: ReadSet = ReadSet::BOTH;
const EDGES: ReadSet = ReadSet {
    edges: true,
    code: false,
    layout: false,
};
const CODE: ReadSet = ReadSet {
    edges: false,
    code: true,
    layout: false,
};
/// The file and the place in the layout of the module: only a layout effect leaves it unknown.
const LAYOUT: ReadSet = ReadSet {
    edges: false,
    code: false,
    layout: true,
};

fn contract() -> Result<Contract, Box<dyn std::error::Error>> {
    let path = format!("{ROOT}/fixtures/F-architecture/architecture-contract.json");
    let mut value: Value = serde_json::from_slice(&std::fs::read(path)?)?;
    // A mount needs its tree; the rules of the root contract are what this test reads.
    for component in value["components"].as_array_mut().ok_or("components")? {
        component
            .as_object_mut()
            .ok_or("component")?
            .remove("inside");
    }
    value["schema_version"] = json!("3.21.0");
    let rules = value["rules"].as_array_mut().ok_or("rules")?;
    let head = json!({"rationale": "r", "provenance": ["p"], "decided_by": "architect"});
    for mut rule in [
        json!({"id": "MODULE-CYCLES", "kind": "no_component_cycles", "level": "module"}),
        json!({"id": "REQUIRES", "kind": "complete_requires"}),
        json!({"id": "DEP-APP-INDIRECT", "kind": "forbidden_dependency", "source": "shop.app",
            "target": "shop.store", "include_type_checking": true, "indirect": true}),
        json!({"id": "SELECTOR", "kind": "forbidden_construct", "source": "shop.app",
            "constructs": ["string_literal_compare"],
            "selector": {"receiver": "Order", "member": "id", "role": "read"}}),
    ] {
        for (key, field) in head.as_object().into_iter().flatten() {
            rule[key] = field.clone();
        }
        rules.push(rule);
    }
    match archkeel_contract::parse(value.to_string().as_bytes())? {
        ParsedContract::Complete(contract) => Ok(contract),
        _ => Err("a partial contract".into()),
    }
}

fn model(contract: &Contract) -> Result<Model, Box<dyn std::error::Error>> {
    let mut text = String::new();
    let path = format!("{ROOT}/tests/golden/typescript/h-typescript.json.gz");
    flate2::read::GzDecoder::new(std::fs::File::open(path)?).read_to_string(&mut text)?;
    let mut reply: Value = serde_json::from_str(&text)?;
    reply["facts"]["adapter"]["version"] = json!("0");
    reply["facts"]["adapter"]["code_digest"] = json!("0".repeat(64));
    reply["facts"]["runtime"] = json!({"name": "rust", "version": "1.97.0", "required": ">=1.97",
        "requirement_state": "declared"});
    reply["facts"]["source"]["git_head"] = json!("a");
    reply["facts"]["source"]["dirty"] = json!(false);
    reply["facts"]["provider_bindings"] = json!([]);
    reply["facts"]["validation"] = serde_json::from_str(include_str!(
        "../../../tests/golden/typescript/validation.json"
    ))?;
    let facts: Facts = serde_json::from_value(reply["facts"].clone())?;
    model_of(contract, &facts)
}

fn model_of(contract: &Contract, facts: &Facts) -> Result<Model, Box<dyn std::error::Error>> {
    let settings = Settings::new("shop".to_owned(), facts.profile.as_str().to_owned(), vec![])
        .with_producer(Producer::Trusted);
    let graph = Graph::recorded(facts, settings).map_err(|reason| reason.to_string())?;
    Model::of(contract, graph).map_err(|refused| refused.1.to_string().into())
}

/// A module of the component `app`, a module of `store`, and a module that no component claims.
const APP: &str = "shop.app.orders";
const STORE: &str = "shop.store.sqlite";
const LOOSE: &str = "shop.loose";

/// What each rule reads of some module, of `APP`, of `STORE` and of `LOOSE`.
const ROWS: [(&str, [ReadSet; 4]); 23] = [
    // The root and the source are `shop`: each module below it.
    ("ROOT-LAYOUT", [LAYOUT; 4]),
    ("ASSIGNMENT-COMPLETE", [LAYOUT; 4]),
    ("LAYERS-MODEL", [NONE; 4]),
    ("DEP-APP-ALLOWS-STORE", [NONE; 4]),
    // The sources are the modules of `app`, and a module without an owner.
    ("DEP-APP-NO-RENDER", [EDGES, EDGES, NONE, EDGES]),
    ("DEP-STORE-NO-APP", [EDGES, NONE, EDGES, EDGES]),
    // A chain can run through any module, so an `indirect` rule reads the edges of each one
    // (AD-1085): `store` is no source here, and the direct rule above reads none of it.
    ("DEP-APP-INDIRECT", [EDGES; 4]),
    // A `target_symbol` reads the code of each module.
    ("DEP-STORE-NO-MONEY", [BOTH, CODE, BOTH, BOTH]),
    ("EXTERNAL-COMPLETE", [EDGES; 4]),
    // `shop.store` is an allowed source of `json`.
    ("EXTERNAL-JSON-STORE", [EDGES, EDGES, NONE, EDGES]),
    ("STORE-PEERS-ISOLATED", [EDGES, NONE, EDGES, NONE]),
    ("REQUIRES", [BOTH, BOTH, BOTH, NONE]),
    ("INTERFACE-BOUNDARY", [BOTH, BOTH, BOTH, CODE]),
    ("COMPONENT-NO-CYCLES", [EDGES, EDGES, EDGES, NONE]),
    ("MODULE-CYCLES", [EDGES; 4]),
    ("CONSTRUCT-NO-ASSERT", [BOTH; 4]),
    // The source of the rule is `shop.app`, and a selector reads the bindings of each module.
    ("SELECTOR", [BOTH; 4]),
    // A kind without a proof of a narrower reading reads each module.
    ("APP-TYPES-NOT-DICT", [BOTH; 4]),
    ("CALL-DESCRIBE-NO-MAINTENANCE", [BOTH; 4]),
    ("MODEL-TYPES-IN-ENTITIES", [BOTH; 4]),
    ("MODEL-NONCE-OWNER", [BOTH; 4]),
    ("STORE-READER-DECLARATION", [BOTH; 4]),
    ("APP-OPTION-KEY", [BOTH; 4]),
];

#[test]
fn each_rule_kind_reads_the_facts_that_its_row_states() -> Result<(), Box<dyn std::error::Error>> {
    let contract = contract()?;
    let model = model(&contract)?;
    let rule = |id: &str| -> Option<&Rule> {
        let rules = contract.rules().iter();
        rules
            .into_iter()
            .find(|rule| head_of(rule).id().as_text() == id)
    };
    for (id, expected) in ROWS {
        let rule = rule(id).ok_or(id)?;
        let found =
            [None, Some(APP), Some(STORE), Some(LOOSE)].map(|module| reads(&model, rule, module));
        assert_eq!(found, expected, "{id}");
    }
    // A source that selects no module of the name reads nothing of it.
    let construct = rule("SELECTOR").ok_or("SELECTOR")?;
    assert_eq!(reads(&model, construct, Some("other.loose")), BOTH);
    let plain = rule("CONSTRUCT-NO-ASSERT").ok_or("CONSTRUCT-NO-ASSERT")?;
    assert_eq!(reads(&model, plain, Some("other.loose")), NONE);
    let complete = rule("EXTERNAL-COMPLETE").ok_or("EXTERNAL-COMPLETE")?;
    assert_eq!(reads(&model, complete, Some("other.loose")), NONE);
    // A module outside the root and the source is no file that the layout rules read.
    for id in ["ROOT-LAYOUT", "ASSIGNMENT-COMPLETE"] {
        let layout = rule(id).ok_or(id)?;
        assert_eq!(reads(&model, layout, Some("other.loose")), NONE, "{id}");
    }
    // A pair gap between any two modules can hide a link of a chain.
    let pair_reads = |id: &str| -> Result<_, Box<dyn std::error::Error>> {
        let rule = rule(id).ok_or(id)?;
        Ok(crate::pair_gaps::reads(
            rule,
            contract.components(),
            contract.rules(),
        ))
    };
    assert_eq!(
        pair_reads("DEP-APP-INDIRECT")?,
        crate::pair_gaps::Reads::Every
    );
    assert!(matches!(
        pair_reads("DEP-APP-NO-RENDER")?,
        crate::pair_gaps::Reads::Sides(_)
    ));
    // An exact allowed source of a forbidden dependency is no source.
    let sqlite = rule("DEP-APP-NO-STORE-SQLITE").ok_or("DEP-APP-NO-STORE-SQLITE")?;
    assert_eq!(reads(&model, sqlite, Some("shop.app.maintenance")), NONE);
    assert_eq!(reads(&model, sqlite, Some(APP)), EDGES);
    Ok(())
}

/// AD-1560: an unresolved import that no gap names releases a rule that reads only files, and no
/// other cause of the scope state does: a rule that selects no module, or an unknown Git head,
/// still holds it (the review of #2250).
#[test]
fn unresolved_imports_release_a_file_rule_and_no_other_cause_does(
) -> Result<(), Box<dyn std::error::Error>> {
    let contract = contract()?;
    let decide =
        |git_head: &str, id: &str| -> Result<Result<(), String>, Box<dyn std::error::Error>> {
            let (reply, ..) = crate::edges::tests::unresolved().ok_or("the golden reply")?;
            let mut value = serde_json::to_value(&reply.facts)?;
            value["runtime"] = json!({"name": "rust", "version": "1.97.0", "required": ">=1.97",
                "requirement_state": "declared"});
            value["source"]["git_head"] = json!(git_head);
            let facts: Facts = serde_json::from_value(value)?;
            let model = model_of(&contract, &facts)?;
            let rule = contract
                .rules()
                .iter()
                .find(|rule| head_of(rule).id().as_text() == id)
                .ok_or(id)?;
            Ok(crate::scope_order::rule(&model, rule).map_err(|reason| reason.to_string()))
        };
    // The golden contract has a rule that selects no module of the reply: another cause of the
    // state. A file rule is released from the unresolved import only, so that cause stays.
    for id in ["ROOT-LAYOUT", "ASSIGNMENT-COMPLETE"] {
        let other = decide("a", id)?.err().ok_or(id)?;
        assert!(other.contains("selects no module"), "{id}: {other}");
        let git = decide("unknown", id)?.err().ok_or(id)?;
        assert!(!git.contains("not resolved") && git != other, "{id}: {git}");
    }
    // The rules that read an edge keep the unresolved import as their cause.
    let held = decide("a", "REQUIRES")?;
    assert!(held.is_err_and(|text| text.contains("not resolved")));
    Ok(())
}
