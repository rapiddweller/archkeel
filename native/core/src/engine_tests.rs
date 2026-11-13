// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use std::io::{Read, Write};

use flate2::read::GzDecoder;
use flate2::write::ZlibEncoder;
use flate2::Compression;
use serde_json::{json, Value};

use std::collections::BTreeMap;

use archkeel_model::{Input, Reason, Section, Settings, Unsupported};
use archkeel_report::{Named, RuleReasons};

use super::{Answer, Engine};
use crate::contract::{ContractInput, ContractState};
use crate::ingest::ReplyState;
use crate::request::Request;

const LIMIT: u64 = 1 << 30;

/// The frame of the ruling of the engine, and the reason of each rule without a decision (`*`
/// for one reason of the whole contract).
pub(crate) fn ruled(engine: &mut Engine, named: Named) -> (Value, BTreeMap<String, String>) {
    let Answer::Rules(Ok(ruling)) = engine.answer(Request::Rules(named)) else {
        assert_eq!("no ruling", "a ruling");
        return (Value::Null, BTreeMap::new());
    };
    let reasons = match ruling.unsupported() {
        RuleReasons::Each(each) => each.clone(),
        RuleReasons::All(all) => BTreeMap::from([("*".to_owned(), all.clone())]),
    };
    (
        serde_json::to_value(&ruling).unwrap_or(Value::Null),
        reasons,
    )
}

/// The contract of the native workspace: only structural rule kinds.
pub(crate) const NATIVE_CONTRACT: &str = include_str!("../../architecture-contract.json");

/// The frozen H-typescript reply (AD-343), with the provenance of a run, compressed.
pub(crate) fn golden_reply() -> Vec<u8> {
    golden_reply_by(None)
}

/// The frozen reply; with `adapter`, the reply names that adapter (another collector).
pub(crate) fn golden_reply_by(adapter: Option<&str>) -> Vec<u8> {
    golden_reply_with(|value| {
        if let Some(adapter) = adapter {
            value["facts"]["adapter"]["name"] = json!(adapter);
        }
    })
}

/// The frozen reply after `change` (a caller can write any reply bytes).
pub(crate) fn golden_reply_with(change: impl FnOnce(&mut Value)) -> Vec<u8> {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/golden/typescript/h-typescript.json.gz");
    let mut text = String::new();
    if let Ok(file) = std::fs::File::open(path) {
        let _ = GzDecoder::new(file).read_to_string(&mut text);
    }
    let mut value: Value = serde_json::from_str(&text).unwrap_or(Value::Null);
    value["facts"]["adapter"]["version"] = json!("0");
    value["facts"]["adapter"]["code_digest"] = json!("0".repeat(64));
    value["facts"]["runtime"] = json!({"name": "rust", "version": "1.88.0", "required": ">=1.88",
                                       "requirement_state": "declared"});
    value["facts"]["source"]["git_head"] = json!("a");
    value["facts"]["source"]["dirty"] = json!(false);
    value["facts"]["provider_bindings"] = json!([]);
    value["protocol_version"] = json!("9.0.0");
    value["provider_sources"] = json!([]);
    change(&mut value);
    let mut encoder = ZlibEncoder::new(Vec::new(), Compression::fast());
    let _ = encoder.write_all(value.to_string().as_bytes());
    encoder.finish().unwrap_or_default()
}

/// The profile of the frozen reply, read from the reply (the sources name no language).
pub(crate) fn golden_profile() -> String {
    archkeel_store::ingest_reply(&golden_reply(), LIMIT).map_or_else(
        |_| String::new(),
        |r| r.reply().facts.profile.as_str().to_owned(),
    )
}

fn ingest(engine: &mut Engine) -> Answer {
    engine.answer(Request::Settings(Settings::new(
        "shop".to_owned(),
        golden_profile(),
        Vec::new(),
    )));
    engine.answer(Request::Ingest {
        reply: golden_reply(),
        inflate_limit: LIMIT,
    })
}

