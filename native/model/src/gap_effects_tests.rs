// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The class of a gap, the read set of each rule kind and the stable key of the cause (AD-564).
//! The rules come from the contract of `F-architecture`, which holds a rule of each kind except
//! `complete_requires`. `reads` takes a module name, so no reply has to hold the modules.

use std::io::Read;

use archkeel_contract::{head_of, Contract, ParsedContract, Rule};
use archkeel_facts::data::{GapData, GapEffect};
use archkeel_facts::envelope::Facts;
use archkeel_facts::ids::ModuleName;
use serde_json::{json, Value};

use super::{class, reads, Class, Doubt, ReadSet, Scoped};
use crate::causes::Cause;
use crate::reason::Reason;
use crate::reason_key::stable;
use crate::{Graph, Model, Producer, Settings};

const ROOT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");

const NONE: ReadSet = ReadSet::NONE;
const BOTH: ReadSet = ReadSet::BOTH;
const EDGES: ReadSet = ReadSet {
    edges: true,
    code: false,
};
const CODE: ReadSet = ReadSet {
    edges: false,
    code: true,
};

fn names(names: &[&str]) -> Vec<ModuleName> {
    names.iter().map(|name| ModuleName::new(*name)).collect()
}

fn gap(source: Option<&str>, effect: Option<GapEffect>) -> GapData {
    let mut data = GapData::at("site", "shop.a");
    data.source_module = source.map(ModuleName::new);
    data.effect = effect;
    data
}

#[test]
fn each_doubt_of_a_gap_goes_to_the_wider_class() {
    let known = |name: &str| name == "shop.a" || name == "shop.b";
    let edges = |sources: &[&str]| {
        Some(GapEffect::Edges {
            sources: names(sources),
        })
    };
    let modules = |modules: &[&str]| {
        Some(GapEffect::Modules {
            modules: names(modules),
        })
    };
    let rows = [
        (gap(None, None), Class::Whole),
        (gap(Some("shop.b"), None), Class::Pair),
        // The two names of a pair form are one module: it is no pair (`coverage::droppable`).
        (gap(Some("shop.a"), None), Class::Whole),
        (gap(None, edges(&["shop.a"])), Class::Effect),
        (gap(None, modules(&["shop.a", "shop.b"])), Class::Effect),
        (gap(None, Some(GapEffect::EveryModule)), Class::Effect),
        (gap(None, edges(&[])), Class::Whole),
        (gap(None, modules(&[])), Class::Whole),
        (gap(None, edges(&["shop.a", "shop.c"])), Class::Whole),
        (gap(None, modules(&["shop.c"])), Class::Whole),
        (gap(Some("shop.b"), edges(&["shop.a"])), Class::Whole),
        (
            gap(Some("shop.b"), Some(GapEffect::EveryModule)),
            Class::Whole,
        ),
    ];
    for (data, expected) in rows {
        assert_eq!(class(&data, &known), expected, "{data:?}");
    }
}

