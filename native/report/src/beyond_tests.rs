// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A kept pair gap through the run proof of the report (AD-384 point 7, AD-381): each rule of
//! the contract passes, because no kept gap can change what it reads, but the run does not pass,
//! and each PASS beyond the reference engine has its unknown row in the frame.

use archkeel_eval::evaluate;
use archkeel_model::{Cause, Reason, RunGap};
use serde_json::{json, Value};

use crate::frame::BEYOND_KIND;
use crate::run_tests::{contract, frame, model_of, reply_with, rows};
use crate::{build, Report, Status};

/// A kept gap `presentation.page -> main`: presentation does not require app.
fn kept_gap(reply: &mut Value) {
    let gap = json!({
        "id": "UNKNOWN-00000000000000aa", "evidence_class": "UNKNOWN", "area": "source",
        "kind": "collection_gap", "title": "pair", "subjects": ["shop.src.main_x2e_ts"],
        "evidence_ids": [], "fact_ids": [], "rule_ids": [], "provenance": [],
        "data": {"reason": "pair", "module": "shop.src.main_x2e_ts",
                 "source_module": "shop.src.presentation.page_x2e_ts"}
    });
    reply["facts"]["sections"][1]["records"] = json!([gap.clone()]);
    reply["facts"]["coverage"]["gaps"] = json!([gap]);
    reply["facts"]["coverage"]["full_scope"] = json!(false);
}

#[test]
fn a_kept_gap_that_holds_no_rule_still_holds_the_run_pass_of_the_report() {
    let contract = contract(&["ASSIGNMENT", "LAYOUT"]);
    let model = model_of(&contract, &reply_with(kept_gap), true);
    assert_eq!(model.kept_pair_gaps(), 1);
    let outcomes = evaluate(&model);
    let decisions: Vec<_> = outcomes.iter().filter_map(|o| o.decision()).collect();
    assert!(decisions
        .iter()
        .all(|d| d.passes(&model, outcomes_rule(&outcomes, d))));
    let gap = model.scope(|scope| scope.run_complete(decisions.iter().copied()).err());
    let held = matches!(
        gap,
        Some(RunGap::Scope(Reason::NotComplete(Cause::PairGaps(_))))
    );
    assert!(held, "{gap:?}");
    let (outcome, records) = frame(rows(&outcomes));
    let report = build(outcome, records, Some(&model)).unwrap();
    assert_ne!(report.source().status(), Status::Pass);
    assert!(report.source().pass().is_none());
    assert_eq!(report.source().observation(), Status::Unknown);
}

#[test]
fn each_pass_beyond_the_reference_engine_has_its_row_in_the_report_frame() {
    let contract = contract(&["ASSIGNMENT", "LAYOUT"]);
    let model = model_of(&contract, &reply_with(kept_gap), true);
    let (outcome, records) = frame(rows(&evaluate(&model)));
    let report = build(outcome, records, Some(&model)).unwrap();
    let unknowns = &report.payload().unknowns;
    assert_eq!(
        unknowns.source.len(),
        2,
        "one row for each of the two PASS rules"
    );
    let bytes = report.encode().unwrap();
    let text = String::from_utf8_lossy(&bytes);
    assert!(text.contains(BEYOND_KIND));
    assert!(Report::read(&bytes).is_ok());
    // The same rules without a kept gap pass the run and have no such row.
    let clean = model_of(&contract, &reply_with(|_| {}), true);
    let (outcome, records) = frame(rows(&evaluate(&clean)));
    let report = build(outcome, records, Some(&clean)).unwrap();
    assert_eq!(report.source().status(), Status::Pass);
    assert!(!String::from_utf8_lossy(&report.encode().unwrap()).contains(BEYOND_KIND));
}

/// The rule id of a decision among the outcomes.
fn outcomes_rule<'a>(
    outcomes: &'a [archkeel_eval::Outcome],
    decision: &archkeel_model::Decision,
) -> &'a str {
    outcomes
        .iter()
        .find(|o| o.decision() == Some(decision))
        .map_or("", |o| o.rule())
}
