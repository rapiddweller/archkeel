// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `Sections` request: the rows of each requested section, or the reason that it has none.
//!
//! `violations` holds the rows of the rule kinds that `archkeel-eval` decides, sorted by id as
//! the reference engine sorts the section. A row of another kind is not in it: the harness compares a rule
//! section per family (AD-360 point 5), and the rules of that kind are named unsupported.
//! The sections of slice S3 come from the reply part of the model (`topology.rs`): they need no
//! contract, so their reason is the reason of the reply part.

use std::collections::BTreeMap;

use archkeel_eval::{Cited, Outcome, Violation};
use archkeel_model::{Graph, Model, Reason, Section};
use serde_json::{json, Value};

/// One requested section and its rows or the reason that it has none.
pub(crate) type SectionAnswer = (Section, Result<Vec<Value>, Reason>);

/// The derivation of a run: its reply part and its model, or the reason of each missing part.
pub(crate) type Derivation<'a> = (Result<&'a Graph, Reason>, Result<&'a Model, Reason>);

pub(crate) fn answer(
    (graph, model): Derivation<'_>,
    outcomes: &[Outcome],
    sections: &[Section],
) -> Vec<SectionAnswer> {
    sections
        .iter()
        .map(|&section| {
            let graph_rows = graph
                .clone()
                .map(|graph| crate::topology::rows(graph, section));
            let rows = match (graph_rows, model.clone()) {
                (Ok(Some(rows)), _) => Ok(rows),
                (Err(reason), _) if crate::topology::owns(section) => Err(reason),
                (_, Ok(_)) if section == Section::Violations => Ok(violation_rows(outcomes)),
                (_, Ok(model)) => model.rows(section).map(|rows| match rows {}),
                (_, Err(reason)) => Err(reason),
            };
            (section, rows)
        })
        .collect()
}

/// The rows of the sections that have rows, and the reason of each section that has none.
pub(crate) fn split(
    answers: Vec<SectionAnswer>,
) -> (
    BTreeMap<&'static str, Vec<Value>>,
    BTreeMap<&'static str, String>,
) {
    let mut rows = BTreeMap::new();
    let mut reasons = BTreeMap::new();
    for (section, answer) in answers {
        match answer {
            Ok(found) => {
                rows.insert(section.name(), found);
            }
            Err(reason) => {
                reasons.insert(section.name(), reason.to_string());
            }
        }
    }
    (rows, reasons)
}

fn violation_rows(outcomes: &[Outcome]) -> Vec<Value> {
    let mut violations: Vec<&Violation> = outcomes
        .iter()
        .flat_map(|outcome| outcome.violations())
        .collect();
    violations.sort_by(|a, b| a.id().cmp(b.id()));
    violations.into_iter().map(row).collect()
}

/// The 2.9 row of a violation (`classified` in `ir/source_records.py`).
fn row(violation: &Violation) -> Value {
    match violation {
        Violation::Unassigned {
            id,
            rule,
            source,
            name,
            fact_id,
            evidence,
            ..
        } => record(
            [id, rule, fact_id],
            std::slice::from_ref(evidence),
            ["components", "complete_assignment"],
            &[name],
            format!("{name} is not owned by exactly one component"),
            json!({"source": source, "module": name}),
        ),
        Violation::NotAllowedChild {
            id,
            rule,
            root,
            child,
            allowed,
            fact_id,
            evidence,
            ..
        } => record(
            [id, rule, fact_id],
            std::slice::from_ref(evidence),
            ["module_topology", "root_layout"],
            &[child],
            format!("{child} is not an allowed child of {root}"),
            json!({"root": root, "child": child, "allowed_children": allowed}),
        ),
        Violation::OutsideScope {
            id,
            rule,
            dependency,
            cited,
        } => import_record(
            [id, rule],
            cited,
            "external_dependency_scope",
            format!(
                "{} imports {dependency} outside its allowed scope",
                cited.source_module
            ),
            json!({"source_module": cited.source_module, "target_module": cited.target_module,
                   "dependency": dependency}),
        ),
        Violation::Undeclared {
            id,
            rule,
            source,
            dependency,
            cited,
        } => import_record(
            [id, rule],
            cited,
            "complete_external_scope",
            format!("{} imports undeclared {dependency}", cited.source_module),
            json!({"source": source, "source_module": cited.source_module,
                   "target_module": cited.target_module, "dependency": dependency}),
        ),
    }
}

/// A violation record that cites one import: its subjects are the two modules of the import.
fn import_record(ids: [&str; 2], cited: &Cited, kind: &str, title: String, data: Value) -> Value {
    let [id, rule] = ids;
    record(
        [id, rule, &cited.import],
        &cited.evidence,
        ["dependency_violations", kind],
        &[&cited.source_module, &cited.target_module],
        title,
        data,
    )
}

/// A violation record: `[id, rule, cited record]`, the evidence of the cited record (sorted),
/// `[area, kind]` and the subjects.
fn record(
    ids: [&str; 3],
    evidence: &[String],
    names: [&str; 2],
    subjects: &[&String],
    title: String,
    data: Value,
) -> Value {
    let [id, rule, fact_id] = ids;
    let [area, kind] = names;
    json!({
        "id": id,
        "evidence_class": "VIOLATION",
        "area": area,
        "kind": kind,
        "title": title,
        "subjects": sorted_subjects(subjects),
        "evidence_ids": evidence,
        "rule_ids": [rule],
        "fact_ids": [fact_id],
        "provenance": [],
        "data": data,
    })
}

/// `classified` drops an empty subject and sorts the others.
fn sorted_subjects<'a>(names: &[&'a String]) -> Vec<&'a str> {
    let mut found: Vec<&str> = names
        .iter()
        .map(|name| name.as_str())
        .filter(|name| !name.is_empty())
        .collect();
    found.sort_unstable();
    found
}
