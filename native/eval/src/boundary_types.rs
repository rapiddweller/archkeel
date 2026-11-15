// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `boundary_types`: the written types of the public signatures (AD-550).
//!
//! The model reads the positions (`archkeel_model::boundary_reading`); this module turns each
//! position that breaks the rule into one violation. A violation is a fact also in an incomplete
//! scope, so FAIL needs no proof. A PASS comes only from the scope proof of the model, whose
//! receipt holds back the rule while its surface has a named gap.

use archkeel_contract::BoundaryTypes;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_model::{boundary_reading, Model, Position, Reason};

use crate::violation::Violation;

/// The record of one position that breaks the rule.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BoundaryViolation {
    pub id: String,
    pub rule: String,
    /// `<qualified name>:<position>`.
    pub subject: String,
    pub qualified_name: String,
    pub position: String,
    /// The written type.
    pub text: String,
    /// One reason for each leaf that breaks the rule: its text and why.
    pub reasons: Vec<String>,
    pub evidence: Vec<String>,
}

pub(crate) fn check(
    id: &str,
    rule: &BoundaryTypes,
    model: &Model,
) -> Result<Vec<Violation>, Reason> {
    let reading = boundary_reading(model, rule)?;
    let mut rows: Vec<Violation> = reading
        .violations
        .iter()
        .map(|position| Violation::BoundaryType(Box::new(row(id, position))))
        .collect();
    rows.sort_by(|a, b| a.id().cmp(b.id()));
    Ok(rows)
}

fn row(rule: &str, position: &Position) -> BoundaryViolation {
    BoundaryViolation {
        id: stable_id("VIO", &[Part::Text(rule), Part::Text(&position.subject)]),
        rule: rule.to_owned(),
        subject: position.subject.clone(),
        qualified_name: position.qualified_name.clone(),
        position: position.position.clone(),
        text: position.text.clone(),
        reasons: position
            .leaves
            .iter()
            .map(|leaf| format!("{} is {}", leaf.text, leaf.why))
            .collect(),
        evidence: position.evidence.clone(),
    }
}
