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
