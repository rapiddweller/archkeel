// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The engine frame of the core takes its status and its rule verdicts only from `rule` (AD-388,
//! #1073 item 4). The model comes from the frozen H-typescript reply (`run_tests`).

use archkeel_model::{Input, Reason, UmlGap, UmlTarget, Unsupported};
use serde_json::{json, Value};

use super::{fits, rule, Named, RuleReasons};
use crate::run_tests::{allow, contract, model, model_of, parsed, reply_with, undeclared_import};
use crate::{BuildError, FrameError, RuleVerdict, Status, Unexplained};

const BOTH: [&str; 2] = ["ASSIGNMENT", "LAYOUT"];

#[test]
fn static_html_keeps_each_status_of_its_typed_ruling() {
    let passed = model(&contract(&BOTH), true);
    let unknown = model(&contract(&BOTH), false);
    let reply = reply_with(undeclared_import);
    let failed = model_of(&contract(&["EXTERNAL-COMPLETE"]), &reply, true);
    for (tree, status) in [(&passed, "PASS"), (&failed, "FAIL"), (&unknown, "UNKNOWN")] {
        let ruling = rule(Ok(tree), Named::default()).unwrap().with_html(true);
        let frame = ruling.frame(&json!({})).unwrap().into_bytes();
        let frame: Value = serde_json::from_slice(&frame).unwrap();
        assert_eq!(frame["html"]["status"], frame["status"]);
        assert_eq!(frame["status"], status);
        assert!(frame["html"]["document"]
            .as_str()
            .unwrap()
            .contains(&format!("<h1>Verdict: {status}</h1>")));
        assert_eq!(
            ruling.frame(&json!({"html": "forged"})),
            Err(FrameError::RulingKey("html".to_owned()))
        );
    }
}

#[test]
fn the_refused_fixture_has_one_golden_static_page() {
    let reason = Reason::MissingInput(Input::Reply);
    let ruling = rule(
        Err(&reason),
        Named {
            contract: Some("fixture refused".to_owned()),
            ..Named::default()
        },
    )
    .unwrap()
    .with_html(true);
    let bytes = ruling.frame(&json!({
        "engine": "archkeel-core CODE-DIGEST", "locations": {}, "collection_gaps": [],
        "contract_digest": null, "sections": {}, "unsupported": {"sections": {}, "report": null},
        "self_test": {"contract": {"not_read": "fixture refused"},
            "reply": {"absent": "fixture refused"}, "collect": {"refused": "fixture refused"}}
    })).unwrap().into_bytes();
    let frame: Value = serde_json::from_slice(&bytes).unwrap();
    // AD-496: the style (fonts, tokens, components) and the theme script are files of the design
    // system; their bytes are checked by their own tests. The golden keeps the rest of the page.
    let page = frame["html"]["document"].as_str().unwrap();
    let cut = |text: &str, open: &str, close: &str| {
        let (head, rest) = text.split_once(open).unwrap();
        let (_, tail) = rest.split_once(close).unwrap();
        format!(
            "{head}{open}[{}]{close}{tail}",
            open.trim_matches(|c| c == '<' || c == '>')
        )
    };
    let skeleton = cut(&cut(page, "<script>", "</script>"), "<style>", "</style>");
    assert_eq!(skeleton, include_str!("../testdata/refused.html"));
}

#[test]
fn a_frame_without_rules_is_unknown_and_names_the_contract() {
    for trusted in [true, false] {
        let model = model(&contract(&[]), trusted);
        let ruling = rule(Ok(&model), Named::default()).unwrap();
        let bytes = ruling.frame(&json!({})).unwrap().into_bytes();
        let value: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(value["status"], "UNKNOWN");
        assert_eq!(value["rules"], json!({}));
        assert_eq!(
            value["unsupported"]["rules"],
            "unsupported: contract has no decided rule"
        );
        assert!(!ruling.unsupported().is_empty());
        assert!(ruling.decided().pass().is_none());
    }
}

