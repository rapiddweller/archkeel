// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A PASS needs the model (AD-381, #1073 items 1 to 3 and 7): a rule row only with a PASS of
//! its own rule of the model, the observation only with a complete scope, the status only with
//! the run proof of L-35b. The model and the outcomes come from the frozen H-typescript reply.

use std::io::{Read, Write};

use archkeel_contract::{Contract, ParsedContract};
use archkeel_eval::{evaluate, Outcome};
use archkeel_model::{Decision, Graph, ModelTree, Producer, RunGap, Settings};
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
    value["protocol_version"] = json!("9.0.0");
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

pub(crate) fn text() -> RuleText {
    RuleText {
        title: "a rule".to_owned(),
        rationale: "a reason".to_owned(),
        decided_by: None,
        evaluated: true,
        undecided: Vec::new(),
    }
}

pub(crate) fn rows(outcomes: &[Outcome]) -> Vec<RuleOutcome> {
    outcomes
        .iter()
        .map(|o| RuleOutcome::evaluated(o, text()))
        .collect()
}

/// The rows of an oracle payload with no unknowns row and no diagnostic.
pub(crate) fn frame(rules: Vec<RuleOutcome>) -> (RunOutcome, Records) {
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
    let (outcome, records) = frame(rows(&evaluate(model.root())));
    let report = build(outcome, records, Some(&model)).unwrap();
    assert_eq!(report.source().status(), Status::Pass);
    assert_eq!(report.source().observation(), Status::Pass);
    assert!(report
        .source()
        .pass()
        .is_some_and(|pass| pass.of(model.root())));
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
    let (outcome, records) = frame(rows(&evaluate(first.root())));
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
    let outcomes = evaluate(model.root());
    let mut rules = rows(&outcomes);
    let pass_of_a = RuleDecision::Decided(outcomes[0].decision().cloned().unwrap());
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
    let outcomes = evaluate(model.root());
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
    let outcomes = evaluate(complete.root());
    let decisions: Vec<Decision> = outcomes
        .iter()
        .filter_map(|o| o.decision().cloned())
        .collect();
    let proof = |m: &ModelTree, d: &[Decision]| {
        m.root().scope(|s| s.run_complete(d).map(|p| s.pass_run(p)))
    };
    let other = model(&contract, true);
    let pass = proof(&complete, &decisions);
    assert!(pass.is_ok_and(|pass| pass.of(complete.root()) && !pass.of(other.root())));
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

fn contract_model(keep: &[&str]) -> ModelTree {
    model(&contract(keep), true)
}

#[test]
fn the_observation_is_pass_only_for_a_complete_scope_of_the_model() {
    let contract = contract(&BOTH);
    let incomplete = model(&contract, false);
    let outcomes = evaluate(incomplete.root());
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
    let outcomes = evaluate(incomplete.root());
    let row = RuleOutcome::evaluated(&outcomes[0], text());
    assert_eq!(row.id(), "ASSIGNMENT");
    assert_eq!(row.kind, "complete_assignment");
    assert_eq!(row.why_unknown, Some(crate::WhyUnknown::ScopeIncomplete));
    let complete = model(&contract, true);
    let passed = RuleOutcome::evaluated(&evaluate(complete.root())[1], text());
    assert_eq!((passed.id(), passed.why_unknown), ("LAYOUT", None));
}

#[test]
fn each_reason_of_the_model_has_its_row_reason() {
    use archkeel_model::Unsupported;
    use archkeel_model::{Cause, Held, Incomplete, Input, Part, Reason, Refusal, Section};

    use crate::WhyUnknown::{NoReceipt, ScopeIncomplete, Undecided};
    let kind = archkeel_contract::RuleKind::LayerOrder;
    let Some(held) = Held::of(std::iter::once(("a", "b"))) else {
        return assert_eq!("one held gap", "");
    };
    let table = [
        (Reason::NotComplete(Cause::Undecided(1)), Undecided),
        (Reason::NotComplete(Cause::DynamicImport), NoReceipt),
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
        (Reason::NotComplete(Cause::PairGaps(held)), ScopeIncomplete),
        (Reason::NotComplete(Cause::Receipt("a")), NoReceipt),
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

#[test]
fn a_pass_row_without_its_receipt_is_refused() {
    let contract = contract(&BOTH);
    let model = model(&contract, true);
    let outcomes = evaluate(model.root());
    let no_receipt = RuleText {
        evaluated: false,
        ..text()
    };
    let mut rules = rows(&outcomes);
    rules[0] = RuleOutcome::evaluated(&outcomes[0], no_receipt);
    let (outcome, records) = frame(rules);
    let wanted = BuildError::PassWithoutReceipt {
        rule: "ASSIGNMENT".to_owned(),
    };
    assert_eq!(build(outcome, records, Some(&model)), Err(wanted));
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

/// B1 of the review of #1080: the reply imports `transport.client`, which the contract does not
/// declare. Before the fix, `evaluate(&forged, &model)` read the FORGE rule of the caller and
/// gave a PASS of EXTERNAL-COMPLETE bound to `model`, and the run proof took it. Now `evaluate`
/// reads only `model.contract()`.
#[test]
fn a_rule_of_another_contract_cannot_make_a_run_pass() {
    let reply = reply_with(undeclared_import);
    let own = contract(&["EXTERNAL-COMPLETE"]);
    let model = model_of(&own, &reply, true);
    let decisions: Vec<Decision> = evaluate(model.root())
        .iter()
        .filter_map(|o| o.decision().cloned())
        .collect();
    assert_eq!(decisions, vec![Decision::fail()]);
    let forge = json!({"id": "FORGE", "kind": "external_dependency_scope",
        "dependency": "transport.client", "allowed_sources": ["shop"],
        "rationale": "a forged declaration", "provenance": ["docs/architecture/shop.md"],
        "decided_by": "architect"});
    let forged = parsed(&["EXTERNAL-COMPLETE"], vec![forge]).unwrap();
    let other = model_of(&forged, &reply, true);
    let foreign: Vec<Decision> = evaluate(other.root())
        .iter()
        .filter(|o| o.rule() == "EXTERNAL-COMPLETE")
        .filter_map(|o| o.decision().cloned())
        .collect();
    assert!(foreign[0].passes(other.root(), "EXTERNAL-COMPLETE"));
    let run = model
        .root()
        .scope(|s| s.run_complete(&foreign).map(|p| s.pass_run(p)));
    assert_eq!(run, Err(RunGap::NotPass(0)));
    let rows = frame(rows(&evaluate(other.root())[..1]));
    let wanted = BuildError::ForeignPass {
        rule: "EXTERNAL-COMPLETE".to_owned(),
    };
    assert_eq!(build(rows.0, rows.1, Some(&model)), Err(wanted));
}

pub(crate) fn allow() -> Value {
    json!({"id": "ALLOW", "kind": "allowed_dependency", "source": "shop.src.data",
        "target": "shop.src.domain", "rationale": "data reads the domain values",
        "provenance": ["docs/architecture/shop.md"], "decided_by": "architect"})
}

/// S1 of the review of #1080: a declaration has no verdict, so a contract of declarations only
/// passes with a complete scope, and its rows show DECLARATION.
#[test]
fn a_contract_with_only_declaration_rules_passes() {
    let contract = parsed(&[], vec![allow()]).unwrap();
    let model = model(&contract, true);
    let outcomes = evaluate(model.root());
    assert!(outcomes.iter().all(|o| o.decision().is_none()));
    let (outcome, records) = frame(rows(&outcomes));
    let report = build(outcome, records, Some(&model)).unwrap();
    assert_eq!(report.source().status(), Status::Pass);
    assert_eq!(report.source().rule("ALLOW"), Some(None));
}

/// F3 of the review of #1080: only a declaration rule of the model shows DECLARATION.
#[test]
fn a_fail_rule_shown_as_a_declaration_is_refused() {
    let contract = parsed(&BOTH, vec![allow()]).unwrap();
    let model = model(&contract, true);
    assert!(RuleOutcome::declaration(model.root(), "ASSIGNMENT".into(), text()).is_none());
    assert!(RuleOutcome::declaration(model.root(), "ALLOW".into(), text()).is_some());
    let mut rules = rows(&evaluate(model.root()));
    rules[0] = RuleOutcome::of(
        "ASSIGNMENT".into(),
        "complete_assignment".into(),
        RuleDecision::Declaration,
        None,
        text(),
    );
    let (outcome, records) = frame(rules);
    let wanted = BuildError::ForeignDeclaration {
        rule: "ASSIGNMENT".to_owned(),
    };
    assert_eq!(build(outcome, records, Some(&model)), Err(wanted));
}

/// S1, F3: a declaration row does not stand in for a rule without its PASS.
#[test]
fn a_declaration_row_cannot_stand_in_for_a_missing_pass() {
    let contract = parsed(&BOTH, vec![allow()]).unwrap();
    let model = model(&contract, true);
    let outcomes = evaluate(model.root());
    let allow_row = RuleOutcome::declaration(model.root(), "ALLOW".into(), text()).unwrap();
    let (outcome, records) = frame(vec![rows(&outcomes)[0].clone(), allow_row]);
    let wanted = BuildError::PassWithoutProof(Some(RunGap::Rule("LAYOUT".to_owned())));
    assert_eq!(build(outcome, records, Some(&model)), Err(wanted));
    let (outcome, records) = frame(rows(&outcomes));
    let report = build(outcome, records, Some(&model)).unwrap();
    assert_eq!(report.source().status(), Status::Pass);
}

/// F2 of the review of #1080: each kind word is the word of the contract grammar, and the
/// grammar has 22 kinds.
#[test]
fn each_kind_word_reads_back_as_its_kind() {
    let words = "call_owner forbidden_call_argument catalog_argument catalog_use \
        forbidden_effect_under_condition forbidden_dependency allowed_dependency \
        forbidden_construct source_ownership external_dependency_scope complete_assignment \
        root_layout complete_external_scope complete_requires layer_order no_component_cycles \
        interface_boundary sibling_isolation symbol_placement boundary_types \
        bounded_numeric_operand protocol_declarations";
    let words: Vec<&str> = words.split_whitespace().collect();
    assert_eq!(words.len(), 22);
    for word in words {
        let kind = serde_json::from_value::<archkeel_contract::RuleKind>(json!(word)).unwrap();
        assert_eq!(crate::kind::word(kind), word);
    }
}