#[test]
fn the_engine_reads_the_rules_of_a_structural_contract() {
    let mut engine = Engine::default();
    let answer = engine.answer(Request::Contract(ContractInput::root(
        NATIVE_CONTRACT.as_bytes().to_vec(),
    )));
    let rules = match answer {
        Answer::Contract(ContractState::Parsed(rules)) => rules,
        other => {
            assert_eq!(format!("{other:?}"), "a parsed native contract");
            return;
        }
    };
    assert_eq!(rules.len(), 83);
    assert!(rules.contains_key("NATIVE-REQUIRES-COMPLETE"));
    let (frame, reasons) = ruled(&mut engine, Named::default());
    assert_eq!(frame["rules"], json!({}));
    assert_eq!(frame["status"], "UNKNOWN");
    assert_eq!(reasons.len(), 83);
    // Each kind of the native contract is decided since slice S7: each rule needs the model.
    for (id, reason) in &reasons {
        assert_eq!(
            reason,
            &Reason::MissingInput(Input::Reply).to_string(),
            "{id}"
        );
    }
}

/// The H-typescript contract with the packages of `data` moved away: two modules lose their owner.
fn unowned_contract() -> Vec<u8> {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/H-typescript/architecture-contract.json");
    let text = std::fs::read_to_string(path).unwrap_or_default();
    let mut value: Value = serde_json::from_str(&text).unwrap_or(Value::Null);
    if let Some(components) = value["components"].as_array_mut() {
        for component in components {
            if component["id"] == "COMP-DATA" {
                component["packages"] = json!(["shop.src.store"]);
            }
        }
    }
    value.to_string().into_bytes()
}

#[test]
fn the_engine_decides_the_s1_kinds_and_writes_their_violation_rows() {
    let mut engine = Engine::default();
    let _ = engine.answer(Request::Contract(ContractInput::root(unowned_contract())));
    let _ = ingest(&mut engine);
    let (frame, _) = ruled(&mut engine, Named::default());
    assert_eq!(
        frame["rules"]["ASSIGNMENT"],
        json!(["complete_assignment", "FAIL"])
    );
    // The settings name no producer, so the reply counts as one of an external collector: the
    // scope is not complete, and the rule is a decided UNKNOWN with its reason (AD-378).
    assert_eq!(frame["rules"]["LAYOUT"], json!(["root_layout", "UNKNOWN"]));
    assert_eq!(
        frame["explained"]["LAYOUT"],
        "incomplete scope: the reply does not come from the bundled collector, and the collector pin is not verified by the core"
    );
    assert_eq!(frame["violations"]["ASSIGNMENT"], 2);
    assert_eq!(frame["status"], "FAIL");
    let Answer::Sections(rows) = engine.answer(Request::Sections(vec![Section::Violations])) else {
        fail("a sections answer");
        return;
    };
    let rows = rows.into_iter().next().and_then(|(_, rows)| rows.ok());
    let rows = rows.unwrap_or_default();
    assert_eq!(rows.len(), 2);
    let local = rows.iter().find(|row| row["id"] == "VIO-671ede9c9771d825");
    let expected = json!({
        "id": "VIO-671ede9c9771d825", "evidence_class": "VIOLATION", "area": "components",
        "kind": "complete_assignment",
        "title": "shop.src.data.local_x2e_ts is not owned by exactly one component",
        "subjects": ["shop.src.data.local_x2e_ts"], "evidence_ids": [local.map(|r| r["evidence_ids"][0].clone())],
        "rule_ids": ["ASSIGNMENT"], "fact_ids": ["MOD-18a1182dc796d79c"], "provenance": [],
        "data": {"source": "shop", "module": "shop.src.data.local_x2e_ts"}
    });
    assert_eq!(local, Some(&expected));
}

#[test]
fn a_contract_with_declarations_parses_in_the_core() {
    let mut engine = Engine::default();
    let answer = engine.answer(Request::Contract(ContractInput::root(
        br#"{"schema_version": "3.14.0",
        "components": [], "rules": [], "declarations": {}}"#
            .to_vec(),
    )));
    assert!(
        matches!(answer, Answer::Contract(ContractState::Parsed(_))),
        "{answer:?}"
    );
}

