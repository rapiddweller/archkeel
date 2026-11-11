// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Each step of the status rule of AD-361 point 4 and each row rule of point 5, on copies of
//! oracle payloads.

use crate::corpus_tests::bytes;
use crate::{
    status_of, unexplained, Code, Payload, Problem, ReadError, Report, Status, Unexplained,
    UnknownReason, UnknownSource,
};

fn payload(name: &str) -> Payload {
    Payload::decode(&bytes(name)).unwrap()
}

fn with_diagnostic(mut p: Payload, reason: UnknownReason) -> Payload {
    p.run.observation = Status::Unknown;
    let u = &mut p.unknowns;
    u.source.push(Code::of(UnknownSource::Diagnostic));
    u.reason.push(Code::of(reason));
    u.kind.push(0);
    u.node.push(0);
    u.rule.push(-1);
    u.detail.push(0);
    p
}

#[test]
fn a_revoking_diagnostic_of_an_incomplete_run_turns_a_violation_into_unknown() {
    let fail = payload("python-newer-syntax-demo");
    assert_eq!(status_of(&fail), Status::Fail);
    for reason in [
        UnknownReason::RuntimeMismatch,
        UnknownReason::IncomparableRuntime,
        UnknownReason::ContractInvalid,
    ] {
        assert_eq!(
            status_of(&with_diagnostic(fail.clone(), reason)),
            Status::Unknown
        );
    }
    let kept = with_diagnostic(fail, UnknownReason::IncompleteScan);
    assert_eq!(status_of(&kept), Status::Fail);
}

#[test]
fn a_revoking_diagnostic_of_a_complete_run_keeps_the_fail() {
    let mut p = with_diagnostic(
        payload("python-newer-syntax-demo"),
        UnknownReason::RuntimeMismatch,
    );
    p.run.observation = Status::Pass;
    assert_eq!(status_of(&p), Status::Fail);
}

#[test]
fn an_undecided_position_of_a_pass_rule_gives_unknown() {
    let mut p = payload("H-uml-dart");
    assert_eq!(status_of(&p), Status::Pass);
    p.rules[0].undecided = 1;
    assert_eq!(status_of(&p), Status::Unknown);
}

#[test]
fn no_target_comes_first() {
    let mut p = payload("python-newer-syntax-demo");
    p.run.target = false;
    assert_eq!(status_of(&p), Status::Unknown);
}

#[test]
fn a_run_without_target_needs_its_run_row() {
    let mut p = payload("explore-N-explore");
    let row = p
        .unknowns
        .source
        .iter()
        .position(|s| s.is(UnknownSource::Run))
        .unwrap();
    let u = &mut p.unknowns;
    u.source.remove(row);
    u.reason.remove(row);
    u.kind.remove(row);
    u.node.remove(row);
    u.rule.remove(row);
    u.detail.remove(row);
    p.summary.counts.unknowns -= 1;
    assert_eq!(
        unexplained(&p, Status::Unknown),
        vec![Unexplained::NoTargetWithoutRunRow]
    );
    let result = Report::read(&p.encode().unwrap());
    let wanted = Problem::Unexplained(Unexplained::NoTargetWithoutRunRow);
    assert!(matches!(&result, Err(ReadError::Check(found)) if found.contains(&wanted)));
}

#[test]
fn a_rule_that_one_row_cites_twice_counts_once() {
    let mut p = payload("variant-decision-conflict");
    let id = p.violation_rules[0];
    p.violation_rules.insert(0, id);
    for end in &mut p.violations.rules_end {
        *end += 1;
    }
    assert!(Report::read(&p.encode().unwrap()).is_ok());
}
