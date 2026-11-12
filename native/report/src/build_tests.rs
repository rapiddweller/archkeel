// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `build` writes the bytes of the Python producer from the same inputs, refuses a frame that
//! leaves a status unexplained, and names each table that no slice produces yet.

use crate::test_support::{bytes, inputs, BUILDABLE};
use crate::{
    build, BuildError, Payload, Permission, Problem, Produced, Relation, Report, RuleDecision,
    Status, Target, Unexplained, UnknownSource, WhyUnknown,
};
use archkeel_model::{Decision, ModelTree, Section, Unsupported};

/// A run without a model: no rule, observation or status can be PASS (AD-381).
const NO_MODEL: Option<&ModelTree> = None;

fn payload(name: &str) -> Payload {
    Payload::decode(&bytes(name)).unwrap()
}

#[test]
fn the_built_frame_equals_the_python_payload_byte_for_byte() {
    for name in BUILDABLE {
        let (outcome, records) = inputs(&payload(name)).unwrap();
        let report = build(outcome, records, NO_MODEL)
            .map_err(|e| format!("{name}: {e}"))
            .unwrap();
        assert_eq!(report.encode().unwrap(), bytes(name), "{name}");
        assert!(Report::read(&report.encode().unwrap()).is_ok(), "{name}");
    }
}

#[test]
fn a_payload_with_a_pass_has_no_inputs_without_the_scope_proof() {
    for name in [
        "F-architecture-tests",
        "H-uml-dart",
        "python-stdlib-demo",
        "G-dart",
    ] {
        assert!(inputs(&payload(name)).is_none(), "{name}");
    }
}

#[test]
fn the_built_frame_keeps_the_decision_of_each_rule() {
    let (outcome, records) = inputs(&payload("L-nest-realworld")).unwrap();
    let ids: Vec<String> = outcome.rules.iter().map(|r| r.id.clone()).collect();
    let report = build(outcome, records, NO_MODEL).unwrap();
    assert_eq!(report.source().status(), Status::Unknown);
    assert!(report.source().pass().is_none());
    for id in ids {
        assert!(report.source().rule(&id).is_some(), "{id}");
    }
}

#[test]
fn a_table_without_rows_is_named_and_never_empty() {
    let part = Unsupported::Section(Section::Cycles);
    for table in [
        "nodes",
        "measures",
        "units",
        "permissions",
        "violations",
        "unknowns",
        "findings",
    ] {
        let (outcome, mut records) = inputs(&payload("E-runtime")).unwrap();
        match table {
            "nodes" => records.tree = Produced::NotProduced(part.clone()),
            "measures" => records.measures = Produced::NotProduced(part.clone()),
            "units" => records.units = Produced::NotProduced(part.clone()),
            "permissions" => records.permissions = Produced::NotProduced(part.clone()),
            "violations" => records.violations = Produced::NotProduced(part.clone()),
            "unknowns" => records.unknowns = Produced::NotProduced(part.clone()),
            _ => records.findings = Produced::NotProduced(part.clone()),
        }
        assert_eq!(
            build(outcome, records, NO_MODEL),
            Err(BuildError::NotProduced {
                table,
                part: part.clone()
            })
        );
    }
}

#[test]
fn a_frame_without_the_graph_says_that_imports_are_not_carried() {
    let (outcome, mut records) = inputs(&payload("L-nest-realworld")).unwrap();
    records.graph = Produced::NotProduced(Unsupported::Section(Section::DependencyEdges));
    let report = build(outcome, records, NO_MODEL).unwrap();
    let p = report.payload();
    assert!(p.edges.level.is_empty() && p.crossings.edge.is_empty() && p.via.is_empty());
    let not_carried: Vec<_> = p.run.not_carried.iter().filter_map(|c| c.known()).collect();
    assert!(not_carried.contains(&Relation::Imports));
    assert!(not_carried.contains(&Relation::Reexports));
}