#[test]
fn a_contract_that_mounts_an_inside_contract_names_the_missing_paths_and_is_never_used() {
    let mut engine = Engine::default();
    let answer = engine.answer(Request::Contract(ContractInput::root(
        br#"{"schema_version": "2.1.0", "rules": [], "components": [{"id": "C-A",
        "label": "a", "role": "component", "packages": ["p.a"], "responsibilities": ["A."],
        "forbidden_responsibilities": [], "provenance": ["d.md"], "inside": "inner.json"}]}"#
            .to_vec(),
    )));
    let text = format!("{answer:?}");
    assert!(
        matches!(answer, Answer::Contract(ContractState::Missing(paths)) if paths == ["inner.json"]),
        "{text}"
    );
    assert!(engine.usable().is_none());
}

#[test]
fn the_engine_ingests_a_reply_and_each_section_has_rows_or_names_its_slice() {
    let mut engine = Engine::default();
    let _ = engine.answer(Request::Contract(ContractInput::root(
        NATIVE_CONTRACT.as_bytes().to_vec(),
    )));
    assert!(matches!(ingest(&mut engine), Answer::Reply(ReplyState::Ingested(files)) if files > 0));
    let rows = match engine.answer(Request::Sections(Section::ALL.to_vec())) {
        Answer::Sections(rows) => rows,
        other => {
            assert_eq!(format!("{other:?}"), "a sections answer");
            return;
        }
    };
    assert_eq!(rows.len(), Section::ALL.len());
    for (section, rows) in rows {
        if section == Section::Violations {
            // The rows of the decided kinds; the native contract finds no violation here.
            assert!(rows.is_ok_and(|rows| rows.is_empty()));
            continue;
        }
        if crate::topology::owns(section) {
            // The rows of slice S3; the golden reply has no cycle.
            let empty = section == Section::Cycles;
            assert!(
                rows.is_ok_and(|rows| rows.is_empty() == empty),
                "{section:?}"
            );
            continue;
        }
        assert_eq!(
            rows.err(),
            Some(Reason::Unsupported(Unsupported::Section(section)))
        );
    }
}

#[test]
fn a_run_derives_its_model_one_time_until_an_input_changes() {
    let mut engine = Engine::default();
    let _ = engine.answer(Request::Contract(ContractInput::root(
        NATIVE_CONTRACT.as_bytes().to_vec(),
    )));
    let _ = ingest(&mut engine);
    assert_eq!(engine.derivations(), 0);
    let _ = engine.answer(Request::Sections(vec![
        Section::Modules,
        Section::Violations,
    ]));
    let _ = engine.answer(Request::Rules(Named::default()));
    let _ = engine.answer(Request::Sections(vec![Section::DependencyEdges]));
    assert_eq!(engine.derivations(), 1);
    // A new contract drops the derivation, so the next request derives again.
    let _ = engine.answer(Request::Contract(ContractInput::root(
        NATIVE_CONTRACT.as_bytes().to_vec(),
    )));
    let _ = engine.answer(Request::Rules(Named::default()));
    assert_eq!(engine.derivations(), 2);
}

#[test]
fn a_module_outside_the_namespace_refuses_the_four_sections_of_slice_s3() {
    let mut engine = Engine::default();
    let _ = ingest(&mut engine);
    let _ = engine.answer(Request::Settings(Settings::new(
        "elsewhere".to_owned(),
        golden_profile(),
        Vec::new(),
    )));
    let owned = vec![
        Section::DependencyEdges,
        Section::Modules,
        Section::Packages,
        Section::Cycles,
    ];
    let Answer::Sections(rows) = engine.answer(Request::Sections(owned)) else {
        return fail("a sections answer");
    };
    assert_eq!(rows.len(), 4);
    for (section, rows) in rows {
        let text = rows
            .err()
            .map(|reason| reason.to_string())
            .unwrap_or_default();
        assert!(
            text.starts_with("refused settings: "),
            "{section:?}: {text}"
        );
        assert!(
            text.contains("outside the namespace"),
            "{section:?}: {text}"
        );
    }
}

