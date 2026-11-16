// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `unused_public`: each public item that no other component uses is one violation (AD-670).
//!
//! The model judges the items (`archkeel_model::unused_public`). A violation is a fact also in an
//! incomplete scope, so FAIL needs no proof. An undecided item and a collector that does not state
//! every public symbol hold back a PASS (the scope proof of the model).

use archkeel_contract::UnusedPublic;
use archkeel_model::{unused_public, Model, Unused};

use crate::violation::Violation;

pub(crate) fn check(id: &str, rule: &UnusedPublic, model: &Model) -> Vec<Violation> {
    let mut rows: Vec<Violation> = unused_public(model, rule)
        .into_iter()
        .filter(|(_, judged)| *judged == Unused::Fail)
        .map(|(item, _)| Violation::unused(id, item))
        .collect();
    rows.sort_by(|a, b| a.id().cmp(b.id()));
    rows
}