#[test]
fn a_declaration_only_frame_has_no_decision_and_no_run_pass() {
    for trusted in [true, false] {
        let tree = model(&parsed(&[], vec![allow()]).unwrap(), trusted);
        let ruling = rule(Ok(&tree), Named::default()).unwrap();
        let bytes = ruling.frame(&json!({})).unwrap().into_bytes();
        let value: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(value["status"], "UNKNOWN");
        assert_eq!(value["rules"]["ALLOW"][1], "DECLARATION");
        assert!(!ruling.unsupported().is_empty());
        assert!(ruling.decided().pass().is_none());
    }
}

#[test]
fn a_repeated_outcome_is_refused_before_a_frame_can_be_made() {
    let tree = model(&contract(&["ASSIGNMENT", "COMPONENT-CYCLES"]), true);
    let model = tree.root();
    for outcome in archkeel_eval::evaluate(model) {
        let mut rows = super::Rows::default();
        let mut gaps = Default::default();
        rows.add(&outcome, model, None, &mut gaps).unwrap();
        assert_eq!(
            rows.add(&outcome, model, None, &mut gaps),
            Err(BuildError::DuplicateRule {
                rule: outcome.rule().to_owned()
            })
        );
    }
}

fn frame(ruling: &super::Ruling) -> Value {
    serde_json::to_value(ruling).unwrap_or(Value::Null)
}

#[test]
fn a_complete_run_whose_rules_pass_writes_pass_with_the_run_proof() {
    let model = model(&contract(&BOTH), true);
    let ruling = rule(Ok(&model), Named::default()).unwrap();
    assert_eq!(ruling.decided().status(), Status::Pass);
    assert!(ruling
        .decided()
        .pass()
        .is_some_and(|pass| pass.of(model.root())));
    assert_eq!(
        frame(&ruling),
        json!({"protocol": "archkeel-core-frame-1", "status": "PASS", "scope": "complete", "explained": {}, "violations": {},
               "details": {}, "unknown_kinds": {},
               "beyond": {},
               "rules": {"ASSIGNMENT": ["complete_assignment", "PASS"],
                         "LAYOUT": ["root_layout", "PASS"]}})
    );
    assert_eq!(ruling.unsupported(), &RuleReasons::Each(Default::default()));
}

#[test]
fn an_incomplete_scope_writes_unknown_rules_with_their_reasons() {
    let model = model(&contract(&BOTH), false);
    let ruling = rule(Ok(&model), Named::default()).unwrap();
    let value = frame(&ruling);
    assert_eq!(value["status"], "UNKNOWN");
    assert_ne!(value["scope"], "complete");
    assert_eq!(value["rules"]["ASSIGNMENT"][1], "UNKNOWN");
    assert!(value["explained"]["ASSIGNMENT"]
        .as_str()
        .is_some_and(|why| !why.is_empty()));
    assert!(ruling.decided().pass().is_none());
}

#[test]
fn a_fail_rule_writes_its_violations_and_a_gap_does_not_hide_it() {
    let reply = reply_with(undeclared_import);
    let model = model_of(&contract(&["EXTERNAL-COMPLETE"]), &reply, true);
    let named = Named {
        contract: None,
        rules: [(
            "inside/R".to_owned(),
            Reason::Unsupported(Unsupported::InsideRule),
        )]
        .into(),
        hold: None,
        uml: None,
    };
    let value = frame(&rule(Ok(&model), named).unwrap());
    assert_eq!(value["status"], "FAIL");
    assert_eq!(value["rules"]["EXTERNAL-COMPLETE"][1], "FAIL");
    assert!(value["violations"]["EXTERNAL-COMPLETE"]
        .as_u64()
        .is_some_and(|count| count > 0));
}

