// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use std::io::{Read, Write};

use flate2::read::GzDecoder;
use flate2::write::ZlibEncoder;
use flate2::Compression;
use serde_json::{json, Value};

use archkeel_model::{Input, Reason, Section, Unsupported};

use super::{Answer, Engine};
use crate::contract::ContractState;
use crate::ingest::ReplyState;
use crate::request::Request;

const LIMIT: u64 = 1 << 30;

/// The contract of the native workspace: only structural rule kinds.
pub(crate) const NATIVE_CONTRACT: &str = include_str!("../../architecture-contract.json");

/// The frozen H-typescript reply (AD-343), with the provenance of a run, compressed.
pub(crate) fn golden_reply() -> Vec<u8> {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/golden/typescript/h-typescript.json.gz");
    let mut text = String::new();
    if let Ok(file) = std::fs::File::open(path) {
        let _ = GzDecoder::new(file).read_to_string(&mut text);
    }
    let mut value: Value = serde_json::from_str(&text).unwrap_or(Value::Null);
    value["facts"]["adapter"]["version"] = json!("0");
    value["facts"]["adapter"]["code_digest"] = json!("0".repeat(64));
    value["facts"]["runtime"] = json!({"name": "rust", "version": "1.88.0", "required": null,
                                       "requirement_state": "declared"});
    value["facts"]["source"]["git_head"] = json!("a");
    value["facts"]["source"]["dirty"] = json!(false);
    value["facts"]["provider_bindings"] = json!([]);
    value["protocol_version"] = json!("9.0.0");
    value["provider_sources"] = json!([]);
    let mut encoder = ZlibEncoder::new(Vec::new(), Compression::fast());
    let _ = encoder.write_all(value.to_string().as_bytes());
    encoder.finish().unwrap_or_default()
}

fn ingest(engine: &mut Engine) -> Answer {
    engine.answer(Request::Ingest {
        reply: golden_reply(),
        inflate_limit: LIMIT,
    })
}

#[test]
fn the_engine_reads_the_rules_of_a_structural_contract() {
    let mut engine = Engine::default();
    let answer = engine.answer(Request::Contract(NATIVE_CONTRACT.as_bytes().to_vec()));
    let rules = match answer {
        Answer::Contract(ContractState::Parsed(rules)) => rules,
        other => {
            assert_eq!(format!("{other:?}"), "a parsed native contract");
            return;
        }
    };
    assert_eq!(rules.len(), 8);
    assert!(rules.contains_key("NATIVE-REQUIRES-COMPLETE"));
    let reasons =
        crate::contract::rule_reasons(engine.contract(), "native/architecture-contract.json");
    assert_eq!(reasons.len(), 8);
    assert!(reasons
        .values()
        .all(|reason| reason.to_string().starts_with("unsupported: rule kind")));
}

#[test]
fn a_contract_with_declarations_parses_in_the_core() {
    let mut engine = Engine::default();
    let answer = engine.answer(Request::Contract(
        br#"{"schema_version": "3.14.0",
        "components": [], "rules": [], "declarations": {}}"#
            .to_vec(),
    ));
    assert!(
        matches!(answer, Answer::Contract(ContractState::Parsed(_))),
        "{answer:?}"
    );
}

#[test]
fn a_contract_that_mounts_an_inside_contract_is_refused_by_name_and_never_used() {
    let mut engine = Engine::default();
    let answer = engine.answer(Request::Contract(
        br#"{"schema_version": "2.1.0", "rules": [], "components": [{"id": "C-A",
        "label": "a", "role": "component", "packages": ["p.a"], "responsibilities": ["A."],
        "forbidden_responsibilities": [], "provenance": ["d.md"], "inside": "inner.json"}]}"#
            .to_vec(),
    ));
    let text = format!("{answer:?}");
    assert!(
        matches!(
            answer,
            Answer::Contract(ContractState::Unsupported(Reason::Unsupported(
                Unsupported::InsideTree
            )))
        ),
        "{text}"
    );
    assert!(engine.contract().is_none());
}

#[test]
fn the_engine_ingests_a_reply_and_every_section_names_its_slice() {
    let mut engine = Engine::default();
    let _ = engine.answer(Request::Contract(NATIVE_CONTRACT.as_bytes().to_vec()));
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
        assert_eq!(
            rows.err(),
            Some(Reason::Unsupported(Unsupported::Section(section)))
        );
    }
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
    let rows = engine.answer(Request::Sections(vec![Section::Modules]));
    let text = format!("{rows:?}");
    assert!(text.contains("MissingInput(Contract)"), "{text}");
    let _ = engine.answer(Request::Contract(NATIVE_CONTRACT.as_bytes().to_vec()));
    let rows = engine.answer(Request::Sections(vec![Section::Modules]));
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
    let _ = engine.answer(Request::Contract(
        br#"{"schema_version": "2.2.0", "components": [], "rules": [],
        "declarations": {"uml": {"schema_version": "1.1.0"}}}"#
            .to_vec(),
    ));
    let reasons = crate::contract::rule_reasons(engine.contract(), "architecture-contract.json");
    let reason = reasons
        .get("UML-TARGET-a2e40c5592b1b06a")
        .map(ToString::to_string);
    assert_eq!(
        reason.as_deref(),
        Some("unsupported: the UML target of the contract: no slice ports it yet")
    );
}
