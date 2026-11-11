// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The findings of the review of #1056: hostile numbers, the byte budget, a PASS without its
//! parts, a FAIL rule without a violation row, a reason that its verdict cannot have, and the
//! rules that no planted payload held.

use crate::corpus_tests::bytes;
use crate::{
    Code, EdgeTarget, Gap, Level, Payload, Problem, ReadError, Relation, Report, RuleReason,
    RuleVerdict, Status, Unexplained, MAX_BYTES,
};

fn payload(name: &str) -> Payload {
    Payload::decode(&bytes(name)).unwrap()
}

/// The problems of a planted payload; the bytes must stay canonical.
fn refused(planted: &Payload) -> Vec<Problem> {
    let result = Report::read(&planted.encode().unwrap());
    assert!(matches!(result, Err(ReadError::Check(_))), "{result:?}");
    match result {
        Err(ReadError::Check(found)) => found,
        _ => Vec::new(),
    }
}

fn overflow(found: &[Problem], wanted: &str) -> bool {
    found
        .iter()
        .any(|f| matches!(f, Problem::Count { name, rows: u64::MAX, .. } if *name == wanted))
}

#[test]
fn an_undecided_sum_above_u64_is_a_named_count_and_no_abort() {
    let mut p = payload("variant-decision-conflict");
    p.rules[0].undecided = u64::MAX;
    p.rules[1].undecided = 1;
    assert!(overflow(&refused(&p), "undecided"));
}

#[test]
fn an_omitted_sum_above_u64_is_a_named_count_and_no_abort() {
    let mut p = payload("variant-forbidden-dependency-pair");
    let modules: Vec<usize> = (0..p.edges.level.len())
        .filter(|row| p.edges.level[*row].is(Level::Module))
        .collect();
    p.edges.omitted[modules[0]] = u64::MAX;
    p.edges.omitted[modules[1]] = 1;
    assert!(overflow(&refused(&p), "crossing_names"));
}

#[test]
fn a_not_ranked_sum_above_u64_is_a_named_count_and_no_abort() {
    let mut p = payload("variant-package-cycle-rollup-only");
    let mut extra = p.run.not_ranked[0].clone();
    p.run.not_ranked[0].count = u64::MAX;
    extra.count = 1;
    p.run.not_ranked.push(extra);
    assert!(overflow(&refused(&p), "run.not_ranked"));
}

#[test]
fn a_payload_budget_other_than_the_version_budget_is_refused() {
    for max_bytes in [0, 1, MAX_BYTES - 1, MAX_BYTES + 1] {
        let mut p = payload("H-uml-dart");
        p.run.payload_budget.max_bytes = max_bytes;
        assert_eq!(refused(&p), vec![Problem::PayloadBudget], "{max_bytes}");
    }
}

#[test]
fn input_above_the_budget_is_refused_before_the_parse() {
    let large = vec![b' '; usize::try_from(MAX_BYTES).unwrap() + 1];
    let result = Report::read(&large);
    assert!(matches!(result, Err(ReadError::TooLarge { bytes }) if bytes == MAX_BYTES + 1));
}

fn not_carried(p: &mut Payload, relations: &[Relation]) {
    p.run
        .not_carried
        .extend(relations.iter().copied().map(Code::of));
    p.run.not_carried.sort();
}

#[test]
fn a_pass_without_the_graph_is_refused() {
    let mut p = payload("H-uml-dart");
    assert_eq!(p.summary.status, Status::Pass);
    let e = &mut p.edges;
    for column in [&mut e.names, &mut e.sites, &mut e.omitted, &mut e.via_end] {
        column.clear();
    }
    e.level.clear();
    e.from.clear();
    e.to.clear();
    e.target.clear();
    e.rationale.clear();
    p.via.clear();
    p.crossings = crate::Crossings::default();
    not_carried(&mut p, &[Relation::Imports, Relation::Reexports]);
    let found = refused(&p);
    assert!(
        found.contains(&Problem::Unexplained(Unexplained::PassWithoutPart)),
        "{found:?}"
    );
}

#[test]
fn each_part_that_a_pass_needs_is_refused_alone_also_for_a_pass_observation() {
    for name in ["H-uml-dart", "G-dart"] {
        for relation in crate::PASS_NEEDS {
            let mut p = payload(name);
            assert_eq!(p.run.observation, Status::Pass);
            not_carried(&mut p, &[relation]);
            let wanted = Problem::Unexplained(Unexplained::PassWithoutPart);
            assert!(refused(&p).contains(&wanted), "{name} {relation:?}");
        }
    }
}

#[test]
fn a_fail_rule_without_a_violation_row_is_refused() {
    let mut p = payload("python-newer-syntax-demo");
    let rule = p
        .rules
        .iter_mut()
        .find(|r| r.verdict == RuleVerdict::Pass)
        .unwrap();
    rule.verdict = RuleVerdict::Fail;
    rule.reason = RuleReason::Violations;
    let id = rule.id.clone();
    p.summary.counts.rules_pass -= 1;
    p.summary.counts.rules_fail += 1;
    assert_eq!(
        refused(&p),
        vec![Problem::FailRuleWithoutViolation { rule: id }]
    );
}

#[test]
fn a_reason_that_the_verdict_cannot_have_is_refused() {
    let mut p = payload("H-uml-dart");
    p.rules[0].reason = RuleReason::NoReceipt;
    let id = p.rules[0].id.clone();
    assert_eq!(refused(&p), vec![Problem::VerdictReason { rule: id }]);
}

#[test]
fn a_flag_above_one_and_offsets_out_of_order_stop_the_check() {
    let mut p = payload("variant-forbidden-dependency-pair");
    p.units.is_static[0] = 2;
    assert!(refused(&p).contains(&Problem::FlagRange {
        column: "units.static"
    }));
    let mut p = payload("variant-decision-conflict");
    p.violations.rules_end.swap(0, 1);
    let wanted = Problem::OffsetEnd {
        column: "violations.rules_end",
    };
    assert!(refused(&p).contains(&wanted));
}

#[test]
fn a_major_version_other_than_2_is_refused() {
    let mut p = payload("H-uml-dart");
    p.schema_version = "3.0.0".to_owned();
    assert_eq!(refused(&p), vec![Problem::SchemaVersion]);
}

#[test]
fn a_gap_that_the_gap_list_does_not_hold_is_refused() {
    let mut p = payload("variant-forbidden-dependency-pair");
    p.gaps.retain(|row| !row.gap.is(Gap::Budgets));
    p.summary.counts.gaps -= 1;
    assert_eq!(refused(&p), vec![Problem::GapNotListed]);
}

#[test]
fn a_measured_value_without_budget_must_name_g_budgets() {
    let mut p = payload("variant-forbidden-dependency-pair");
    let row = p.measures.gap.iter().position(|g| *g == 6).unwrap();
    p.measures.gap[row] = i64::from(Code::of(Gap::Trend).value());
    let found = refused(&p);
    assert!(
        found.contains(&Problem::MeasureWithoutBudgetGap { row }),
        "{found:?}"
    );
}

#[test]
fn a_package_edge_with_a_target_is_refused() {
    let mut p = payload("variant-forbidden-dependency-pair");
    let edge = p
        .edges
        .level
        .iter()
        .position(|l| l.is(Level::Package))
        .unwrap();
    p.edges.target[edge] = Code::of(EdgeTarget::Declared);
    assert!(refused(&p).contains(&Problem::EdgeTarget { edge }));
}
