// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `boundary_types`: the written types of the public signatures (AD-550).
//!
//! The model reads the positions (`archkeel_model::boundary_reading`); this module turns each
//! position that breaks the rule into one violation. A violation is a fact also in an incomplete
//! scope, so FAIL needs no proof. A PASS comes only from the scope proof of the model, whose
//! receipt holds the rule back while its surface has a named gap.

use archkeel_contract::BoundaryTypes;
use archkeel_model::{boundary_reading, Model, Reason};

use crate::violation::Violation;

pub(crate) fn check(
    id: &str,
    rule: &BoundaryTypes,
    model: &Model,
) -> Result<Vec<Violation>, Reason> {
    let reading = boundary_reading(model, rule)?;
    let mut rows: Vec<Violation> = reading
        .violations
        .iter()
        .map(|position| Violation::boundary(id, position))
        .collect();
    rows.sort_by(|a, b| a.id().cmp(b.id()));
    Ok(rows)
}

impl Violation {
    /// The id of the violation record.
    pub(crate) fn boundary(rule: &str, position: &archkeel_model::Position) -> Self {
        Violation::BoundaryType(Box::new(boundary_row(rule, position)))
    }
}

fn boundary_row(
    rule: &str,
    position: &archkeel_model::Position,
) -> crate::violation::BoundaryViolation {
    let id = archkeel_facts::identity::stable_id(
        "VIO",
        &[
            archkeel_facts::identity::Part::Text(rule),
            archkeel_facts::identity::Part::Text(&position.subject),
        ],
    );
    let reasons = position
        .leaves
        .iter()
        .map(|leaf| format!("{} is {}", leaf.text, leaf.why))
        .collect();
    crate::violation::BoundaryViolation {
        id,
        rule: rule.to_owned(),
        subject: position.subject.clone(),
        qualified_name: position.qualified_name.clone(),
        position: position.position.clone(),
        text: position.text.clone(),
        reasons,
        evidence: position.evidence.clone(),
    }
}

pub(crate) fn protocol(
    id: &str,
    rule: &archkeel_contract::ProtocolDeclarations,
    model: &Model,
) -> Result<Vec<Violation>, Reason> {
    let rows = archkeel_model::protocol_violations(model, rule)?;
    Ok(rows
        .into_iter()
        .map(|member| {
            let position = archkeel_model::Position {
                subject: format!("{}:{}", member.owner, member.name),
                qualified_name: member.owner,
                position: member.name,
                text: member.text,
                leaves: Vec::new(),
                evidence: vec![member.evidence],
            };
            Violation::ProtocolDeclaration(Box::new(boundary_row(id, &position)))
        })
        .collect())
}
