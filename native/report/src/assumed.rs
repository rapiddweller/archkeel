// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The premise of a PASS under a declared door reach (AD-664).
//!
//! A declared reach of a door is a premise of the contract, not a proof. A PASS of a rule that
//! the door would hold without its declaration is never a plain PASS: the frame names it in
//! `assumed` with the door sites, and names each applied declaration in `door_reach`. The text and
//! the page read these two keys and print "PASS assuming the declared reach of N doors"
//! (`html_rules.rs` `qualifier`).

use archkeel_contract::head_of;
use archkeel_model::{Applied, Model, ModelTree};
use serde::Serialize;

/// The door sites under whose declared reach the PASS of the rule `id` of `model` holds, if any.
pub(crate) fn sites(model: &Model, id: &str) -> Option<Vec<String>> {
    let rule = model
        .contract()
        .rules()
        .iter()
        .find(|rule| head_of(rule).id().as_text() == id)?;
    let sites: Vec<String> = archkeel_model::assumed(model, rule)
        .into_iter()
        .map(Applied::site)
        .collect();
    (!sites.is_empty()).then_some(sites)
}

/// One applied declaration as the frame writes it.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct DoorRow {
    /// The id of the declaration.
    id: String,
    /// The module of the door.
    module: String,
    /// The line of the door site.
    line: u32,
    /// The form of the door.
    door: &'static str,
    /// The declared module prefixes that the door may import.
    loads: Vec<String>,
    /// The declared module prefixes whose names the door may change.
    changes: Vec<String>,
}

/// The applied declarations of the run, in contract order; none without models.
pub(crate) fn rows(models: Option<&ModelTree>) -> Vec<DoorRow> {
    let applied = models.map(|models| models.root().graph().doors().applied());
    applied.into_iter().flatten().map(row).collect()
}

/// The row of one applied declaration.
fn row(door: &Applied) -> DoorRow {
    DoorRow {
        id: door.id.clone(),
        module: door.module.clone(),
        line: door.line,
        door: door.door(),
        loads: door.loads.clone(),
        changes: door.changes.clone(),
    }
}
