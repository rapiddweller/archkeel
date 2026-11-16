// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `unused_public`: each public item that no other component uses is one violation (AD-670).
//!
//! The model judges the items (`archkeel_model::unused_public`). A violation is a fact also in an
//! incomplete scope, so FAIL needs no proof. An undecided item and a collector that does not state
//! every public symbol hold back a PASS (the scope proof of the model).

use archkeel_contract::UnusedPublic;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_model::{unused_public, Model, PublicItem, Unused};

use crate::violation::{UnusedItem, Violation};

pub(crate) fn check(id: &str, rule: &UnusedPublic, model: &Model) -> Vec<Violation> {
    let mut rows: Vec<Violation> = unused_public(model, rule)
        .into_iter()
        .filter(|(_, judged)| *judged == Unused::Fail)
        .map(|(item, _)| violation(id, item))
        .collect();
    rows.sort_by(|a, b| a.id().cmp(b.id()));
    rows
}

fn violation(rule: &str, item: &PublicItem) -> Violation {
    let subject = format!("{}:{}", item.module, item.name);
    Violation::UnusedPublic(Box::new(UnusedItem {
        id: stable_id("VIO", &[Part::Text(rule), Part::Text(&subject)]),
        rule: rule.to_owned(),
        module: item.module.clone(),
        name: item.name.clone(),
        kind: item.kind.word(),
        evidence: item.evidence.clone(),
    }))
}