#[test]
fn an_incomplete_observation_without_a_row_cannot_be_built() {
    let (mut outcome, mut records) = inputs(&payload("E-runtime")).unwrap();
    outcome.diagnostics.clear();
    records.unknowns = Produced::Rows(Vec::new());
    let wanted = BuildError::Unexplained(vec![
        Unexplained::IncompleteWithoutRow,
        Unexplained::UnknownWithoutRow,
    ]);
    assert_eq!(build(outcome, records, NO_MODEL), Err(wanted));
}

#[test]
fn the_status_comes_from_the_rows_and_a_run_without_a_model_has_no_pass() {
    let (outcome, records) = inputs(&payload("E-runtime")).unwrap();
    let report = build(outcome, records, NO_MODEL).unwrap();
    assert_eq!(report.source().status(), Status::Unknown);
    assert_eq!(report.source().observation(), Status::Unknown);
    assert!(report.source().pass().is_none());
    // The PASS paths need a model: `run_tests.rs` builds them from a real model and eval run.
}

#[test]
fn a_rule_reason_comes_from_its_verdict() {
    let (mut outcome, records) = inputs(&payload("L-nest-realworld")).unwrap();
    let unknown = outcome
        .rules
        .iter()
        .position(|r| r.why_unknown.is_some())
        .unwrap();
    outcome.rules[unknown].why_unknown = None;
    let id = outcome.rules[unknown].id.clone();
    let wanted = BuildError::ReasonMismatch { rule: id };
    assert_eq!(build(outcome, records.clone(), NO_MODEL), Err(wanted));
    let (mut outcome, _) = inputs(&payload("L-nest-realworld")).unwrap();
    outcome.rules[unknown].decision = RuleDecision::Decided(Decision::fail());
    outcome.rules[unknown].why_unknown = Some(WhyUnknown::NoReceipt);
    let id = outcome.rules[unknown].id.clone();
    let wanted = BuildError::ReasonMismatch { rule: id };
    assert_eq!(build(outcome, records, NO_MODEL), Err(wanted));
}

#[test]
fn a_frame_that_breaks_another_rule_is_invalid_by_name() {
    let (outcome, mut records) = inputs(&payload("L-nest-realworld")).unwrap();
    let Produced::Rows(permissions) = &mut records.permissions else {
        return;
    };
    let row = permissions
        .iter()
        .position(|p| p.status == Permission::Forbidden)
        .unwrap();
    permissions[row].rule = None;
    let wanted = BuildError::Invalid(vec![Problem::PermissionRule { row }]);
    assert_eq!(build(outcome, records, NO_MODEL), Err(wanted));
}

#[test]
fn a_run_without_target_gets_its_run_row_and_no_contract() {
    let (mut outcome, records) = inputs(&payload("E-runtime")).unwrap();
    outcome.target = Target::Absent;
    let report = build(outcome, records, NO_MODEL).unwrap();
    let p = report.payload();
    assert!(!p.run.target && p.run.contract.is_none());
    assert!(p.unknowns.source.iter().any(|s| s.is(UnknownSource::Run)));
    assert_eq!(p.summary.status, Status::Unknown);
}

/// `tests/test_native_report.py` sets `ARCHKEEL_REPORT_SAMPLES` to a directory: this test writes
/// built frames there, and the Python test validates each against the schema.
#[test]
fn write_built_samples_for_the_schema_test() {
    let Some(directory) = std::env::var_os("ARCHKEEL_REPORT_SAMPLES") else {
        return;
    };
    let directory = std::path::PathBuf::from(directory);
    for name in BUILDABLE {
        let (outcome, mut records) = inputs(&payload(name)).unwrap();
        let built = build(outcome.clone(), records.clone(), NO_MODEL).unwrap();
        std::fs::write(
            directory.join(format!("{name}.built.json")),
            built.encode().unwrap(),
        )
        .unwrap();
        records.graph = Produced::NotProduced(Unsupported::Section(Section::DependencyEdges));
        let mut absent = outcome;
        absent.target = Target::Absent;
        let built = build(absent, records, NO_MODEL).unwrap();
        let file = directory.join(format!("{name}.no-graph-no-target.json"));
        std::fs::write(file, built.encode().unwrap()).unwrap();
    }
}