/// Each gap of the core holds back a PASS: a named rule, a reason for the whole
/// contract and the hold of a mounted root. The rows of the other rules stay.
#[test]
fn each_gap_of_the_core_holds_back_a_pass() {
    let model = model(&contract(&BOTH), true);
    let gap = Reason::Unsupported(Unsupported::InsideRule);
    let gaps = [
        Named {
            rules: [("inside/R".to_owned(), gap.clone())].into(),
            ..Named::default()
        },
        Named {
            contract: Some("refused: no contract".to_owned()),
            ..Named::default()
        },
        Named {
            hold: Some(Reason::Unsupported(Unsupported::TreeScope)),
            ..Named::default()
        },
    ];
    for named in gaps {
        let ruling = rule(Ok(&model), named.clone()).unwrap();
        assert_eq!(ruling.decided().status(), Status::Unknown, "{named:?}");
        assert!(ruling.decided().pass().is_none());
    }
    let whole = Named {
        contract: Some("refused: no contract".to_owned()),
        ..Named::default()
    };
    let ruling = rule(Ok(&model), whole).unwrap();
    assert_eq!(frame(&ruling)["rules"], json!({}));
    assert_eq!(
        ruling.unsupported(),
        &RuleReasons::All("refused: no contract".to_owned())
    );
    let held = Named {
        hold: Some(Reason::Unsupported(Unsupported::TreeScope)),
        ..Named::default()
    };
    let ruling = rule(Ok(&model), held).unwrap();
    assert_eq!(frame(&ruling)["rules"], json!({}));
    let each = match ruling.unsupported() {
        RuleReasons::Each(each) => each.len(),
        RuleReasons::All(_) => 0,
    };
    assert_eq!(each, 2);
}

#[test]
fn an_unported_kind_is_a_named_gap_and_never_a_row() {
    let model = model(&contract(&["ASSIGNMENT", "COMPONENT-CYCLES"]), true);
    let ruling = rule(Ok(&model), Named::default()).unwrap();
    assert_eq!(ruling.decided().status(), Status::Unknown);
    let value = frame(&ruling);
    assert_eq!(value["rules"]["ASSIGNMENT"][1], "PASS");
    assert!(value["rules"].get("COMPONENT-CYCLES").is_none());
    assert!(!ruling.unsupported().is_empty());
}

#[test]
fn a_run_without_a_model_is_unknown_with_the_reason_as_its_scope() {
    let reason = Reason::MissingInput(Input::Reply);
    let ruling = rule(Err(&reason), Named::default()).unwrap();
    assert_eq!(ruling.decided().status(), Status::Unknown);
    assert_eq!(frame(&ruling)["scope"], reason.to_string());
}

/// F4 of AD-381: a permission declaration has no verdict, and the run proof skips it.
#[test]
fn a_declaration_writes_its_row_and_holds_back_no_pass() {
    let model = model(&parsed(&["ASSIGNMENT"], vec![allow()]).unwrap(), true);
    let ruling = rule(Ok(&model), Named::default()).unwrap();
    assert_eq!(ruling.decided().status(), Status::Pass);
    assert_eq!(frame(&ruling)["rules"]["ALLOW"][1], "DECLARATION");
    assert_eq!(ruling.decided().rule("ALLOW"), Some(None));
}

/// L-23: a FAIL row without a violation and a row of another verdict with one are refused.
#[test]
fn a_fail_without_violations_and_another_verdict_with_violations_are_refused() {
    let fail = Err(BuildError::Unexplained(vec![
        Unexplained::FailWithoutViolation,
    ]));
    assert_eq!(fits(RuleVerdict::Fail, 0, "R"), fail);
    assert_eq!(fits(RuleVerdict::Fail, 2, "R"), Ok(()));
    for verdict in [
        RuleVerdict::Pass,
        RuleVerdict::Unknown,
        RuleVerdict::Declaration,
    ] {
        assert_eq!(fits(verdict, 0, "R"), Ok(()));
        let mismatch = Err(BuildError::ReasonMismatch {
            rule: "R".to_owned(),
        });
        assert_eq!(fits(verdict, 1, "R"), mismatch);
    }
}

/// Review N1 of #1090: the engine frame has one status, the ruling's. A part of the core with a
/// key of the ruling is refused, and the ruling writes `unsupported.rules`.
#[test]
fn the_frame_writes_the_keys_of_the_ruling_one_time() {
    let model = model(&contract(&BOTH), true);
    let ruling = rule(Ok(&model), Named::default()).unwrap();
    let parts = json!({"engine": "e", "sections": {}, "unsupported": {"report": "r"}});
    let bytes = ruling.frame(&parts).unwrap().into_bytes();
    let value: Value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
    assert_eq!(value["status"], "PASS");
    assert_eq!(value["engine"], "e");
    assert_eq!(value["unsupported"], json!({"rules": {}, "report": "r"}));
    for (key, part) in [
        ("status", json!({"status": "PASS"})),
        ("scope", json!({"scope": "complete"})),
        ("beyond", json!({"beyond": {}})),
        ("unsupported.rules", json!({"unsupported": {"rules": {}}})),
    ] {
        assert_eq!(
            ruling.frame(&part),
            Err(FrameError::RulingKey(key.to_owned()))
        );
    }
    assert_eq!(ruling.frame(&json!([1])), Err(FrameError::NotAnObject));
}