#[test]
fn new_settings_or_a_new_reply_drop_the_cached_model() {
    let mut engine = Engine::default();
    let _ = engine.answer(Request::Contract(ContractInput::root(
        NATIVE_CONTRACT.as_bytes().to_vec(),
    )));
    let _ = ingest(&mut engine);
    let _ = engine.answer(Request::Rules(Named::default()));
    assert_eq!(engine.derivations(), 1);
    let _ = engine.answer(Request::Settings(Settings::new(
        "shop".to_owned(),
        golden_profile(),
        Vec::new(),
    )));
    let _ = engine.answer(Request::Rules(Named::default()));
    assert_eq!(engine.derivations(), 2);
    let _ = engine.answer(Request::Ingest {
        reply: golden_reply(),
        inflate_limit: LIMIT,
    });
    let _ = engine.answer(Request::Sections(vec![Section::Modules]));
    assert_eq!(engine.derivations(), 3);
}

#[test]
fn a_section_named_twice_has_its_rows_built_once() {
    let mut engine = Engine::default();
    let _ = engine.answer(Request::Contract(ContractInput::root(
        NATIVE_CONTRACT.as_bytes().to_vec(),
    )));
    let _ = ingest(&mut engine);
    let repeated = vec![Section::Cycles, Section::Modules, Section::Cycles];
    let Answer::Sections(rows) = engine.answer(Request::Sections(repeated)) else {
        return fail("a sections answer");
    };
    let sections: Vec<Section> = rows.iter().map(|(section, _)| *section).collect();
    assert_eq!(sections, [Section::Cycles, Section::Modules]);
}

#[test]
fn a_reply_that_is_not_compressed_is_refused_by_the_store() {
    let mut engine = Engine::default();
    let answer = engine.answer(Request::Ingest {
        reply: b"{}".to_vec(),
        inflate_limit: LIMIT,
    });
    assert!(
        matches!(answer, Answer::Reply(ReplyState::Refused(message)) if message.contains("compressed"))
    );
}

#[test]
fn the_report_is_unsupported_until_slice_0d() {
    let answer = Engine::default().answer(Request::Report);
    assert!(matches!(
        answer,
        Answer::Report(Reason::Unsupported(Unsupported::Report))
    ));
}

#[test]
fn a_section_without_a_contract_or_a_reply_names_the_missing_input() {
    let mut engine = Engine::default();
    let rows = engine.answer(Request::Sections(vec![Section::Metrics]));
    let text = format!("{rows:?}");
    assert!(text.contains("MissingInput(Contract)"), "{text}");
    // A section of slice S3 needs only the reply part of the model: it names the reply.
    let rows = engine.answer(Request::Sections(vec![Section::Modules]));
    let text = format!("{rows:?}");
    assert!(text.contains("MissingInput(Reply)"), "{text}");
    let _ = engine.answer(Request::Contract(ContractInput::root(
        NATIVE_CONTRACT.as_bytes().to_vec(),
    )));
    let rows = engine.answer(Request::Sections(vec![Section::Metrics]));
    let text = format!("{rows:?}");
    assert!(text.contains("MissingInput(Reply)"), "{text}");
    assert_eq!(
        Reason::MissingInput(Input::Reply).to_string(),
        "missing input: no valid collector reply"
    );
}

#[test]
fn the_uml_target_of_a_contract_is_an_unsupported_rule_by_name() {
    let mut engine = Engine::default();
    let _ = engine.answer(Request::Contract(ContractInput::root(
        br#"{"schema_version": "2.2.0", "components": [], "rules": [],
        "declarations": {"uml": {"schema_version": "1.1.0"}}}"#
            .to_vec(),
    )));
    let reason = crate::contract::uml_reason(engine.usable(), "architecture-contract.json");
    let reason = reason.map(|(id, reason)| format!("{id}: {reason}"));
    assert_eq!(
        reason.as_deref(),
        Some("UML-TARGET-a2e40c5592b1b06a: unsupported: the UML target of the contract: no slice ports it yet")
    );
}

/// Fail the test with a message (clippy refuses `panic!` in this workspace).
fn fail(message: &str) {
    assert_eq!(message, "", "the test setup failed");
}
