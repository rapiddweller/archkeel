// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `Sections` request: the rows of each requested section, or the reason that it has none.
//!
//! `violations` holds the rows of the rule kinds that `archkeel-eval` decides, sorted by id as
//! the reference engine sorts the section. A row of another kind is not in it: the harness compares a rule
//! section per family (AD-360 point 5), and the rules of that kind are named unsupported.

use std::collections::BTreeMap;

use archkeel_eval::{Outcome, Violation};
use archkeel_model::{Model, Reason, Section};
use serde_json::{json, Value};

/// One requested section and its rows or the reason that it has none.
pub(crate) type SectionAnswer = (Section, Result<Vec<Value>, Reason>);

pub(crate) fn answer(
    model: &Result<Model, Reason>,
    outcomes: &[Outcome],
    sections: &[Section],
) -> Vec<SectionAnswer> {
    sections
        .iter()
        .map(|section| {
            let rows = match model {
                Ok(_) if *section == Section::Violations => Ok(violation_rows(outcomes)),
                Ok(model) => model.rows(*section).map(|rows| match rows {}),
                Err(reason) => Err(reason.clone()),
            };
            (*section, rows)
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
            [id, rule, fact_id, evidence],
            ["components", "complete_assignment", name],
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
            [id, rule, fact_id, evidence],
            ["module_topology", "root_layout", child],
            format!("{child} is not an allowed child of {root}"),
            json!({"root": root, "child": child, "allowed_children": allowed}),
        ),
    }
}

/// A violation record: `[id, rule, cited record, its evidence]` and `[area, kind, subject]`.
fn record(ids: [&str; 4], names: [&str; 3], title: String, data: Value) -> Value {
    let [id, rule, fact_id, evidence] = ids;
    let [area, kind, subject] = names;
    json!({
        "id": id,
        "evidence_class": "VIOLATION",
        "area": area,
        "kind": kind,
        "title": title,
        "subjects": subjects(subject),
        "evidence_ids": [evidence],
        "rule_ids": [rule],
        "fact_ids": [fact_id],
        "provenance": [],
        "data": data,
    })
}

/// `classified` drops an empty subject.
fn subjects(name: &str) -> Vec<&str> {
    Some(name)
        .filter(|name| !name.is_empty())
        .into_iter()
        .collect()
}
