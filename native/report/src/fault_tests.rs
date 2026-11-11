// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Faults planted in copies of oracle payloads. The bytes stay canonical, so only the check can
//! refuse them, and each refusal names its rule.

use crate::corpus_tests::bytes;
use crate::{
    Code, Payload, Permission, Problem, ReadError, Report, RuleVerdict, Status, Unexplained,
    UnknownReason, UnknownSource,
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

fn drop_row<T>(column: &mut Vec<T>, row: usize) {
    column.remove(row);
}

#[test]
fn a_fail_without_its_violation_row_is_refused() {
    let mut p = payload("python-newer-syntax-demo");
    assert_eq!(p.summary.status, Status::Fail);
    let v = &mut p.violations;
    let row = 0;
    let (rules, subjects, evidence) = (v.rules_end[row], v.subjects_end[row], v.evidence_end[row]);
    p.violation_rules.drain(..usize::try_from(rules).unwrap());
    p.violation_subjects
        .drain(..usize::try_from(subjects).unwrap());
    p.violation_evidence
        .drain(..usize::try_from(evidence).unwrap());
    drop_row(&mut v.kind, row);
    drop_row(&mut v.rules_end, row);
    drop_row(&mut v.subjects_end, row);
    drop_row(&mut v.source_module, row);
    drop_row(&mut v.target_module, row);
    drop_row(&mut v.symbol, row);
    drop_row(&mut v.source_component, row);
    drop_row(&mut v.target_component, row);
    drop_row(&mut v.evidence_end, row);
    drop_row(&mut v.path, row);
    drop_row(&mut v.line, row);
    drop_row(&mut v.node, row);
    let found = refused(&p);
    assert!(found.contains(&Problem::Unexplained(Unexplained::FailWithoutViolation)));
    assert!(found.iter().any(|f| matches!(
        f,
        Problem::Status {
            stated: Status::Fail,
            ..
        }
    )));
}

#[test]
fn a_flipped_permission_is_refused() {
    let base = payload("variant-forbidden-dependency-pair");
    for (row, status) in base.permissions.status.iter().enumerate() {
        for flipped in [
            Permission::Allowed,
            Permission::Forbidden,
            Permission::Undecided,
        ] {
            if status.is(flipped) {
                continue;
            }
            let mut p = base.clone();
            p.permissions.status[row] = Code::of(flipped);
            let found = refused(&p);
            let named = found.iter().any(|f| {
                matches!(
                    f,
                    Problem::EdgeTarget { .. }
                        | Problem::AllowedWithoutEdge { .. }
                        | Problem::PermissionRule { .. }
                )
            });
            assert!(named, "row {row} to {flipped:?}: {found:?}");
        }
    }
}

#[test]
fn a_removed_undecided_position_is_refused() {
    let mut p = payload("H-typescript");
    let rule = p.rules.iter_mut().find(|r| r.undecided > 0).unwrap();
    rule.undecided -= 1;
    let found = refused(&p);
    assert!(found.iter().any(|f| matches!(
        f,
        Problem::Count {
            name: "undecided",
            ..
        }
    )));
}

#[test]
fn a_pass_with_a_run_row_is_refused() {
    let mut p = payload("F-architecture-tests");
    assert_eq!(p.summary.status, Status::Pass);
    let u = &mut p.unknowns;
    u.source.push(Code::of(UnknownSource::Run));
    u.reason.push(Code::of(UnknownReason::NoTarget));
    u.kind.push(0);
    u.node.push(0);
    u.rule.push(-1);
    u.detail.push(0);
    p.summary.counts.unknowns += 1;
    assert_eq!(refused(&p), vec![Problem::RunRowWithTarget]);
}

#[test]
fn a_wrong_count_in_the_head_is_refused() {
    for name in [
        "modules",
        "violations",
        "gaps",
        "rules_pass",
        "forbidden_edges",
    ] {
        let mut p = payload("variant-forbidden-dependency-pair");
        let c = &mut p.summary.counts;
        let cell = match name {
            "modules" => &mut c.modules,
            "violations" => &mut c.violations,
            "gaps" => &mut c.gaps,
            "rules_pass" => &mut c.rules_pass,
            _ => &mut c.forbidden_edges,
        };
        *cell += 1;
        let found = refused(&p);
        assert!(found
            .iter()
            .any(|f| matches!(f, Problem::Count { name: n, .. } if *n == name)));
    }
}

#[test]
fn an_unknown_code_is_refused_and_never_read_as_clean() {
    let mut p = payload("E-runtime");
    p.unknowns.reason[0] = Code::raw(99);
    let found = refused(&p);
    let wanted = Problem::UnknownCode {
        list: "UnknownReason",
        value: 99,
    };
    assert!(found.contains(&wanted), "{found:?}");
}

fn swap_permissions(p: &mut Payload, a: usize, b: usize) {
    let t = &mut p.permissions;
    t.component.swap(a, b);
    t.target.swap(a, b);
    t.status.swap(a, b);
    t.rule.swap(a, b);
}

#[test]
fn a_reordered_table_is_refused() {
    let mut p = payload("variant-forbidden-dependency-pair");
    swap_permissions(&mut p, 0, 1);
    let found = refused(&p);
    assert!(found.contains(&Problem::RowOrder {
        table: "permissions",
        row: 1
    }));
    let mut p = payload("L-nest-realworld");
    p.unknowns.detail.swap(0, 1);
    p.unknowns.kind.swap(0, 1);
    p.unknowns.node.swap(0, 1);
    p.unknowns.reason.swap(0, 1);
    p.unknowns.rule.swap(0, 1);
    if p.unknowns == payload("L-nest-realworld").unknowns {
        return;
    }
    assert!(refused(&p).iter().any(|f| matches!(
        f,
        Problem::RowOrder {
            table: "unknowns",
            ..
        }
    )));
}

#[test]
fn a_duplicated_row_is_refused() {
    let mut p = payload("variant-forbidden-dependency-pair");
    let t = &mut p.permissions;
    t.component.insert(1, t.component[0]);
    t.target.insert(1, t.target[0]);
    t.status.insert(1, t.status[0]);
    t.rule.insert(1, t.rule[0]);
    assert!(refused(&p).contains(&Problem::RowOrder {
        table: "permissions",
        row: 1
    }));
    let mut p = payload("variant-decision-conflict");
    let rule = p.rules[0].clone();
    p.rules.insert(0, rule);
    assert!(refused(&p)
        .iter()
        .any(|f| matches!(f, Problem::RowOrder { table: "rules", .. })));
}

#[test]
fn a_pass_rule_without_receipt_and_a_flipped_status_are_refused() {
    let mut p = payload("H-uml-dart");
    let rule = p
        .rules
        .iter_mut()
        .find(|r| r.verdict == RuleVerdict::Pass)
        .unwrap();
    rule.evaluated = false;
    let id = rule.id.clone();
    assert_eq!(refused(&p), vec![Problem::PassWithoutReceipt { rule: id }]);
    let mut p = payload("variant-complete-assignment");
    p.summary.status = Status::Pass;
    let found = refused(&p);
    assert_eq!(
        found,
        vec![Problem::Status {
            stated: Status::Pass,
            rule: Status::Fail
        }]
    );
}

#[test]
fn a_dangling_id_and_an_unsorted_string_table_stop_the_check() {
    let mut p = payload("G-dart");
    let nodes = p.nodes.level.len();
    p.edges.from[0] = u32::try_from(nodes).unwrap();
    let found = refused(&p);
    assert!(matches!(
        found.as_slice(),
        [Problem::IdOutOfRange {
            column: "edges.from",
            ..
        }]
    ));
    let mut p = payload("G-dart");
    p.strings.swap(1, 2);
    assert!(refused(&p).contains(&Problem::StringsNotSorted));
}

#[test]
fn a_short_column_and_a_late_parent_are_refused() {
    let mut p = payload("G-dart");
    p.nodes.fan_in.pop();
    assert!(refused(&p).contains(&Problem::ColumnLengths { table: "nodes" }));
    let mut p = payload("G-dart");
    p.nodes.parent[1] = 5;
    assert!(refused(&p).contains(&Problem::ParentOrder));
}
