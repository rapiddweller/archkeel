// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rows of `boundary_types` in the hygiene of a run (AD-550).
//!
//! Release 4.0.1 names each position of a public signature that it cannot decide
//! (`boundary_type_position`) and each exception of the contract that no position uses. The core
//! names the same: one row for each position or entry that syntax does not decide, with the cause
//! and the written text, so an accepted list of the baseline binds the written type. A row holds
//! back a PASS and never makes a verdict.

use archkeel_contract::Rule;
use archkeel_model::{boundary_reading, ModelTree};

use crate::hygiene_refs::{model_of, Finding};

/// The rows of the `boundary_types` rules of the contract of `index` (the root when `None`).
pub(crate) fn findings(tree: &ModelTree, index: Option<usize>) -> Vec<Finding> {
    let Some(model) = model_of(tree, index) else {
        return Vec::new();
    };
    let mut found = Vec::new();
    for (position, rule) in model.contract().rules().iter().enumerate() {
        let Rule::BoundaryTypes(rule) = rule else {
            continue;
        };
        let Ok(reading) = boundary_reading(model, rule) else {
            continue;
        };
        let pointer = format!("/rules/{position}");
        for gap in &reading.gaps {
            found.push((
                "boundary_type_position",
                pointer.clone(),
                gap.subject.clone(),
                gap.reason(),
            ));
        }
        for stale in &reading.stale {
            found.push((
                "boundary_type_allowance_stale",
                pointer.clone(),
                stale.subject.clone(),
                format!(
                    "The exception for {} matches no position of the public surface.",
                    stale.annotation
                ),
            ));
        }
    }
    found
}