const UML: &str = "UML-TARGET-a2e40c5592b1b06a";
const COMPARED: UmlGap = UmlGap::NotCompared {
    entities: 2,
    relationships: 1,
    scopes: 0,
};

fn uml(gap: UmlGap) -> Named {
    Named {
        uml: Some((UML.to_owned(), UmlTarget::Gap(gap))),
        ..Named::default()
    }
}

/// AD-470: the UML target row is UNKNOWN with its cause and `no_receipt`. It holds back the PASS
/// of a run whose rules pass, and it is a row, not a gap of the frame.
#[test]
fn a_uml_target_is_an_unknown_row_that_holds_back_a_pass() {
    let model = model(&contract(&BOTH), true);
    let ruling = rule(Ok(&model), uml(COMPARED)).unwrap();
    assert_eq!(ruling.decided().status(), Status::Unknown);
    assert!(ruling.decided().pass().is_none());
    assert_eq!(ruling.decided().rule(UML), None);
    let value = frame(&ruling);
    assert_eq!(value["rules"][UML], json!(["uml_target", "UNKNOWN"]));
    assert_eq!(value["rules"]["ASSIGNMENT"][1], "PASS");
    assert_eq!(
        value["explained"][UML],
        "the UML target: the core does not compare 2 entities, 1 relationships and 0 scopes \
         with the source facts"
    );
    assert_eq!(value["unknown_kinds"][UML], "no_receipt");
    assert_eq!(ruling.unsupported(), &RuleReasons::Each(Default::default()));
}

/// A contract with only a UML target has one row that explains its UNKNOWN status, so the core
/// does not name the contract as one without a decided rule.
#[test]
fn a_contract_with_only_a_uml_target_has_its_row_and_no_contract_gap() {
    let model = model(&contract(&[]), true);
    let ruling = rule(Ok(&model), uml(UmlGap::Empty)).unwrap();
    let value = frame(&ruling);
    assert_eq!(value["status"], "UNKNOWN");
    assert_eq!(value["rules"], json!({UML: ["uml_target", "UNKNOWN"]}));
    assert_eq!(
        value["explained"][UML],
        "the UML target: it declares no entity, relationship or scope"
    );
    assert_eq!(ruling.unsupported(), &RuleReasons::Each(Default::default()));
}

/// Without a model, the UML target names the reason of the run as a gap; with a reason for the
/// whole contract, the frame has no row at all.
#[test]
fn a_uml_target_without_a_decided_model_is_a_gap_and_never_a_row() {
    let reason = Reason::MissingInput(Input::Reply);
    let ruling = rule(Err(&reason), uml(COMPARED)).unwrap();
    assert_eq!(frame(&ruling)["rules"], json!({}));
    let expected = [(UML.to_owned(), reason.to_string())].into();
    assert_eq!(ruling.unsupported(), &RuleReasons::Each(expected));
    let model = model(&contract(&BOTH), true);
    let whole = Named {
        contract: Some("refused: no contract".to_owned()),
        ..uml(COMPARED)
    };
    let ruling = rule(Ok(&model), whole).unwrap();
    assert_eq!(frame(&ruling)["rules"], json!({}));
    assert_eq!(ruling.decided().status(), Status::Unknown);
}

/// A UML target id that a rule of the contract also has is refused, as a repeated rule is.
#[test]
fn a_uml_target_with_the_id_of_a_rule_is_refused() {
    let model = model(&contract(&BOTH), true);
    let named = Named {
        uml: Some(("ASSIGNMENT".to_owned(), UmlTarget::Gap(COMPARED))),
        ..Named::default()
    };
    let refused = Err(BuildError::DuplicateRule {
        rule: "ASSIGNMENT".to_owned(),
    });
    assert_eq!(rule(Ok(&model), named).map(|_| ()), refused);
}