fn contract() -> Result<Contract, Box<dyn std::error::Error>> {
    let path = format!("{ROOT}/fixtures/F-architecture/architecture-contract.json");
    let mut value: Value = serde_json::from_slice(&std::fs::read(path)?)?;
    // A mount needs its tree; the rules of the root contract are what this test reads.
    for component in value["components"].as_array_mut().ok_or("components")? {
        component.as_object_mut().ok_or("component")?.remove("inside");
    }
    let rules = value["rules"].as_array_mut().ok_or("rules")?;
    let head = json!({"rationale": "r", "provenance": ["p"], "decided_by": "architect"});
    for mut rule in [
        json!({"id": "MODULE-CYCLES", "kind": "no_component_cycles", "level": "module"}),
        json!({"id": "REQUIRES", "kind": "complete_requires"}),
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
    let facts: Facts = serde_json::from_value(reply["facts"].clone())?;
    let settings = Settings::new("shop".to_owned(), facts.profile.as_str().to_owned(), vec![])
        .with_producer(Producer::Trusted);
    let graph = Graph::recorded(&facts, settings).map_err(|reason| reason.to_string())?;
    Model::of(contract, graph).map_err(|refused| refused.1.to_string().into())
}

/// A module of the component `app`, a module of `store`, and a module that no component claims.
const APP: &str = "shop.app.orders";
const STORE: &str = "shop.store.sqlite";
const LOOSE: &str = "shop.loose";

/// What each rule reads of some module, of `APP`, of `STORE` and of `LOOSE`.
const ROWS: [(&str, [ReadSet; 4]); 22] = [
    ("ROOT-LAYOUT", [NONE; 4]),
    ("ASSIGNMENT-COMPLETE", [NONE; 4]),
    ("LAYERS-MODEL", [NONE; 4]),
    ("DEP-APP-ALLOWS-STORE", [NONE; 4]),
    // The sources are the modules of `app`, and a module without an owner.
    ("DEP-APP-NO-RENDER", [EDGES, EDGES, NONE, EDGES]),
    ("DEP-STORE-NO-APP", [EDGES, NONE, EDGES, EDGES]),
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
        rules.into_iter().find(|rule| head_of(rule).id().as_text() == id)
    };
    for (id, expected) in ROWS {
        let rule = rule(id).ok_or(id)?;
        let found = [None, Some(APP), Some(STORE), Some(LOOSE)]
            .map(|module| reads(&model, rule, module));
        assert_eq!(found, expected, "{id}");
    }
    // A source that selects no module of the name reads nothing of it.
    let construct = rule("SELECTOR").ok_or("SELECTOR")?;
    assert_eq!(reads(&model, construct, Some("other.loose")), BOTH);
    let plain = rule("CONSTRUCT-NO-ASSERT").ok_or("CONSTRUCT-NO-ASSERT")?;
    assert_eq!(reads(&model, plain, Some("other.loose")), NONE);
    let complete = rule("EXTERNAL-COMPLETE").ok_or("EXTERNAL-COMPLETE")?;
    assert_eq!(reads(&model, complete, Some("other.loose")), NONE);
    // An exact allowed source of a forbidden dependency is no source.
    let sqlite = rule("DEP-APP-NO-STORE-SQLITE").ok_or("DEP-APP-NO-STORE-SQLITE")?;
    assert_eq!(reads(&model, sqlite, Some("shop.app.maintenance")), NONE);
    assert_eq!(reads(&model, sqlite, Some(APP)), EDGES);
    Ok(())
}

fn scoped(ids: &[&str], doubts: Vec<Doubt>) -> Scoped {
    Scoped {
        ids: ids.iter().map(|id| (*id).to_owned()).collect(),
        doubts,
    }
}

#[test]
fn the_cause_names_the_doubts_and_its_key_holds_no_gap_id() {
    let doubts = vec![
        Doubt::Edges("shop.a".to_owned()),
        Doubt::Code("shop.b".to_owned()),
        Doubt::EveryModule,
    ];
    let first = Reason::NotComplete(Cause::ScopedGaps(scoped(&["U-1", "U-2"], doubts.clone())));
    assert_eq!(
        first.to_string(),
        "incomplete scope: 2 gaps leave unknown what the rule reads: the import edges \
         of shop.a, the code of shop.b, the code of every module"
    );
    let key = stable(&first);
    let words: Vec<(&str, &str)> = key
        .iter()
        .map(|entry| (entry.kind.as_str(), entry.reason.as_str()))
        .collect();
    assert_eq!(
        words,
        [
            ("gap_effect", "edges: shop.a"),
            ("gap_effect", "modules: shop.b"),
            ("gap_effect", "every_module"),
        ]
    );
    // The same doubts of other gaps are the same key; another doubt is another key.
    let moved = Reason::NotComplete(Cause::ScopedGaps(scoped(&["U-9"], doubts)));
    assert_eq!(stable(&moved), key);
    let other = vec![Doubt::Edges("shop.c".to_owned())];
    let other = Reason::NotComplete(Cause::ScopedGaps(scoped(&["U-1", "U-2"], other)));
    assert_ne!(stable(&other), key);
}
