// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A PASS needs the model (AD-381, #1073 items 1 to 3 and 7): a rule row only with a PASS of
//! its own rule of the model, the observation only with a complete scope, the status only with
//! the run proof of L-35b. The model and the outcomes come from the frozen H-typescript reply.

use std::io::{Read, Write};

use archkeel_contract::{Contract, ParsedContract};
use archkeel_eval::{evaluate, Outcome};
use archkeel_model::{Decision, Model, Producer, RunGap, Settings};
use flate2::read::GzDecoder;
use flate2::write::ZlibEncoder;
use flate2::Compression;
use serde_json::{json, Value};

use crate::test_support::{bytes, inputs};
use crate::{
    build, BuildError, Payload, Produced, Records, Report, RuleDecision, RuleOutcome, RuleText,
    RunOutcome, Status, Target,
};

const ROOT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");

fn read_json(path: &str) -> Value {
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
fn contract(keep: &[&str]) -> Contract {
    parsed(keep).unwrap()
}

fn parsed(keep: &[&str]) -> Option<Contract> {
    let mut value = read_json("fixtures/H-typescript/architecture-contract.json");
    let rules: Vec<Value> = value["rules"]
        .as_array()
        .map(|rules| {
            let kept = rules
                .iter()
                .filter(|r| keep.iter().any(|id| r["id"] == *id));
            kept.cloned().collect()
        })
        .unwrap_or_default();
    value["rules"] = json!(rules);
    match archkeel_contract::parse(value.to_string().as_bytes()) {
        Ok(ParsedContract::Complete(contract)) => Some(contract),
        _ => None,
    }
}

/// The H-typescript reply as the store accepts it.
fn reply() -> archkeel_store::Ingested {
    let mut value = read_json("tests/golden/typescript/h-typescript.json.gz");
    value["facts"]["adapter"]["version"] = json!("0");
    value["facts"]["adapter"]["code_digest"] = json!("0".repeat(64));
    value["facts"]["runtime"] = json!({"name": "rust", "version": "1.88.0", "required": ">=1.88",
                                       "requirement_state": "declared"});
    value["facts"]["source"]["git_head"] = json!("a");
    value["facts"]["source"]["dirty"] = json!(false);
    value["facts"]["provider_bindings"] = json!([]);
    value["protocol_version"] = json!("9.0.0");
    value["provider_sources"] = json!([]);
    let mut encoder = ZlibEncoder::new(Vec::new(), Compression::fast());
    encoder.write_all(value.to_string().as_bytes()).unwrap();
    archkeel_store::ingest_reply(&encoder.finish().unwrap(), 1 << 30).unwrap()
}

/// A model of the contract; `trusted` false gives the cause `Producer`, an incomplete scope.
fn model(contract: &Contract, trusted: bool) -> Model {
    let reply = reply();
    let profile = reply.reply().facts.profile.as_str().to_owned();
    let settings = Settings::new("shop".to_owned(), profile, Vec::new());
    let settings = if trusted {
        settings.with_producer(Producer::Trusted)
    } else {
        settings
    };
    Model::derive(contract, &reply, settings).unwrap()
}

fn text() -> RuleText {
    RuleText {
        title: "a rule".to_owned(),
        rationale: "a reason".to_owned(),
        decided_by: None,
        evaluated: true,
        undecided: Vec::new(),
    }
}

fn rows(outcomes: &[Outcome]) -> Vec<RuleOutcome> {
    outcomes
        .iter()
        .map(|o| RuleOutcome::evaluated(o, text()))
        .collect()
}

/// The rows of an oracle payload with no unknowns row and no diagnostic.
fn frame(rules: Vec<RuleOutcome>) -> (RunOutcome, Records) {
    let payload = Payload::decode(&bytes("E-runtime")).unwrap();
    let (mut outcome, mut records) = inputs(&payload).unwrap();
    outcome.diagnostics.clear();
    outcome.rules = rules;
    records.unknowns = Produced::Rows(Vec::new());
    (outcome, records)
}

const BOTH: [&str; 2] = ["ASSIGNMENT", "LAYOUT"];

#[test]
fn a_complete_run_whose_rules_pass_builds_a_pass_frame() {
    let contract = contract(&BOTH);
    let model = model(&contract, true);
    let (outcome, records) = frame(rows(&evaluate(&contract, &model)));
    let report = build(outcome, records, Some(&model)).unwrap();
    assert_eq!(report.source().status(), Status::Pass);
    assert_eq!(report.source().observation(), Status::Pass);
    assert!(report.source().pass().is_some_and(|pass| pass.of(&model)));
    assert!(Report::read(&report.encode().unwrap()).is_ok());
}

#[test]
fn a_contract_without_rules_passes_only_with_a_complete_scope() {
    let contract = contract(&[]);
    let complete = model(&contract, true);
    let (outcome, records) = frame(Vec::new());
    let report = build(outcome.clone(), records.clone(), Some(&complete)).unwrap();
    assert_eq!(report.source().status(), Status::Pass);
    let incomplete = model(&contract, false);
    let report = build(outcome.clone(), records.clone(), Some(&incomplete));
    let unexplained = matches!(report, Err(BuildError::Unexplained(_)));
    assert!(
        unexplained,
        "an incomplete scope is UNKNOWN and needs its row"
    );
    assert!(build(outcome, records, None).is_err());
}

#[test]
fn a_pass_of_another_model_is_refused_in_the_rule_row() {
    let contract = contract(&BOTH);
    let first = model(&contract, true);
    let second = model(&contract, true);
    let (outcome, records) = frame(rows(&evaluate(&contract, &first)));
    let wanted = BuildError::ForeignPass {
        rule: "ASSIGNMENT".to_owned(),
    };
    assert_eq!(
        build(outcome.clone(), records.clone(), Some(&second)),
        Err(wanted.clone())
    );
    assert_eq!(build(outcome, records, None), Err(wanted));
}

#[test]
fn a_pass_of_rule_a_in_the_row_of_rule_b_is_refused() {
    let contract = contract(&BOTH);
    let model = model(&contract, true);
    let outcomes = evaluate(&contract, &model);
    let mut rules = rows(&outcomes);
    let pass_of_a = RuleDecision::Decided(outcomes[0].decision().clone());
    let layout = RuleOutcome::of(
        "LAYOUT".into(),
        "root_layout".into(),
        pass_of_a,
        None,
        text(),
    );
    rules[1] = layout;
    let (outcome, records) = frame(rules);
    let wanted = BuildError::ForeignPass {
        rule: "LAYOUT".to_owned(),
    };
    assert_eq!(build(outcome, records, Some(&model)), Err(wanted));
}

#[test]
fn a_run_with_a_rule_without_its_pass_has_no_run_proof() {
    let contract = contract(&BOTH);
    let model = model(&contract, true);
    let outcomes = evaluate(&contract, &model);
    for rules in [
        rows(&outcomes[..1]),
        vec![
            rows(&outcomes[..1])[0].clone(),
            rows(&outcomes[..1])[0].clone(),
        ],
    ] {
        let (outcome, records) = frame(rules);
        let wanted = BuildError::PassWithoutProof(Some(RunGap::Rule("LAYOUT".to_owned())));
        assert_eq!(build(outcome, records, Some(&model)), Err(wanted));
    }
}

#[test]
fn the_run_proof_needs_the_scope_and_a_pass_of_each_rule() {
    let contract = contract(&BOTH);
    let complete = model(&contract, true);
    let outcomes = evaluate(&contract, &complete);
    let decisions: Vec<Decision> = outcomes.iter().map(|o| o.decision().clone()).collect();
    let proof = |m: &Model, d: &[Decision]| m.scope(|s| s.run_complete(d).map(|p| s.pass_run(p)));
    assert!(proof(&complete, &decisions).is_ok_and(|pass| pass.of(&complete)));
    let other = model(&contract, true);
    assert_eq!(proof(&other, &decisions), Err(RunGap::NotPass(0)));
    let with_fail = [decisions[0].clone(), decisions[1].clone(), Decision::fail()];
    assert_eq!(proof(&complete, &with_fail), Err(RunGap::NotPass(2)));
    let incomplete = model(&contract, false);
    let gap = proof(&incomplete, &[]);
    assert!(matches!(gap, Err(RunGap::Scope(_))), "{gap:?}");
    let empty = contract_model(&[]);
    assert!(proof(&empty, &[]).is_ok());
    assert_eq!(proof(&empty, &decisions[..1]), Err(RunGap::NotPass(0)));
}

fn contract_model(keep: &[&str]) -> Model {
    model(&contract(keep), true)
}

#[test]
fn the_observation_is_pass_only_for_a_complete_scope_of_the_model() {
    let contract = contract(&BOTH);
    let incomplete = model(&contract, false);
    let outcomes = evaluate(&contract, &incomplete);
    let payload = Payload::decode(&bytes("E-runtime")).unwrap();
    let (mut outcome, records) = inputs(&payload).unwrap();
    outcome.rules = rows(&outcomes);
    outcome.target = Target::Absent;
    let report = build(outcome, records, Some(&incomplete)).unwrap();
    assert_eq!(report.source().observation(), Status::Unknown);
    assert_eq!(report.source().status(), Status::Unknown);
}

#[test]
fn an_evaluated_row_takes_its_id_kind_and_reason_from_the_outcome() {
    let contract = contract(&BOTH);
    let incomplete = model(&contract, false);
    let outcomes = evaluate(&contract, &incomplete);
    let row = RuleOutcome::evaluated(&outcomes[0], text());
    assert_eq!(row.id(), "ASSIGNMENT");
    assert_eq!(row.kind, "complete_assignment");
    assert_eq!(row.why_unknown, Some(crate::WhyUnknown::ScopeIncomplete));
    let complete = model(&contract, true);
    let passed = RuleOutcome::evaluated(&evaluate(&contract, &complete)[1], text());
    assert_eq!((passed.id(), passed.why_unknown), ("LAYOUT", None));
}

#[test]
fn each_reason_of_the_model_has_its_row_reason() {
    use archkeel_model::{Cause, Incomplete, Input, Part, Reason, Refusal, Section, Unsupported};

    use crate::WhyUnknown::{NoReceipt, ScopeIncomplete, Undecided};
    let kind = archkeel_contract::RuleKind::LayerOrder;
    let table = [
        (Reason::NotComplete(Cause::DynamicImport), Undecided),
        (Reason::NoSubjects, NoReceipt),
        (Reason::UncitedChild("a".into()), NoReceipt),
        (Reason::Unsupported(Unsupported::Rule(kind)), NoReceipt),
        (Reason::Unsupported(Unsupported::InsideRule), NoReceipt),
        (Part::AllowedPairGap.into(), ScopeIncomplete),
        (
            Reason::Unsupported(Unsupported::Section(Section::Cycles)),
            ScopeIncomplete,
        ),
        (Reason::Unsupported(Unsupported::TreeScope), ScopeIncomplete),
        (Reason::NotComplete(Cause::PairGaps(1)), ScopeIncomplete),
        (Reason::NotComplete(Cause::Producer), ScopeIncomplete),
        (
            Reason::NotComplete(Cause::NoRuleSubjects("a".into())),
            ScopeIncomplete,
        ),
        (
            Reason::Incomplete(Incomplete::NoSourceFiles),
            ScopeIncomplete,
        ),
        (Reason::MissingInput(Input::Reply), ScopeIncomplete),
        (Reason::Refused(Refusal::ProfileMismatch), ScopeIncomplete),
        (Reason::TooManyRows("modules"), ScopeIncomplete),
    ];
    for (reason, wanted) in table {
        assert_eq!(crate::WhyUnknown::of(&reason), wanted, "{reason}");
    }
}
